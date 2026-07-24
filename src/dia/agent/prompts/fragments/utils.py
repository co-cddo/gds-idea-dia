from __future__ import annotations

from collections.abc import Iterable
from textwrap import dedent


def clean(text: str) -> str:
    return dedent(text).strip()


def block(name: str, body: str) -> str:
    body = clean(body)
    return f"<{name}>\n{body}\n</{name}>"


def join_sections(*sections: str | None) -> str:
    return "\n\n".join(s for s in sections if s and s.strip())


def bullet_list(items: Iterable[str]) -> str:
    return "\n".join(f"- {item}" for item in items)
