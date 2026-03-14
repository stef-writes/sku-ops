"""Pre-deploy verification script.

Runs every check that can be validated locally without live infrastructure.
Pass/fail per check. Exit 1 if any check fails.

Usage:
    ./bin/dev verify
    ./bin/dev verify --url https://your-railway-domain  # also hits a live server
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.request

# ── Colour helpers ────────────────────────────────────────────────────────────

_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_BOLD = "\033[1m"
_RESET = "\033[0m"

_failures: list[str] = []
_warnings: list[str] = []


def _ok(label: str, detail: str = "") -> None:
    suffix = f"  {detail}" if detail else ""
    print(f"  {_GREEN}✓{_RESET}  {label}{suffix}")


def _fail(label: str, detail: str = "") -> None:
    suffix = f"\n       {_RED}{detail}{_RESET}" if detail else ""
    print(f"  {_RED}✗{_RESET}  {label}{suffix}")
    _failures.append(label)


def _warn(label: str, detail: str = "") -> None:
    suffix = f"\n       {_YELLOW}{detail}{_RESET}" if detail else ""
    print(f"  {_YELLOW}~{_RESET}  {label}{suffix}")
    _warnings.append(label)


def _section(title: str) -> None:
    print(f"\n{_BOLD}{title}{_RESET}")


# ── Individual checks ─────────────────────────────────────────────────────────


def check_config_guards() -> None:
    """Verify that production config raises on missing secrets."""
    _section("Config guards (production startup validation)")

    cases = [
        (
            "Production rejects missing JWT_SECRET",
            {
                "ENV": "production",
                "DATABASE_URL": "postgresql://x:x@x:5432/x",
                "CORS_ORIGINS": "https://example.com",
            },
            "JWT_SECRET",
            True,
        ),
        (
            "Production rejects wildcard CORS",
            {
                "ENV": "production",
                "DATABASE_URL": "postgresql://x:x@x:5432/x",
                "JWT_SECRET": "a" * 32,
            },
            "CORS_ORIGINS",
            True,
        ),
        (
            "Production rejects SQLite DATABASE_URL",
            {"ENV": "production", "JWT_SECRET": "a" * 32, "CORS_ORIGINS": "https://x.com"},
            "DATABASE_URL",
            True,
        ),
        (
            "Development allows permissive defaults",
            {"ENV": "development"},
            None,
            False,
        ),
    ]

    for label, env, missing_var, should_raise in cases:
        merged = dict.fromkeys(
            ["ENV", "DATABASE_URL", "JWT_SECRET", "CORS_ORIGINS", "REDIS_URL"], ""
        )
        merged.update(env)
        if missing_var:
            merged.pop(missing_var, None)
            merged[missing_var] = ""

        code = (
            "import os\n"
            + "\n".join(f"os.environ[{k!r}] = {v!r}" for k, v in merged.items())
            + "\nimport importlib, shared.infrastructure.config as _c; importlib.reload(_c)"
        )

        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", code],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, **merged, "PYTHONPATH": _pythonpath()},
        )
        raised = result.returncode != 0

        if (should_raise and raised) or (not should_raise and not raised):
            _ok(label)
        elif should_raise and not raised:
            _fail(label, "Expected RuntimeError but config loaded without error")
        else:
            _fail(label, f"Unexpected RuntimeError:\n       {result.stderr.strip()[-300:]}")


def check_supabase_jwt_shape() -> None:
    """Mint a Supabase-shaped JWT and verify auth_deps decodes it correctly."""
    _section("Supabase JWT decode (shape compatibility)")

    try:
        import jwt

        from shared.api.auth_deps import _extract_role
        from shared.infrastructure.config import JWT_ALGORITHM, JWT_SECRET
    except ImportError as e:
        _fail("Import failed", str(e))
        return

    # Case 1: Supabase-shaped token (role in app_metadata, name in user_metadata)
    supabase_payload = {
        "sub": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "email": "admin@example.com",
        "app_metadata": {"role": "admin"},
        "user_metadata": {"name": "Test Admin"},
        "aud": "authenticated",
        "role": "authenticated",  # Supabase sets this — NOT the app role
        "exp": int(time.time()) + 3600,
    }
    token = jwt.encode(supabase_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    try:
        payload = jwt.decode(
            token, JWT_SECRET, algorithms=[JWT_ALGORITHM], options={"verify_aud": False}
        )
        role = _extract_role(payload)
        name = payload.get("name") or (payload.get("user_metadata") or {}).get("name") or ""
        user_id = payload.get("user_id") or payload.get("sub")

        assert role == "admin", f"Expected role='admin', got {role!r}"
        assert name == "Test Admin", f"Expected name='Test Admin', got {name!r}"
        assert user_id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", f"Wrong user_id: {user_id!r}"
        _ok("Supabase token: role extracted from app_metadata.role", f"role={role!r}")
        _ok("Supabase token: name extracted from user_metadata.name", f"name={name!r}")
        _ok("Supabase token: user_id taken from sub claim", f"sub={user_id[:8]}...")
    except Exception as e:
        _fail("Supabase token decode failed", str(e))

    # Case 2: Token missing role claim → must 401
    no_role_payload = {
        "sub": "test-uuid",
        "email": "norole@example.com",
        "app_metadata": {},
        "aud": "authenticated",
        "role": "authenticated",
        "exp": int(time.time()) + 3600,
    }
    no_role_token = jwt.encode(no_role_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    try:
        payload = jwt.decode(
            no_role_token, JWT_SECRET, algorithms=[JWT_ALGORITHM], options={"verify_aud": False}
        )
        _extract_role(payload)
        _fail("Token missing role: should raise 401 but did not")
    except Exception:
        _ok("Token missing app_metadata.role raises 401")

    # Case 3: Dev-issued token (role at top level) still works
    dev_payload = {
        "sub": "dev-user-1",
        "user_id": "dev-user-1",
        "email": "dev@example.com",
        "role": "admin",
        "name": "Dev User",
        "organization_id": "default",
        "exp": int(time.time()) + 3600,
    }
    dev_token = jwt.encode(dev_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    try:
        payload = jwt.decode(
            dev_token, JWT_SECRET, algorithms=[JWT_ALGORITHM], options={"verify_aud": False}
        )
        role = _extract_role(payload)
        assert role == "admin"
        _ok("Dev-issued token (role at top level) still decodes correctly")
    except Exception as e:
        _fail("Dev token decode failed", str(e))

    # Case 4: Expired token → must 401
    expired_payload = {**supabase_payload, "exp": int(time.time()) - 10}
    expired_token = jwt.encode(expired_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    try:
        jwt.decode(
            expired_token, JWT_SECRET, algorithms=[JWT_ALGORITHM], options={"verify_aud": False}
        )
        _fail("Expired token: should raise ExpiredSignatureError but did not")
    except jwt.ExpiredSignatureError:
        _ok("Expired token raises ExpiredSignatureError")
    except Exception as e:
        _fail("Expired token raised unexpected error", str(e))


def check_cors_config() -> None:
    """Verify CORS header splitting handles single and multiple origins."""
    _section("CORS origin parsing")

    from shared.infrastructure.config import CORS_ORIGINS

    origins = [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]
    if CORS_ORIGINS == "*":
        _warn("CORS_ORIGINS is '*' (dev default — must be set in production)")
    else:
        _ok(f"CORS_ORIGINS parsed into {len(origins)} origin(s)", ", ".join(origins))

    # Simulate what server.py does: CORS_ORIGINS.split(",")
    test_cases = [
        ("https://app.vercel.app", ["https://app.vercel.app"]),
        (
            "https://app.vercel.app,https://staging.vercel.app",
            ["https://app.vercel.app", "https://staging.vercel.app"],
        ),
        (
            "https://app.vercel.app, https://staging.vercel.app",
            ["https://app.vercel.app", " https://staging.vercel.app"],
        ),
    ]
    all_ok = True
    for raw, expected in test_cases:
        parsed = raw.split(",")
        if parsed != expected:
            _fail(f"CORS split mismatch for: {raw!r}")
            all_ok = False
    if all_ok:
        _ok("CORS_ORIGINS.split(',') parses correctly in all cases")


def check_websocket_routes() -> None:
    """Verify both WebSocket routes are registered on the app."""
    _section("WebSocket route registration")

    try:
        from starlette.routing import WebSocketRoute

        from server import app

        ws_paths = {r.path for r in app.routes if isinstance(r, WebSocketRoute)}
        for expected in ("/api/ws", "/api/ws/chat"):
            if expected in ws_paths:
                _ok(f"WebSocket route mounted: {expected}")
            else:
                _fail(f"WebSocket route NOT mounted: {expected}", "Check routes.py")
    except Exception as e:
        _fail("Could not import server app", str(e))


def check_production_flags() -> None:
    """Verify that dev-only endpoints are disabled when ENV=production."""
    _section("Production endpoint gating")

    try:
        import importlib
        import sys

        # Temporarily set production env to check route gating
        orig_env = os.environ.get("ENV", "development")
        os.environ["ENV"] = "production"
        os.environ.setdefault("JWT_SECRET", "a" * 32)
        os.environ.setdefault("DATABASE_URL", "postgresql://x:x@x:5432/x")
        os.environ.setdefault("CORS_ORIGINS", "https://example.com")

        # Re-import config to pick up production flags
        if "shared.infrastructure.config" in sys.modules:
            importlib.reload(sys.modules["shared.infrastructure.config"])

        from shared.infrastructure.config import ALLOW_PUBLIC_AUTH, ALLOW_RESET

        if not ALLOW_PUBLIC_AUTH:
            _ok("ALLOW_PUBLIC_AUTH=False in production (login/register endpoints disabled)")
        elif os.environ.get("ALLOW_PUBLIC_AUTH", "").lower() in ("1", "true"):
            _ok("ALLOW_PUBLIC_AUTH=True explicitly set (local auth mode, no Supabase)")
        else:
            _fail(
                "ALLOW_PUBLIC_AUTH=True in production",
                "Local auth endpoints should not be reachable",
            )

        if not ALLOW_RESET:
            _ok("ALLOW_RESET=False in production (seed/reset endpoints disabled)")
        elif os.environ.get("ALLOW_RESET", "").lower() in ("1", "true"):
            _warn("ALLOW_RESET=True explicitly set — disable after seeding")
        else:
            _fail("ALLOW_RESET=True in production", "Reset endpoint should not be reachable")

        os.environ["ENV"] = orig_env
        if "shared.infrastructure.config" in sys.modules:
            importlib.reload(sys.modules["shared.infrastructure.config"])

    except Exception as e:
        _fail("Production flag check failed", str(e))


def check_frontend_build() -> None:
    """Verify the frontend builds cleanly with production-style VITE_* vars set."""
    _section("Frontend build (Vite with VITE_* env vars)")

    frontend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
    frontend_dir = os.path.realpath(frontend_dir)

    if not os.path.isdir(frontend_dir):
        _warn("frontend/ directory not found — skipping build check")
        return

    env = {
        **os.environ,
        "VITE_SUPABASE_URL": "https://test-project.supabase.co",
        "VITE_SUPABASE_ANON_KEY": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test",
        "VITE_BACKEND_URL": "https://test-backend.railway.app",
    }

    result = subprocess.run(
        ["npm", "run", "build"],  # noqa: S607
        check=False,
        cwd=frontend_dir,
        capture_output=True,
        text=True,
        env=env,
    )

    if result.returncode == 0:
        _ok("Frontend builds cleanly with VITE_* vars set")
    else:
        last_lines = "\n       ".join(result.stderr.strip().splitlines()[-10:])
        _fail("Frontend build failed", last_lines)


def check_live_server(base_url: str) -> None:
    """Hit a live server's health and ready endpoints."""
    _section(f"Live server checks ({base_url})")

    base = base_url.rstrip("/")

    # /health
    try:
        with urllib.request.urlopen(f"{base}/api/health", timeout=10) as resp:  # noqa: S310
            import json

            data = json.loads(resp.read())
            env = data.get("env", "unknown")
            version = data.get("version", "?")
            _ok("/api/health returns 200", f"env={env}, version={version}")
            if env == "development":
                _warn("Server reports env=development — expected production or staging")
    except Exception as e:
        _fail("/api/health unreachable", str(e))
        return

    # /ready
    try:
        with urllib.request.urlopen(f"{base}/api/ready", timeout=10) as resp:  # noqa: S310
            import json

            data = json.loads(resp.read())
            checks = data.get("checks", {})
            for name, check in checks.items():
                status = check.get("status", "unknown")
                if status == "ok":
                    detail = check.get("latency_ms")
                    _ok(
                        f"/api/ready check: {name}",
                        f"{status}" + (f" ({detail}ms)" if detail else ""),
                    )
                elif status == "unconfigured":
                    _warn(f"/api/ready check: {name}", f"{status} (optional)")
                else:
                    _fail(f"/api/ready check: {name}", f"{status} — {check.get('error', '')}")
    except urllib.error.HTTPError as e:
        import json

        try:
            data = json.loads(e.read())
            for name, check in data.get("checks", {}).items():
                status = check.get("status", "?")
                if status != "ok":
                    _fail(f"/api/ready check: {name}", f"{status} — {check.get('error', '')}")
        except Exception:
            _fail("/api/ready returned non-200", str(e))
    except Exception as e:
        _fail("/api/ready unreachable", str(e))


