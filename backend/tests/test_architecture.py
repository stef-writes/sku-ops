"""
Architecture tests: DDD bounded context boundary validation.

Rules enforced here:
  1. shared/ kernel imports nothing from bounded contexts (it must be dependency-free).
  2. Domain layer files (*/domain/*.py) import nothing from infrastructure or api layers.
  3. No context imports another context's api layer (only composition roots do that).
  4. Cross-context infrastructure imports are frozen at a known set — no new ones allowed.
     (Existing violations are pre-DDD coupling that will be cleaned up incrementally.)
"""
import ast
from pathlib import Path

BACKEND = Path(__file__).parent.parent

BOUNDED_CONTEXTS = frozenset({
    "identity", "catalog", "inventory", "operations",
    "purchasing", "finance", "documents", "assistant", "reports",
})

# Files that compose routers/schemas from all contexts — architecture rules don't apply.
# shared/api/deps.py is a FastAPI dependency-injection composition helper: it wires
# identity.application auth functions into Annotated type aliases used across all routes.
# It is a composition root by function even though it lives in shared/api/.
COMPOSITION_ROOTS = frozenset({"server.py", "api/__init__.py", "full_schema.py", "shared/api/deps.py"})

# ── Known cross-context infrastructure violations (pre-DDD coupling to clean up) ──────────
# Each entry is "relative/path/from/backend:imported.module".
# The test fails if NEW violations appear; add entries here only as a last resort.
# All pre-DDD violations resolved — contexts now communicate via application-layer query services.
KNOWN_CROSS_INFRA_VIOLATIONS: frozenset[str] = frozenset()


def _get_context(path: Path) -> str | None:
    parts = path.relative_to(BACKEND).parts
    return parts[0] if parts[0] in BOUNDED_CONTEXTS else None


def _from_imports(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    return [
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    ]


def _all_backend_py_files(skip_roots: bool = True):
    for py_file in BACKEND.rglob("*.py"):
        rel = py_file.relative_to(BACKEND)
        if "__pycache__" in rel.parts or rel.parts[0] == "tests":
            continue
        if skip_roots and str(rel) in COMPOSITION_ROOTS:
            continue
        yield py_file


# ── Test 1: shared kernel is dependency-free ─────────────────────────────────────────────

def test_shared_kernel_has_no_context_imports():
    """shared/ must not import from any bounded context.

    Exception: shared/api/deps.py is a FastAPI dependency-injection composition
    helper that wires identity auth into Annotated type aliases used across all
    routes.  It is a composition root by function (same category as server.py)
    even though it lives in shared/api/ for import-path convenience.
    """
    violations = []
    for py_file in (BACKEND / "shared").rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        rel = py_file.relative_to(BACKEND)
        if str(rel) in COMPOSITION_ROOTS:
            continue
        for module in _from_imports(py_file):
            if module.split(".")[0] in BOUNDED_CONTEXTS:
                violations.append(f"  {rel}: from {module}")
    assert not violations, (
        "shared/ imports from bounded contexts:\n" + "\n".join(violations)
    )


# ── Test 2: domain layer purity ──────────────────────────────────────────────────────────

def test_domain_layer_does_not_import_infrastructure_or_api():
    """Domain models must be pure — no infrastructure or HTTP coupling."""
    violations = []
    for py_file in _all_backend_py_files():
        rel = py_file.relative_to(BACKEND)
        parts = rel.parts
        if len(parts) < 2 or parts[1] != "domain":
            continue
        for module in _from_imports(py_file):
            seg = module.split(".")
            # Importing own or other context's infrastructure/api is a violation
            if len(seg) >= 2 and seg[1] in ("infrastructure", "api"):
                violations.append(f"  {rel}: from {module}")
    assert not violations, (
        "Domain files import from infrastructure or api layers:\n"
        + "\n".join(violations)
    )


# ── Test 3: no cross-context api imports ─────────────────────────────────────────────────

def test_no_cross_context_api_imports():
    """Contexts must not import each other's api layer (only composition roots do that)."""
    violations = []
    for py_file in _all_backend_py_files(skip_roots=True):
        rel = py_file.relative_to(BACKEND)
        home_ctx = _get_context(py_file)
        if home_ctx is None:
            continue
        for module in _from_imports(py_file):
            seg = module.split(".")
            if (
                len(seg) >= 2
                and seg[0] in BOUNDED_CONTEXTS
                and seg[1] == "api"
                and seg[0] != home_ctx
            ):
                violations.append(f"  {rel}: from {module}")
    assert not violations, (
        "Cross-context api imports (only composition roots may do this):\n"
        + "\n".join(violations)
    )


# ── Test 4: cross-infra violations are frozen ────────────────────────────────────────────

def test_cross_context_infrastructure_violations_not_growing():
    """
    Detect cross-context infrastructure imports.

    Existing violations are documented in KNOWN_CROSS_INFRA_VIOLATIONS above.
    This test fails if NEW violations are introduced, preventing regression.
    Remove entries from KNOWN_CROSS_INFRA_VIOLATIONS as coupling is cleaned up.
    """
    found = set()
    for py_file in _all_backend_py_files(skip_roots=True):
        rel = py_file.relative_to(BACKEND)
        str_rel = str(rel)
        home_ctx = _get_context(py_file)
        if home_ctx is None:
            continue
        for module in _from_imports(py_file):
            seg = module.split(".")
            if (
                len(seg) >= 2
                and seg[0] in BOUNDED_CONTEXTS
                and seg[1] == "infrastructure"
                and seg[0] != home_ctx
            ):
                # Normalise: "path/to/file.py:imported.module.top_two_parts"
                imported_key = ".".join(seg[:3]) if len(seg) >= 3 else module
                found.add(f"{str_rel}:{imported_key}")

    new_violations = found - KNOWN_CROSS_INFRA_VIOLATIONS
    assert not new_violations, (
        "NEW cross-context infrastructure imports detected (not in known list):\n"
        + "\n".join(f"  {v}" for v in sorted(new_violations))
        + "\n\nFix the coupling, or add to KNOWN_CROSS_INFRA_VIOLATIONS with a comment."
    )
