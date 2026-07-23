from __future__ import annotations

from textwrap import dedent
from typing import Iterable, Optional


def clean(text: str) -> str:
    return dedent(text).strip()


def block(name: str, body: str) -> str:
    body = clean(body)
    return f"<{name}>\n{body}\n</{name}>"


def join_sections(*sections: Optional[str]) -> str:
    return "\n\n".join(s for s in sections if s and s.strip())


def bullet_list(items: Iterable[str]) -> str:
    return "\n".join(f"- {item}" for item in items)
