"""
Trigger expression evaluator.

Tag configs express their firing conditions as small declarative strings, for
example::

    "pattern_score >= 3 AND pattern_hard_count >= 1"
    "rule_inferred == true OR flexibility_score >= 2"
    "shift_result == shifted_ok"

This module parses and evaluates those expressions against a dictionary of
derived signals. It is intentionally *not* backed by :func:`eval` - only the
documented grammar below is accepted, so a malformed or hostile config can
never execute arbitrary code.

Grammar::

    expression  := clause (("AND" | "OR") clause)*
    clause      := signal operator literal
    operator    := ">=" | "<=" | "==" | "!=" | ">" | "<"
    literal     := number | "true" | "false" | bare_word

``AND`` binds tighter than ``OR``, matching conventional boolean precedence.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List, Mapping

logger = logging.getLogger(__name__)

# Longest operators first so ">=" is not mis-read as ">".
_OPERATORS: Dict[str, Callable[[Any, Any], bool]] = {
    ">=": lambda left, right: left >= right,
    "<=": lambda left, right: left <= right,
    "==": lambda left, right: left == right,
    "!=": lambda left, right: left != right,
    ">": lambda left, right: left > right,
    "<": lambda left, right: left < right,
}

_CLAUSE_PATTERN = re.compile(
    r"^\s*(?P<signal>[A-Za-z_][A-Za-z0-9_]*)"
    r"\s*(?P<operator>>=|<=|==|!=|>|<)\s*"
    r"(?P<literal>.+?)\s*$"
)

_OR_SPLIT = re.compile(r"\s+OR\s+", re.IGNORECASE)
_AND_SPLIT = re.compile(r"\s+AND\s+", re.IGNORECASE)

_BOOLEAN_LITERALS = {"true": True, "false": False}


class TriggerSyntaxError(ValueError):
    """Raised when a trigger string does not match the supported grammar."""


def parse_literal(raw: str) -> Any:
    """Convert the right-hand side of a clause into a Python value."""
    text = raw.strip().strip("'\"")
    lowered = text.lower()

    if lowered in _BOOLEAN_LITERALS:
        return _BOOLEAN_LITERALS[lowered]
    if lowered in {"none", "null"}:
        return None

    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass

    # Bare word, e.g. the sort-task outcome "shifted_ok".
    return text


def _coerce_for_comparison(left: Any, right: Any) -> tuple[Any, Any]:
    """Align operand types so comparisons behave predictably.

    Signals arrive from JSON and from Python scoring code, so a value may be
    ``True`` where the config says ``1``, or ``"3"`` where it says ``3``.
    """
    if isinstance(right, bool):
        return bool(left), right
    if isinstance(left, bool) and isinstance(right, (int, float)):
        return int(left), right

    if isinstance(right, (int, float)) and not isinstance(left, (int, float)):
        try:
            return float(left), float(right)
        except (TypeError, ValueError):
            return left, right

    if isinstance(left, (int, float)) and isinstance(right, str):
        return str(left), right

    return left, right


def evaluate_clause(clause: str, signals: Mapping[str, Any]) -> bool:
    """Evaluate a single ``signal op literal`` comparison."""
    match = _CLAUSE_PATTERN.match(clause)
    if not match:
        raise TriggerSyntaxError(f"Malformed clause: {clause!r}")

    signal_name = match.group("signal")
    operator = match.group("operator")
    expected = parse_literal(match.group("literal"))

    if signal_name not in signals:
        # An absent signal simply means the condition is not met. This keeps
        # engines free to omit signals that do not apply to a given grade.
        logger.debug("Signal %r absent while evaluating %r", signal_name, clause)
        return False

    actual = signals[signal_name]
    if actual is None:
        return expected is None if operator == "==" else False

    left, right = _coerce_for_comparison(actual, expected)

    try:
        return _OPERATORS[operator](left, right)
    except TypeError:
        logger.warning(
            "Cannot compare %r %s %r in clause %r", left, operator, right, clause
        )
        return False


def evaluate(trigger: str, signals: Mapping[str, Any]) -> bool:
    """Evaluate a full trigger expression.

    Returns ``False`` (rather than raising) when the expression is malformed,
    so that one bad config entry cannot take down an entire assessment.
    """
    if not trigger or not trigger.strip():
        return False

    try:
        # OR is the loosest binding, so split on it first.
        for or_branch in _OR_SPLIT.split(trigger):
            and_clauses: List[str] = _AND_SPLIT.split(or_branch)
            if all(evaluate_clause(clause, signals) for clause in and_clauses):
                return True
        return False
    except TriggerSyntaxError as exc:
        logger.error("Invalid trigger %r: %s", trigger, exc)
        return False


def referenced_signals(trigger: str) -> List[str]:
    """List every signal name a trigger depends on.

    Used by the config loader to verify that a test declares all the signals
    its own triggers reference.
    """
    names: List[str] = []
    if not trigger:
        return names

    for or_branch in _OR_SPLIT.split(trigger):
        for clause in _AND_SPLIT.split(or_branch):
            match = _CLAUSE_PATTERN.match(clause)
            if match:
                name = match.group("signal")
                if name not in names:
                    names.append(name)
    return names
