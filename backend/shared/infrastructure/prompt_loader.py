"""Load versioned .md prompt files co-located with their owning modules."""
from functools import cache, lru_cache
from pathlib import Path


@cache
def load_prompt(anchor: str, filename: str) -> str:
    """Return the contents of *filename* resolved relative to *anchor*.

    Usage::

        SYSTEM_PROMPT = load_prompt(__file__, "prompt.md")
    """
    return (Path(anchor).resolve().parent / filename).read_text(encoding="utf-8")
