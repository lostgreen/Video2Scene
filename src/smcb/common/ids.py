"""Stable identifier helpers."""

from uuid import uuid4


def new_id(prefix: str) -> str:
    """Create a filesystem-safe identifier with a readable prefix."""
    return f"{prefix}_{uuid4().hex}"
