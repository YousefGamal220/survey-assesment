"""Conditional-logic engine.

JSON DSL:
    {"all": [leaf|node, ...]}      # AND
    {"any": [leaf|node, ...]}      # OR
    {"not": leaf|node}             # NOT
    {"field": "<key>", "op": "<op>", "value": <literal|list>}   # leaf

Ops: eq, neq, in, not_in, gt, lt, gte, lte, contains, is_set, is_not_set.
`None` as a rule always evaluates True.
Missing field is treated as unset (falsey under most ops; is_set is False).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from rest_framework.exceptions import ValidationError

_SENTINEL: Any = object()


def evaluate(rule: dict | None, answers: dict[str, Any]) -> bool:
    if rule is None:
        return True
    if not isinstance(rule, dict):
        raise ValidationError("rule must be a dict or null")

    if "all" in rule:
        return all(evaluate(child, answers) for child in _as_list(rule["all"]))
    if "any" in rule:
        return any(evaluate(child, answers) for child in _as_list(rule["any"]))
    if "not" in rule:
        return not evaluate(rule["not"], answers)
    if "field" in rule and "op" in rule:
        return _leaf(rule, answers)
    raise ValidationError(f"rule must have one of: all, any, not, field+op; got {sorted(rule)}")


def _as_list(v: Any) -> list:
    if not isinstance(v, list):
        raise ValidationError("combiner value must be a list")
    return v


def _leaf(rule: dict, answers: dict[str, Any]) -> bool:
    key = rule["field"]
    op = rule["op"]
    actual = answers.get(key, _SENTINEL)
    target = rule.get("value")
    handler = _OPS.get(op)
    if handler is None:
        raise ValidationError(f"unknown op: {op!r}")
    return handler(actual, target)


def _is_set(actual: Any, _target: Any) -> bool:
    return actual is not _SENTINEL and actual is not None and actual != ""


def _is_not_set(actual: Any, target: Any) -> bool:
    return not _is_set(actual, target)


def _eq(actual: Any, target: Any) -> bool:
    if actual is _SENTINEL:
        return False
    return bool(actual == target)


def _neq(actual: Any, target: Any) -> bool:
    if actual is _SENTINEL:
        return True
    return bool(actual != target)


def _in(actual: Any, target: Any) -> bool:
    if not isinstance(target, list):
        raise ValidationError("`in` requires a list value")
    if actual is _SENTINEL:
        return False
    return actual in target


def _not_in(actual: Any, target: Any) -> bool:
    if not isinstance(target, list):
        raise ValidationError("`not_in` requires a list value")
    if actual is _SENTINEL:
        return True
    return actual not in target


def _gt(actual: Any, target: Any) -> bool:
    return _cmp(actual, target, lambda a, b: a > b)


def _lt(actual: Any, target: Any) -> bool:
    return _cmp(actual, target, lambda a, b: a < b)


def _gte(actual: Any, target: Any) -> bool:
    return _cmp(actual, target, lambda a, b: a >= b)


def _lte(actual: Any, target: Any) -> bool:
    return _cmp(actual, target, lambda a, b: a <= b)


def _cmp(actual: Any, target: Any, fn: Any) -> bool:
    if actual is _SENTINEL:
        return False
    a, b = _coerce_compare(actual, target)
    return bool(fn(a, b))


def _coerce_compare(actual: Any, target: Any) -> tuple[Any, Any]:
    if isinstance(actual, bool) or isinstance(target, bool):
        raise ValidationError("ordering ops don't support booleans")
    if isinstance(actual, (int, float)) and isinstance(target, (int, float)):
        return actual, target
    if isinstance(actual, str) and isinstance(target, str):
        try:
            return date.fromisoformat(actual), date.fromisoformat(target)
        except ValueError as exc:
            raise ValidationError("ordering ops require numbers or ISO-8601 dates") from exc
    raise ValidationError("ordering ops require numbers or ISO-8601 dates")


def _contains(actual: Any, target: Any) -> bool:
    if actual is _SENTINEL or actual is None:
        return False
    if isinstance(actual, str):
        return isinstance(target, str) and target in actual
    if isinstance(actual, list):
        return target in actual
    return False


_OPS = {
    "eq": _eq,
    "neq": _neq,
    "in": _in,
    "not_in": _not_in,
    "gt": _gt,
    "lt": _lt,
    "gte": _gte,
    "lte": _lte,
    "contains": _contains,
    "is_set": _is_set,
    "is_not_set": _is_not_set,
}
