"""Eval runner — loads datasets, runs test cases, collects scores.

Usage:
    python -m devtools.evals.runner --suite routing
    python -m devtools.evals.runner --suite inventory --model anthropic/claude-haiku-4-5
    python -m devtools.evals.runner --suite all
    python -m devtools.evals.runner --suite all --compare "anthropic/claude-sonnet-4-6,anthropic/claude-haiku-4-5"
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from assistant.agents.tools.registry import init_tools
from assistant.application.assistant import chat
from devtools.evals.scorer import score_case
from shared.infrastructure.database import init_db

logger = logging.getLogger(__name__)

_DATASETS_DIR = Path(__file__).parent / "datasets"
_REPORTS_DIR = Path(__file__).parent / "reports"

_AVAILABLE_SUITES = ("routing", "inventory", "ops", "finance")


# ── Data types ────────────────────────────────────────────────────────────────


@dataclass
class EvalCaseResult:
    case_id: str
    passed: bool
    assertions: list[dict] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    model: str = ""
    error: str | None = None


@dataclass
class EvalReport:
    suite: str
    model: str
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    avg_latency_ms: float = 0.0
    results: list[EvalCaseResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return self.passed_cases / self.total_cases if self.total_cases else 0.0


# ── Dataset loading ───────────────────────────────────────────────────────────


def load_dataset(suite: str) -> list[dict]:
    path = _DATASETS_DIR / f"{suite}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f) or []


# ── Routing eval ──────────────────────────────────────────────────────────────


async def _eval_routing_case(case: dict) -> EvalCaseResult:
    """Run a routing test case through the unified agent (LLM-native routing)."""
    return await _eval_agent_case(case, agent_type="routing")


# ── Agent eval ────────────────────────────────────────────────────────────────


async def _eval_agent_case(
    case: dict, agent_type: str, _model_override: str | None = None
) -> EvalCaseResult:
    """Run a single agent test case through the full chat pipeline."""
    t0 = time.monotonic()
    try:
        result = await chat(
            user_message=case["input"],
            history=None,
            ctx={"org_id": "default"},
            mode="fast",
            agent_type=agent_type,
        )
        latency = int((time.monotonic() - t0) * 1000)

        card = score_case(
            case=case,
            response=result.get("response", ""),
            tool_calls=result.get("tool_calls", []),
            tool_calls_detailed=result.get("tool_calls", []),
            usage=result.get("usage", {}),
            latency_ms=latency,
        )
        return EvalCaseResult(
            case_id=card.case_id,
            passed=card.passed,
            assertions=[
                {"name": a.name, "passed": a.passed, "detail": a.detail} for a in card.assertions
            ],
            input_tokens=card.total_input_tokens,
            output_tokens=card.total_output_tokens,
            cost_usd=card.cost_usd,
            latency_ms=card.latency_ms,
            model=card.model,
        )
    except (ValueError, KeyError, RuntimeError, OSError) as e:
        latency = int((time.monotonic() - t0) * 1000)
        return EvalCaseResult(
            case_id=case.get("id", "?"), passed=False, error=str(e), latency_ms=latency
        )


# ── Suite runner ──────────────────────────────────────────────────────────────


async def run_eval_suite(suite: str, model_override: str | None = None) -> EvalReport:
    """Run all test cases in a dataset."""
    cases = load_dataset(suite)
    results: list[EvalCaseResult] = []

    for case in cases:
        if suite == "routing":
            r = await _eval_routing_case(case)
        else:
            r = await _eval_agent_case(case, agent_type=suite, model_override=model_override)
        results.append(r)
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.case_id}: {case['input'][:60]}")
        if not r.passed:
            for a in r.assertions:
                if not a["passed"]:
                    print(f"         -> {a['name']}: {a['detail']}")
            if r.error:
                print(f"         -> ERROR: {r.error}")

    passed = sum(1 for r in results if r.passed)
    report = EvalReport(
        suite=suite,
        model=model_override or "default",
        total_cases=len(results),
        passed_cases=passed,
        failed_cases=len(results) - passed,
        total_input_tokens=sum(r.input_tokens for r in results),
        total_output_tokens=sum(r.output_tokens for r in results),
        total_cost_usd=sum(r.cost_usd for r in results),
        avg_latency_ms=sum(r.latency_ms for r in results) / len(results) if results else 0,
        results=results,
    )
    return report


def _save_report(report: EvalReport) -> Path:
    """Save report to JSON file."""
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = _REPORTS_DIR / f"{report.suite}_{ts}.json"
    with open(path, "w") as f:
        json.dump(asdict(report), f, indent=2, default=str)
    return path


def _print_summary(report: EvalReport) -> None:
    rate = report.pass_rate * 100
    print(f"\n{'=' * 60}")
    print(f"  Suite: {report.suite}  |  Model: {report.model}")
    print(f"  Pass rate: {report.passed_cases}/{report.total_cases} ({rate:.0f}%)")
    if report.total_cost_usd > 0:
        print(
            f"  Cost: ${report.total_cost_usd:.6f}  |  Tokens: {report.total_input_tokens}in + {report.total_output_tokens}out"
        )
    if report.avg_latency_ms > 0:
        print(f"  Avg latency: {report.avg_latency_ms:.0f}ms")
    print(f"{'=' * 60}\n")


# ── CLI ───────────────────────────────────────────────────────────────────────


async def _main():
    parser = argparse.ArgumentParser(description="Run agent eval suites")
    parser.add_argument(
        "--suite", required=True, help=f"Suite name: {', '.join(_AVAILABLE_SUITES)} or 'all'"
    )
    parser.add_argument("--model", default=None, help="Override model (OpenRouter format)")
    parser.add_argument("--compare", default=None, help="Comma-separated models to A/B compare")
    parser.add_argument("--save", action="store_true", help="Save report to JSON")
    args = parser.parse_args()

    await init_db()
    init_tools()

    suites = list(_AVAILABLE_SUITES) if args.suite == "all" else [args.suite]

    if args.compare:
        models = [m.strip() for m in args.compare.split(",")]
        for suite in suites:
            print(f"\n{'#' * 60}")
            print(f"  A/B comparison: {suite}")
            print(f"{'#' * 60}")
            for model in models:
                print(f"\n--- Model: {model} ---")
                report = await run_eval_suite(suite, model_override=model)
                _print_summary(report)
                if args.save:
                    path = _save_report(report)
                    print(f"  Report saved: {path}")
    else:
        for suite in suites:
            print(f"\n--- {suite.upper()} eval ---")
            report = await run_eval_suite(suite, model_override=args.model)
            _print_summary(report)
            if args.save:
                path = _save_report(report)
                print(f"  Report saved: {path}")


def main():
    backend_dir = str(Path(__file__).resolve().parent.parent.parent)
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    logging.basicConfig(level=logging.WARNING)
    asyncio.run(_main())


if __name__ == "__main__":
    main()
