"""Exact-match checks for Aadhaar, PAN, and date of birth.

Aadhaar numbers are often masked in extracted documents (e.g.
"XXXX XXXX 4321"). MatchResult is tri-state because a masked value can be
inconclusive rather than a clean match/mismatch.
"""

from dataclasses import dataclass
from datetime import date
from enum import Enum

MIN_OVERLAPPING_DIGITS = 4


class MatchResult(str, Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass
class ExactCheckOutcome:
    result: MatchResult
    reason: str | None = None


def _normalize(value: str) -> str:
    return "".join(ch for ch in value.upper() if ch.isdigit() or ch == "X")


def _is_masked(value: str) -> bool:
    return "X" in value


def aadhaar_match(golden: str | None, candidate: str | None) -> ExactCheckOutcome:
    if not golden or not candidate:
        return ExactCheckOutcome(MatchResult.INCONCLUSIVE, "missing_value")

    g = _normalize(golden)
    c = _normalize(candidate)

    if not _is_masked(g) and not _is_masked(c):
        return (
            ExactCheckOutcome(MatchResult.MATCH)
            if g == c
            else ExactCheckOutcome(MatchResult.MISMATCH, "digits_differ")
        )

    if _is_masked(g) != _is_masked(c):
        masked, unmasked = (g, c) if _is_masked(g) else (c, g)
        trailing_digits = "".join(ch for ch in masked if ch != "X")
        if not trailing_digits:
            return ExactCheckOutcome(MatchResult.INCONCLUSIVE, "no_unmasked_digits")
        if len(trailing_digits) < MIN_OVERLAPPING_DIGITS:
            return ExactCheckOutcome(MatchResult.INCONCLUSIVE, "insufficient_unmasked_digits")
        if len(unmasked) < len(trailing_digits):
            return ExactCheckOutcome(MatchResult.INCONCLUSIVE, "unmasked_value_too_short")
        suffix = unmasked[-len(trailing_digits):]
        return (
            ExactCheckOutcome(MatchResult.MATCH)
            if suffix == trailing_digits
            else ExactCheckOutcome(MatchResult.MISMATCH, "suffix_digits_differ")
        )

    # Both masked: compare position-wise where both sides have a digit.
    if len(g) != len(c):
        return ExactCheckOutcome(MatchResult.INCONCLUSIVE, "masked_length_mismatch")

    overlapping = 0
    for gd, cd in zip(g, c):
        if gd == "X" or cd == "X":
            continue
        overlapping += 1
        if gd != cd:
            return ExactCheckOutcome(MatchResult.MISMATCH, "overlapping_digits_differ")

    if overlapping < MIN_OVERLAPPING_DIGITS:
        return ExactCheckOutcome(MatchResult.INCONCLUSIVE, "insufficient_unmasked_digits")

    return ExactCheckOutcome(MatchResult.MATCH)


def pan_match(golden: str | None, candidate: str | None) -> ExactCheckOutcome:
    if not golden or not candidate:
        return ExactCheckOutcome(MatchResult.INCONCLUSIVE, "missing_value")
    g = golden.strip().upper()
    c = candidate.strip().upper()
    return (
        ExactCheckOutcome(MatchResult.MATCH)
        if g == c
        else ExactCheckOutcome(MatchResult.MISMATCH, "pan_differs")
    )


def dob_match(golden: date | None, candidate: date | None) -> ExactCheckOutcome:
    if golden is None or candidate is None:
        return ExactCheckOutcome(MatchResult.INCONCLUSIVE, "missing_value")
    return (
        ExactCheckOutcome(MatchResult.MATCH)
        if golden == candidate
        else ExactCheckOutcome(MatchResult.MISMATCH, "dob_differs")
    )