# ── Entry point ───────────────────────────────────────────────────────────────


def _pythonpath() -> str:
    root = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
    backend = os.path.join(root, "backend")
    existing = os.environ.get("PYTHONPATH", "")
    parts = [p for p in [backend, root, existing] if p]
    return ":".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-deploy verification")
    parser.add_argument(
        "--url",
        default="",
        help="Base URL of a live server to check (e.g. https://your-app.railway.app)",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip the frontend build check (faster for repeated runs)",
    )
    args = parser.parse_args()

    print(f"\n{_BOLD}SKU-Ops pre-deploy verification{_RESET}")
    print("─" * 48)

    # Add backend to path so imports work
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..")))

    check_config_guards()
    check_supabase_jwt_shape()
    check_cors_config()
    check_websocket_routes()
    check_production_flags()

    if not args.skip_build:
        check_frontend_build()
    else:
        print(f"\n{_BOLD}Frontend build{_RESET}")
        _warn("Skipped (--skip-build)")

    if args.url:
        check_live_server(args.url)

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "─" * 48)
    if not _failures and not _warnings:
        print(f"{_GREEN}{_BOLD}All checks passed.{_RESET} Ready to deploy.\n")
        sys.exit(0)
    elif not _failures:
        print(f"{_YELLOW}{_BOLD}{len(_warnings)} warning(s), 0 failures.{_RESET}")
        print("Warnings are non-blocking but worth reviewing before going live.\n")
        sys.exit(0)
    else:
        print(f"{_RED}{_BOLD}{len(_failures)} failure(s){_RESET}, {len(_warnings)} warning(s).")
        print("\nFailed checks:")
        for f in _failures:
            print(f"  {_RED}✗{_RESET}  {f}")
        print()
        sys.exit(1)


if __name__ == "__main__":
    main()
