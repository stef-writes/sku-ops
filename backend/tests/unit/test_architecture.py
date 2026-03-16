"""
Architecture tests: DDD bounded context boundary validation.

Rules enforced here:
  1. shared/ must not import from bounded contexts (except composition roots).
  2. Domain layer files (*/domain/*.py) import nothing from infrastructure or api layers.
  3. No context imports another context's api layer (only composition roots do that).
  4. Cross-context infrastructure imports are frozen at a known set — no new ones allowed.
  5. API route files must not import repos directly.
  6. Cross-context domain imports are disallowed.
"""

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent.parent

BOUNDED_CONTEXTS = frozenset(
    {
        "catalog",
        "inventory",
        "operations",
        "purchasing",
        "finance",
        "documents",
        "assistant",
        "reports",
    }
)

COMPOSITION_ROOTS = frozenset(
    {
        "server.py",
        "routes.py",
        "startup.py",
        "scheduler.py",
        "shared/infrastructure/full_schema.py",
    }
)

# All pre-DDD violations resolved — contexts communicate via application-layer facades.
KNOWN_CROSS_INFRA_VIOLATIONS: frozenset[str] = frozenset()


def _get_context(path: Path) -> str | None:
    parts = path.relative_to(BACKEND).parts
    return parts[0] if parts[0] in BOUNDED_CONTEXTS else None


def _is_type_checking_block(node: ast.If) -> bool:
    """Return True if this If node is `if TYPE_CHECKING:` or `if typing.TYPE_CHECKING:`."""
    test = node.test
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _from_imports(path: Path) -> list[str]:
    """Return all runtime `from X import Y` module names, skipping TYPE_CHECKING blocks."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []

    type_checking_nodes: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_type_checking_block(node):
            for child in ast.walk(node):
                type_checking_nodes.add(id(child))

    return [
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module and id(node) not in type_checking_nodes
    ]


def _all_backend_py_files(skip_roots: bool = True):
    for py_file in BACKEND.rglob("*.py"):
        rel = py_file.relative_to(BACKEND)
        if "__pycache__" in rel.parts or rel.parts[0] == "tests":
            continue
        if skip_roots and str(rel) in COMPOSITION_ROOTS:
            continue
        yield py_file


# ── Test 1: shared/ is dependency-free from bounded contexts ──────────────────


def test_shared_has_no_context_imports():
    """shared/ must not import from any bounded context.

    shared/infrastructure/full_schema.py is a composition root (aggregates
    all context schemas) and is exempted.
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
    assert not violations, "shared/ imports from bounded contexts:\n" + "\n".join(violations)


# ── Test 2: domain layer purity ──────────────────────────────────────────────


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
            if len(seg) >= 2 and seg[1] in ("infrastructure", "api"):
                violations.append(f"  {rel}: from {module}")
    assert not violations, "Domain files import from infrastructure or api layers:\n" + "\n".join(
        violations
    )


# ── Test 3: no cross-context api imports ─────────────────────────────────────


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
        "Cross-context api imports (only composition roots may do this):\n" + "\n".join(violations)
    )


# ── Test 4: cross-infra violations are frozen ────────────────────────────────


def test_cross_context_infrastructure_violations_not_growing():
    """
    Detect cross-context infrastructure imports.

    Existing violations are documented in KNOWN_CROSS_INFRA_VIOLATIONS above.
    This test fails if NEW violations are introduced, preventing regression.
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
                imported_key = ".".join(seg[:3]) if len(seg) >= 3 else module
                found.add(f"{str_rel}:{imported_key}")

    new_violations = found - KNOWN_CROSS_INFRA_VIOLATIONS
    assert not new_violations, (
        "NEW cross-context infrastructure imports detected (not in known list):\n"
        + "\n".join(f"  {v}" for v in sorted(new_violations))
        + "\n\nFix the coupling, or add to KNOWN_CROSS_INFRA_VIOLATIONS with a comment."
    )


# ── Test 5: API routes must not import repos directly ─────────────────────────


def test_api_layer_does_not_import_repos():
    """API route files must delegate to the application layer, never import repos."""
    violations = []
    for py_file in _all_backend_py_files():
        rel = py_file.relative_to(BACKEND)
        parts = rel.parts
        if len(parts) < 2 or parts[1] != "api" or parts[0] not in BOUNDED_CONTEXTS:
            continue
        for module in _from_imports(py_file):
            seg = module.split(".")
            if len(seg) >= 2 and seg[-1].endswith("_repo") and "infrastructure" in seg:
                violations.append(f"  {rel}: from {module}")
    assert not violations, (
        "API files import repos directly (should go through application layer):\n"
        + "\n".join(violations)
    )


# ── Test 6: cross-context domain imports ──────────────────────────────────────


def test_no_cross_context_domain_imports():
    """Contexts must not import another context's domain layer directly.

    Cross-context data should flow through application-layer facades and typed DTOs.
    """
    violations = []
    for py_file in _all_backend_py_files(skip_roots=True):
        rel = py_file.relative_to(BACKEND)
        home_ctx = _get_context(py_file)
        if home_ctx is None:
            continue
        layer = rel.parts[1] if len(rel.parts) >= 2 else None
        if layer == "domain":
            continue
        for module in _from_imports(py_file):
            seg = module.split(".")
            if (
                len(seg) >= 2
                and seg[0] in BOUNDED_CONTEXTS
                and seg[1] == "domain"
                and seg[0] != home_ctx
            ):
                violations.append(f"  {rel}: from {module}")
    assert not violations, (
        "Cross-context domain imports (use application facades instead):\n" + "\n".join(violations)
    )
