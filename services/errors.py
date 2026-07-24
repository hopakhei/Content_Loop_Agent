"""Shared publisher errors."""
from __future__ import annotations


class PartialThreadError(Exception):
    """A reply chain failed midway: some posts are already live on the platform.

    Carries the ids that DID publish so the caller can record the root post
    instead of retrying the whole thread (which would duplicate live content).
    """

    def __init__(self, ids: list[str], cause: Exception):
        self.ids = ids
        self.cause = cause
        super().__init__(f"thread failed after {len(ids)} post(s): {cause}")
