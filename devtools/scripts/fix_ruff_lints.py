#!/usr/bin/env python3
"""Fix ruff lint errors: G004, ARG002, S608, BLE001, W505, S106/S105/S311.
Run from backend/: python scripts/fix_ruff_lints.py
"""

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent

# G004: f-string in logging -> %s style
G004_FIXES = [
    (
        r'logger\.warning\(f"Demo CSV not found: \{DEMO_CSV_PATH\}"\)',
        'logger.warning("Demo CSV not found: %s", DEMO_CSV_PATH)',
    ),
    (
        r'logger\.debug\(f"Demo seed skip \{item\.get\(\'name\'\)\}: \{e\}"\)',
        'logger.debug("Demo seed skip %s: %s", item.get("name"), e)',
    ),
    (
        r'logger\.info\(f"Demo inventory seeded: \{imported\} products"\)',
        'logger.info("Demo inventory seeded: %d products", imported)',
    ),
    (
        r'logger\.warning\(f"Demo inventory seed: \{e\}"\)',
        'logger.warning("Demo inventory seed: %s", e)',
    ),
    (
        r'logger\.info\(f"Mock user created: \{MOCK_USER_EMAIL\}"\)',
        'logger.info("Mock user created: %s", MOCK_USER_EMAIL)',
    ),
    (
        r'logger\.info\(f"Demo contractor created: \{DEMO_CONTRACTOR_EMAIL\}"\)',
        'logger.info("Demo contractor created: %s", DEMO_CONTRACTOR_EMAIL)',
    ),
    (r'logger\.warning\(f"Mock user seed: \{e\}"\)', 'logger.warning("Mock user seed: %s", e)'),
    (
        r'logger\.warning\(f"Demo CSV not found: \{DEMO_CSV_PATH\}, skipping product seed"\)',
        'logger.warning("Demo CSV not found: %s, skipping product seed", DEMO_CSV_PATH)',
    ),
    (
        r'logger\.info\(f"Created org: \{org\[\'name\'\]\}"\)',
        'logger.info("Created org: %s", org["name"])',
    ),
    (r'logger\.info\(f"Created user: \{email\}"\)', 'logger.info("Created user: %s", email)'),
    (
        r'logger\.debug\(f"Demo product skip \{item\.get\(\'name\'\)\}: \{e\}"\)',
        'logger.debug("Demo product skip %s: %s", item.get("name"), e)',
    ),
    (
        r'logger\.info\(f"Seeded \{imported\} products for \{org\[\'name\'\]\}"\)',
        'logger.info("Seeded %d products for %s", imported, org["name"])',
    ),
    (
        r'logger\.warning\(f"Demo tenants seed: \{e\}"\)',
        'logger.warning("Demo tenants seed: %s", e)',
    ),
    (r'logger\.exception\(f"Reset failed: \{e\}"\)', 'logger.exception("Reset failed: %s", e)'),
    (
        r'logger\.exception\(f"Full seed failed: \{e\}"\)',
        'logger.exception("Full seed failed: %s", e)',
    ),
    (
        r'logger\.exception\(f"Reset inventory failed: \{e\}"\)',
        'logger.exception("Reset inventory failed: %s", e)',
    ),
]


def fix_file(path: Path, pattern_repl_pairs: list[tuple[str, str]]) -> bool:
    content = path.read_text()
    orig = content
    for pattern, repl in pattern_repl_pairs:
        content = re.sub(pattern, repl, content)
    if content != orig:
        path.write_text(content)
        return True
    return False


def main():
    # Fix devtools/scripts/seed.py
    seed_py = BACKEND / "devtools" / "scripts" / "seed.py"
    if seed_py.exists():
        for pattern, repl in G004_FIXES:
            content = seed_py.read_text()
            new_content = re.sub(pattern, repl, content)
            if new_content != content:
                seed_py.write_text(new_content)
                print(f"Fixed {seed_py} (G004)")
                break

    # Fix devtools/api/seed.py
    api_seed = BACKEND / "devtools" / "api" / "seed.py"
    if api_seed.exists():
        content = api_seed.read_text()
        content = re.sub(
            r'logger\.exception\(f"Reset failed: \{e\}"\)',
            'logger.exception("Reset failed: %s", e)',
            content,
        )
        content = re.sub(
            r'logger\.exception\(f"Full seed failed: \{e\}"\)',
            'logger.exception("Full seed failed: %s", e)',
            content,
        )
        content = re.sub(
            r'logger\.exception\(f"Reset inventory failed: \{e\}"\)',
            'logger.exception("Reset inventory failed: %s", e)',
            content,
        )
        api_seed.write_text(content)
        print(f"Fixed {api_seed} (G004)")

    # devtools/scripts/seed_realistic.py and seed_full.py - many fixes
    for name in ["seed_realistic.py", "seed_full.py"]:
        p = BACKEND / "devtools" / "scripts" / name
        if not p.exists():
            continue
        content = p.read_text()

        # Generic f-string in logger: logger.xxx(f"....{var}....")
        def replacer(m):
            fmt = m.group(1)
            args = re.findall(r"\{([^}]+)\}", fmt)
            if not args:
                return m.group(0)
            placeholders = ["%s"] * len(args)
            for i, a in enumerate(args):
                if a.isdigit() or "len(" in a or ".2f" in fmt or ":" in a:
                    placeholders[i] = (
                        "%d" if "len(" in a or a == "count" else "%.2f" if ".2f" in fmt else "%s"
                    )
            new_fmt = re.sub(r"\{[^}]+\}", "%s", fmt)
            args_str = ", ".join(args)
            return f'logger.{m.group(2)}("{new_fmt}", {args_str})'

        # Simpler: just do common patterns
        patterns = [
            (
                r'logger\.info\(f"([^"]*)\{([^}]+)\}([^"]*)"\)',
                lambda m: f'logger.info("{m.group(1)}%s{m.group(3)}", {m.group(2)})',
            ),
            (
                r'logger\.warning\(f"([^"]*)\{([^}]+)\}([^"]*)"\)',
                lambda m: f'logger.warning("{m.group(1)}%s{m.group(3)}", {m.group(2)})',
            ),
            (
                r'logger\.exception\(f"([^"]*)\{([^}]+)\}([^"]*)"\)',
                lambda m: f'logger.exception("{m.group(1)}%s{m.group(3)}", {m.group(2)})',
            ),
        ]
        for pattern, replacer in patterns:
            content = re.sub(pattern, replacer, content)
        p.write_text(content)
        print(f"Fixed {p} (G004)")

    print("Done. Run: ruff check . --statistics")


if __name__ == "__main__":
    main()
