"""
Shared ReAct loop for all specialist agents.

Features:
- Parallel tool execution via asyncio.gather (when model calls multiple tools at once)
- Extended thinking support (set thinking_budget > 0 to enable; requires Sonnet)
- Thinking trace collection for transparency/debugging
"""
import asyncio
import json
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Extended thinking requires at least this many output tokens beyond the budget
_THINKING_OUTPUT_HEADROOM = 4096


def _serialize_content(content: Any) -> Any:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return [
            block.model_dump() if hasattr(block, "model_dump") else block
            for block in content
        ]
    if hasattr(content, "model_dump"):
        return content.model_dump()
    return str(content)


def _serialize_conversation(conversation: list) -> list:
    return [
        {"role": msg["role"], "content": _serialize_content(msg["content"])}
        for msg in conversation
    ]


def _build_conversation(messages: list, history: list | None, user_message: str) -> list:
    """Build Anthropic-format conversation from history or text-only fallback."""
    if history:
        conversation = list(history)
    else:
        conversation = []
        for m in messages:
            role = "user" if m.get("role") == "user" else "assistant"
            text = (m.get("content") or "").strip()
            if text:
                conversation.append({"role": role, "content": text})
    conversation.append({"role": "user", "content": user_message})
    return conversation


def _extract_thinking(content_blocks: list) -> list[str]:
    """Extract thinking text from response content blocks."""
    traces = []
    for block in content_blocks:
        if hasattr(block, "type") and block.type == "thinking":
            traces.append(getattr(block, "thinking", ""))
    return [t for t in traces if t]


async def run_agent(
    client,
    model: str,
    system_prompt: str,
    tool_schemas: list[dict],
    execute_tool_fn: Callable,  # async (name, args, ctx) -> str
    conversation: list[dict],
    ctx: dict,
    max_loops: int = 8,
    thinking_budget: int = 0,
) -> dict:
    """
    ReAct loop: call Claude with tools, execute tool_use blocks, repeat.

    When thinking_budget > 0, extended thinking is enabled — the model produces
    explicit reasoning traces before each tool call and before the final answer.
    Requires Sonnet (Haiku does not support extended thinking).

    Tool calls within a single turn are executed in parallel via asyncio.gather.

    Returns {"response": str, "tool_calls": list, "thinking": list[str], "conversation": list}.
    """
    tool_calls_made = []
    thinking_traces: list[str] = []

    # Build API kwargs — extended thinking changes max_tokens and adds thinking param
    def _build_kwargs(messages: list) -> dict:
        kwargs: dict = {
            "model": model,
            "system": system_prompt,
            "messages": messages,
            "tools": tool_schemas,
        }
        if thinking_budget > 0:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
            # max_tokens must exceed budget_tokens + room for output
            kwargs["max_tokens"] = thinking_budget + _THINKING_OUTPUT_HEADROOM
        else:
            kwargs["max_tokens"] = 4096
        return kwargs

    for loop_num in range(max_loops):
        try:
            response = await asyncio.to_thread(
                client.messages.create,
                **_build_kwargs(conversation),
            )
        except Exception as e:
            logger.warning(f"Agent generate error (loop {loop_num}): {e}")
            return {
                "response": f"AI error: {e}",
                "tool_calls": tool_calls_made,
                "thinking": thinking_traces,
                "conversation": _serialize_conversation(conversation),
            }

        # Collect any thinking blocks from this turn
        thinking_traces.extend(_extract_thinking(response.content))

        if response.stop_reason == "tool_use":
            # Append assistant turn — must include thinking blocks (API validates their signatures)
            conversation.append({
                "role": "assistant",
                "content": [b.model_dump() for b in response.content],
            })

            # Collect all tool_use blocks from this turn
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            tasks = [
                (b.id, b.name, dict(b.input) if b.input else {})
                for b in tool_use_blocks
            ]

            # Execute all tools in parallel — one tool failure doesn't block the others
            raw_results = await asyncio.gather(
                *[execute_tool_fn(name, args, ctx) for _, name, args in tasks],
                return_exceptions=True,
            )

            tool_results = []
            for (tool_use_id, name, args), result in zip(tasks, raw_results):
                if isinstance(result, Exception):
                    logger.warning(f"Tool {name} raised: {result}")
                    result = json.dumps({"error": str(result)})
                tool_calls_made.append({"tool": name, "args": args})
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": result,
                })

            conversation.append({"role": "user", "content": tool_results})
            continue

        # end_turn — extract final text response
        text = next(
            (b.text for b in response.content if hasattr(b, "text") and b.text),
            "I couldn't generate a response.",
        )
        conversation.append({"role": "assistant", "content": text})
        return {
            "response": text,
            "tool_calls": tool_calls_made,
            "thinking": thinking_traces,
            "conversation": _serialize_conversation(conversation),
        }

    return {
        "response": "Reached maximum reasoning steps. Try a simpler question.",
        "tool_calls": tool_calls_made,
        "thinking": thinking_traces,
        "conversation": _serialize_conversation(conversation),
    }
