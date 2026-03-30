"""
Deterministic condition evaluator — four supported patterns.

Pattern matching order (important — null check before equality):
  1. Null check:         path == null  /  path != null
  2. State check:        path in [...]  /  path not in [...]
  3. Equality:           path == 'string'  /  path != 'string'
  4. Numeric comparison: path op path  /  path op number

If no pattern matches, returns None → caller routes to LLM fallback.
"""

from __future__ import annotations
import re
from typing import Any

from app.eval.resolver import resolve

# -- Compiled regexes --

_NULL_CHECK = re.compile(
    r"^([\w.]+)\s*(==|!=)\s*null\s*$", re.IGNORECASE
)
_STATE_CHECK = re.compile(
    r"^([\w.]+)\s+(not\s+in|in)\s+\[([^\]]+)\]\s*$", re.IGNORECASE
)
_EQUALITY = re.compile(
    r"^([\w.]+)\s*(==|!=)\s*['\"](.+?)['\"]\s*$"
)
_NUMERIC = re.compile(
    r"^([\w.]+)\s*(<=|>=|!=|==|<|>)\s*([\w.]+|-?\d+(?:\.\d+)?)\s*$"
)


def can_evaluate(condition: str) -> bool:
    """Return True if the condition matches any of the four supported patterns."""
    c = condition.strip()
    return bool(
        _NULL_CHECK.match(c)
        or _STATE_CHECK.match(c)
        or _EQUALITY.match(c)
        or _NUMERIC.match(c)
    )


def evaluate(condition: str, context: dict) -> bool | None:
    """Evaluate a condition against an evaluation context.

    Returns:
        True  — condition holds
        False — condition violated
        None  — pattern not recognised; route to LLM fallback
    """
    c = condition.strip()

    # 1. Null check
    m = _NULL_CHECK.match(c)
    if m:
        path, op = m.group(1), m.group(2)
        val = resolve(path, context)
        return (val is None) if op == "==" else (val is not None)

    # 2. State / membership check
    m = _STATE_CHECK.match(c)
    if m:
        path, op_raw, items_str = m.group(1), m.group(2), m.group(3)
        val = resolve(path, context)
        items = [s.strip().strip("'\"") for s in items_str.split(",")]
        in_list = str(val) in items if val is not None else False
        return (not in_list) if "not" in op_raw.lower() else in_list

    # 3. Equality with quoted string literal
    m = _EQUALITY.match(c)
    if m:
        path, op, literal = m.group(1), m.group(2), m.group(3)
        val = resolve(path, context)
        match = str(val) == literal if val is not None else (literal == "None")
        return match if op == "==" else not match

    # 4. Numeric comparison (both sides may be dot-paths or literal numbers)
    m = _NUMERIC.match(c)
    if m:
        lhs_path, op, rhs_token = m.group(1), m.group(2), m.group(3)
        lhs = resolve(lhs_path, context)

        rhs: Any = resolve(rhs_token, context)
        if rhs is None:
            try:
                rhs = float(rhs_token)
            except ValueError:
                return None

        if lhs is None:
            return None

        try:
            lhs_f = float(lhs)
            rhs_f = float(rhs)
        except (ValueError, TypeError):
            return None

        ops = {
            "<=": lhs_f <= rhs_f,
            ">=": lhs_f >= rhs_f,
            "<": lhs_f < rhs_f,
            ">": lhs_f > rhs_f,
            "==": lhs_f == rhs_f,
            "!=": lhs_f != rhs_f,
        }
        return ops[op]

    return None  # No pattern matched → LLM fallback
