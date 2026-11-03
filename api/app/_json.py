"""Tiny helpers shared by providers."""

from __future__ import annotations


def truncate(text: str, limit: int = 200) -> str:
    return text if len(text) <= limit else text[:limit] + "..."
