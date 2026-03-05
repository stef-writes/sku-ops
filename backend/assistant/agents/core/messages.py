"""Message extraction and history building for PydanticAI agent conversations."""
import json

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)


def build_message_history(history: list[dict] | None) -> list | None:
    """Convert text-only {role, content} pairs to PydanticAI ModelMessage list."""
    if not history:
        return None
    messages: list[ModelRequest | ModelResponse] = []
    for h in history:
        content = (h.get("content") or "").strip()
        if not content:
            continue
        if h.get("role") == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content=content)]))
        else:
            messages.append(ModelResponse(parts=[TextPart(content=content)], model_name=None))
    return messages or None


def extract_text_history(messages) -> list[dict]:  # type: ignore[type-arg]
    """Extract text-only turns from PydanticAI all_messages() for session storage."""
    out: list[dict] = []
    for msg in messages:
        if isinstance(msg, ModelRequest):
            for req_part in msg.parts:
                if isinstance(req_part, UserPromptPart):
                    text = req_part.content if isinstance(req_part.content, str) else ""
                    if text:
                        out.append({"role": "user", "content": text})
        elif isinstance(msg, ModelResponse):
            for resp_part in msg.parts:
                if isinstance(resp_part, TextPart) and resp_part.content:
                    out.append({"role": "assistant", "content": resp_part.content})
    return out


def extract_tool_calls(messages) -> list[dict]:
    """Extract tool call names only (lightweight, for API response)."""
    out = []
    for msg in messages:
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, ToolCallPart):
                    out.append({"tool": part.tool_name})
    return out


def extract_tool_calls_detailed(messages) -> list[dict]:
    """Extract tool calls with arguments and return values for monitoring."""
    return_map: dict[str, str] = {}
    for msg in messages:
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, ToolReturnPart):
                    ret = part.content if isinstance(part.content, str) else str(part.content)
                    return_map[part.tool_call_id] = ret[:500]

    out: list[dict] = []
    for msg in messages:
        if isinstance(msg, ModelResponse):
            for resp_part in msg.parts:
                if isinstance(resp_part, ToolCallPart):
                    args_raw = resp_part.args
                    if isinstance(args_raw, str):
                        try:
                            args_raw = json.loads(args_raw)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    entry = {
                        "tool": resp_part.tool_name,
                        "args": args_raw,
                        "result_preview": return_map.get(resp_part.tool_call_id, ""),
                    }
                    out.append(entry)
    return out
