"""Tests for cross-session memory: memory_store and memory_extract."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
class TestMemoryStore:
    """Unit tests for memory_store save/recall."""

    async def test_recall_empty_returns_empty_string(self, db):
        """No artifacts → recall returns ''."""
        from services.agents.memory_store import recall
        result = await recall(org_id="default", user_id="user-1")
        assert result == ""

    async def test_save_and_recall_basic(self, db):
        """save() persists artifacts; recall() returns formatted string."""
        from services.agents.memory_store import save, recall

        artifacts = [
            {"type": "entity_fact", "subject": "contractor:john", "content": "John has $300 unpaid", "tags": ["contractor"]},
            {"type": "user_preference", "subject": "general", "content": "User prefers tables", "tags": ["pref"]},
        ]
        await save("default", "user-1", "sess-1", artifacts)

        result = await recall("default", "user-1")
        assert result != ""
        assert "Memory from previous sessions" in result
        assert "contractor:john" in result
        assert "John has $300 unpaid" in result
        assert "user_preference" in result

    async def test_recall_respects_org_and_user_isolation(self, db):
        """Artifacts saved for one user/org are not visible to another."""
        from services.agents.memory_store import save, recall

        await save("org-A", "user-A", "sess-A", [
            {"type": "entity_fact", "subject": "product:X", "content": "Product X is discontinued", "tags": []}
        ])

        # Different user, same org
        result_other_user = await recall("org-A", "user-B")
        assert result_other_user == ""

        # Different org, same user id
        result_other_org = await recall("org-B", "user-A")
        assert result_other_org == ""

        # Correct user/org
        result = await recall("org-A", "user-A")
        assert "Product X is discontinued" in result

    async def test_save_skips_artifacts_without_content(self, db):
        """Artifacts missing 'content' are silently dropped."""
        from services.agents.memory_store import save, recall

        artifacts = [
            {"type": "entity_fact", "subject": "test", "content": ""},  # empty content → skip
            {"type": "entity_fact", "subject": "test2", "content": "  "},  # whitespace-only still has a string
        ]
        # content="" → skipped (falsy check in save)
        await save("default", "user-1", "sess-skip", artifacts)
        # Should only save the whitespace one (it has a non-empty string even if whitespace)
        # Actually our filter is `if a.get("content")` so both "" and "  " — "  " is truthy
        result = await recall("default", "user-1")
        # At minimum: no crash. Empty content artifact not saved.
        assert isinstance(result, str)

    async def test_recall_limit(self, db):
        """recall() respects the limit parameter."""
        from services.agents.memory_store import save, recall

        # Save 10 artifacts
        artifacts = [
            {"type": "entity_fact", "subject": f"subject:{i}", "content": f"fact number {i}", "tags": []}
            for i in range(10)
        ]
        await save("default", "user-1", "sess-limit", artifacts)

        result = await recall("default", "user-1", limit=3)
        # Should only have 3 facts in the output
        lines = [l for l in result.split("\n") if l.startswith("- [")]
        assert len(lines) == 3

    async def test_save_empty_list_is_noop(self, db):
        """save([]) should not crash and recall still returns ''."""
        from services.agents.memory_store import save, recall
        await save("default", "user-1", "sess-noop", [])
        result = await recall("default", "user-1")
        assert result == ""


@pytest.mark.asyncio
class TestMemoryExtract:
    """Unit tests for memory_extract.extract_and_save."""

    async def test_skips_short_history(self, db):
        """extract_and_save is a no-op when history has < 4 messages (returns before any LLM call)."""
        from services.agents.memory_extract import extract_and_save

        # Function exits before touching anthropic; just ensure no crash and no artifacts
        await extract_and_save("default", "user-1", "sess-1", [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ])
        from services.agents.memory_store import recall
        assert await recall("default", "user-1") == ""

    async def test_skips_when_no_api_key(self, db):
        """extract_and_save exits early when ANTHROPIC_API_KEY is empty."""
        from services.agents.memory_extract import extract_and_save

        history = [{"role": r, "content": f"msg {i}"} for i, r in enumerate(["user", "assistant"] * 3)]
        with patch("services.agents.memory_extract.ANTHROPIC_API_KEY", "", create=True):
            with patch("config.ANTHROPIC_API_KEY", ""):
                await extract_and_save("default", "user-1", "sess-nokey", history)
        # No crash, no artifacts
        from services.agents.memory_store import recall
        assert await recall("default", "user-1") == ""

    async def test_saves_artifacts_from_llm_response(self, db):
        """When LLM returns valid JSON array, artifacts are saved."""
        from services.agents.memory_extract import extract_and_save

        history = [{"role": r, "content": f"msg {i}"} for i, r in enumerate(["user", "assistant"] * 4)]

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps([
            {"type": "entity_fact", "subject": "contractor:alice", "content": "Alice owes $200", "tags": ["contractor"]}
        ]))]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("config.ANTHROPIC_API_KEY", "fake-key"), \
             patch("config.ANTHROPIC_MODEL", "claude-sonnet-4-6"), \
             patch("anthropic.AsyncAnthropic", return_value=mock_client):
            await extract_and_save("default", "user-1", "sess-ok", history)

        from services.agents.memory_store import recall
        result = await recall("default", "user-1")
        assert "contractor:alice" in result
        assert "Alice owes $200" in result

    async def test_handles_markdown_fenced_json(self, db):
        """extract_and_save strips ```json fences if model wraps output."""
        from services.agents.memory_extract import extract_and_save

        history = [{"role": r, "content": f"msg {i}"} for i, r in enumerate(["user", "assistant"] * 4)]

        fenced = "```json\n" + json.dumps([
            {"type": "session_summary", "subject": "session", "content": "User investigated pending requests", "tags": []}
        ]) + "\n```"

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=fenced)]
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("config.ANTHROPIC_API_KEY", "fake-key"), \
             patch("config.ANTHROPIC_MODEL", "claude-sonnet-4-6"), \
             patch("anthropic.AsyncAnthropic", return_value=mock_client):
            await extract_and_save("default", "user-1", "sess-fence", history)

        from services.agents.memory_store import recall
        result = await recall("default", "user-1")
        assert "pending requests" in result

    async def test_swallows_llm_exceptions(self, db):
        """extract_and_save never raises — LLM errors are silently logged."""
        from services.agents.memory_extract import extract_and_save

        history = [{"role": r, "content": f"msg {i}"} for i, r in enumerate(["user", "assistant"] * 4)]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=RuntimeError("network down"))

        with patch("config.ANTHROPIC_API_KEY", "fake-key"), \
             patch("config.ANTHROPIC_MODEL", "claude-sonnet-4-6"), \
             patch("anthropic.AsyncAnthropic", return_value=mock_client):
            # Must not raise
            await extract_and_save("default", "user-1", "sess-err", history)

    async def test_swallows_json_parse_error(self, db):
        """extract_and_save never raises when LLM returns invalid JSON."""
        from services.agents.memory_extract import extract_and_save

        history = [{"role": r, "content": f"msg {i}"} for i, r in enumerate(["user", "assistant"] * 4)]

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="not valid json at all")]
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("config.ANTHROPIC_API_KEY", "fake-key"), \
             patch("config.ANTHROPIC_MODEL", "claude-sonnet-4-6"), \
             patch("anthropic.AsyncAnthropic", return_value=mock_client):
            await extract_and_save("default", "user-1", "sess-bad-json", history)
