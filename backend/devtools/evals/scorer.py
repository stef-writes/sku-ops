"""Deterministic assertion checkers for eval test cases.

Every assertion is a pure function: (test_case, eval_result) -> (passed, detail).
No LLM calls.  Fully unit-testable.
"""
import re
from dataclasses import dataclass, field

from assistant.agents.core.tokens import count_tokens
from assistant.agents.core.validators import _extract_numbers, _numbers_from_tool_results


@dataclass
class AssertionResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class ScoreCard:
    case_id: str
    passed: bool
    assertions: list[AssertionResult] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    model: str = ""

    @property
    def pass_rate(self) -> float:
        if not self.assertions:
            return 1.0
        return sum(1 for a in self.assertions if a.passed) / len(self.assertions)


# ── Individual assertion functions ────────────────────────────────────────────

def assert_tool_called(tool_name: str, tool_calls: list[dict]) -> AssertionResult:
    """Check that a specific tool was invoked."""
    called = [tc.get("tool") for tc in tool_calls]
    ok = tool_name in called
    return AssertionResult(
        name=f"tool_called:{tool_name}",
        passed=ok,
        detail=f"called={called}" if not ok else "",
    )


def assert_min_tools_called(n: int, tool_calls: list[dict]) -> AssertionResult:
    """Check that at least N distinct tools were invoked."""
    unique: set[str] = {tc["tool"] for tc in tool_calls if tc.get("tool") is not None}
    ok = len(unique) >= n
    return AssertionResult(
        name=f"min_tools_called:{n}",
        passed=ok,
        detail=f"got {len(unique)}: {sorted(unique)}" if not ok else "",
    )


def assert_response_contains(terms: list[str], response: str) -> AssertionResult:
    """Check that the response contains all specified terms (case-insensitive)."""
    lower = response.lower()
    missing = [t for t in terms if t.lower() not in lower]
    return AssertionResult(
        name=f"response_contains:{terms}",
        passed=len(missing) == 0,
        detail=f"missing: {missing}" if missing else "",
    )


def assert_response_has_sections(headers: list[str], response: str) -> AssertionResult:
    """Check that the response has markdown section headers matching the given list."""
    lower = response.lower()
    missing = [h for h in headers if f"## {h.lower()}" not in lower and f"**{h.lower()}" not in lower]
    return AssertionResult(
        name=f"response_has_sections:{headers}",
        passed=len(missing) == 0,
        detail=f"missing sections: {missing}" if missing else "",
    )


def assert_max_output_tokens(n: int, response: str) -> AssertionResult:
    """Check that the response is within the token budget."""
    tokens = count_tokens(response)
    ok = tokens <= n
    return AssertionResult(
        name=f"max_output_tokens:{n}",
        passed=ok,
        detail=f"got {tokens} tokens" if not ok else f"{tokens} tokens",
    )


def assert_no_bare_units(response: str) -> AssertionResult:
    """Check that the response doesn't use bare 'units' without a UOM qualifier."""
    bare = bool(re.search(r"\b\d+\s+units?\b", response, re.IGNORECASE))
    return AssertionResult(
        name="no_bare_units",
        passed=not bare,
        detail="found bare 'units' without UOM" if bare else "",
    )


def assert_no_ungrounded_numbers(response: str, tool_results: list[dict]) -> AssertionResult:
    """Check that numbers in the response can be traced back to tool results."""
    resp_nums = _extract_numbers(response)
    if not resp_nums:
        return AssertionResult(name="no_ungrounded_numbers", passed=True)

    tool_nums = _numbers_from_tool_results(tool_results)
    if not tool_nums:
        return AssertionResult(name="no_ungrounded_numbers", passed=True, detail="no tool numbers to compare")

    grounded = resp_nums & tool_nums
    ratio = len(grounded) / len(resp_nums) if resp_nums else 1.0
    ok = ratio >= 0.5
    return AssertionResult(
        name="no_ungrounded_numbers",
        passed=ok,
        detail=f"grounding ratio: {ratio:.0%} ({len(grounded)}/{len(resp_nums)})",
    )


def assert_routed_to(expected: list[str], actual: list[str]) -> AssertionResult:
    """Check that the router classified to the expected agents (order-independent)."""
    ok = set(expected) == set(actual)
    return AssertionResult(
        name=f"routed_to:{expected}",
        passed=ok,
        detail=f"got {actual}" if not ok else "",
    )


def assert_latency_under(ms: int, actual_ms: int) -> AssertionResult:
    """Check that the response latency is under the threshold."""
    ok = actual_ms <= ms
    return AssertionResult(
        name=f"latency_under:{ms}ms",
        passed=ok,
        detail=f"got {actual_ms}ms" if not ok else "",
    )


def assert_cost_under(usd: float, actual_usd: float) -> AssertionResult:
    """Check that the response cost is under the threshold."""
    ok = actual_usd <= usd
    return AssertionResult(
        name=f"cost_under:${usd}",
        passed=ok,
        detail=f"got ${actual_usd:.6f}" if not ok else "",
    )


# ── Score a full test case ────────────────────────────────────────────────────

def score_case(
    case: dict,
    response: str,
    tool_calls: list[dict],
    tool_calls_detailed: list[dict],
    usage: dict,
    latency_ms: int = 0,
    routed_to: list[str] | None = None,
) -> ScoreCard:
    """Run all assertions defined in a test case and produce a ScoreCard."""
    results: list[AssertionResult] = []

    for assertion in case.get("assertions", []):
        if isinstance(assertion, dict):
            for key, value in assertion.items():
                if key == "tool_called":
                    results.append(assert_tool_called(value, tool_calls))
                elif key == "min_tools_called":
                    results.append(assert_min_tools_called(value, tool_calls))
                elif key == "response_contains":
                    results.append(assert_response_contains(value, response))
                elif key == "response_has_sections":
                    results.append(assert_response_has_sections(value, response))
                elif key == "max_output_tokens":
                    results.append(assert_max_output_tokens(value, response))
                elif key == "no_bare_units" and value:
                    results.append(assert_no_bare_units(response))
                elif key == "no_ungrounded_numbers" and value:
                    results.append(assert_no_ungrounded_numbers(response, tool_calls_detailed))
                elif key == "latency_under":
                    results.append(assert_latency_under(value, latency_ms))
                elif key == "cost_under":
                    results.append(assert_cost_under(value, usage.get("cost_usd", 0)))

    # Auto-check expected_agents if routed_to is provided
    if routed_to and "expected_agents" in case:
        results.append(assert_routed_to(case["expected_agents"], routed_to))

    all_passed = all(r.passed for r in results) if results else True

    return ScoreCard(
        case_id=case.get("id", "unknown"),
        passed=all_passed,
        assertions=results,
        total_input_tokens=usage.get("input_tokens", 0),
        total_output_tokens=usage.get("output_tokens", 0),
        cost_usd=usage.get("cost_usd", 0),
        latency_ms=latency_ms,
        model=usage.get("model", ""),
    )
