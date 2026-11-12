"""The decision logic from the flow chart, as one pure function.

    Exists?  no  -> NOT_FOUND
             yes -> Correct claim?  yes -> SUPPORTED
                                    no  -> Related?  yes -> CONTRADICTS
                                                     no  -> AMBIGUOUS
"""
from __future__ import annotations

from enum import Enum


class Status(str, Enum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTS = "CONTRADICTS"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"


def decide_status(exists: bool, matches_claim: bool | None = None, related: bool | None = None) -> Status:
    if not exists:
        return Status.NOT_FOUND          # the claim check is never needed (or run) for a citation that does not exist
    if matches_claim is None:
        raise ValueError("matches_claim is required when the citation exists")
    if matches_claim:
        return Status.SUPPORTED
    if related is None:
        raise ValueError("related is required when the claim does not match")
    return Status.CONTRADICTS if related else Status.AMBIGUOUS
