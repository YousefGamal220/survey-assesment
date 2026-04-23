from __future__ import annotations

import pytest
from rest_framework.exceptions import ValidationError

from apps.surveys.logic import evaluate


class TestCombiners:
    def test_none_rule_is_true(self):
        assert evaluate(None, {}) is True

    def test_empty_all_is_true(self):
        assert evaluate({"all": []}, {}) is True

    def test_empty_any_is_false(self):
        assert evaluate({"any": []}, {}) is False

    def test_all_requires_every_branch(self):
        answers = {"a": 1, "b": 2}
        assert (
            evaluate(
                {
                    "all": [
                        {"field": "a", "op": "eq", "value": 1},
                        {"field": "b", "op": "eq", "value": 2},
                    ]
                },
                answers,
            )
            is True
        )
        assert (
            evaluate(
                {
                    "all": [
                        {"field": "a", "op": "eq", "value": 1},
                        {"field": "b", "op": "eq", "value": 99},
                    ]
                },
                answers,
            )
            is False
        )

    def test_any_requires_at_least_one(self):
        answers = {"a": 1, "b": 2}
        assert (
            evaluate(
                {
                    "any": [
                        {"field": "a", "op": "eq", "value": 99},
                        {"field": "b", "op": "eq", "value": 2},
                    ]
                },
                answers,
            )
            is True
        )

    def test_not_inverts(self):
        assert evaluate({"not": {"field": "a", "op": "eq", "value": 1}}, {"a": 1}) is False
        assert evaluate({"not": {"field": "a", "op": "eq", "value": 1}}, {"a": 2}) is True

    def test_nesting(self):
        rule = {
            "all": [
                {"field": "a", "op": "eq", "value": 1},
                {
                    "any": [
                        {"field": "b", "op": "eq", "value": "x"},
                        {"field": "c", "op": "gt", "value": 0},
                    ]
                },
            ]
        }
        assert evaluate(rule, {"a": 1, "b": "x", "c": -1}) is True
        assert evaluate(rule, {"a": 1, "b": "y", "c": 1}) is True
        assert evaluate(rule, {"a": 2, "b": "x", "c": 1}) is False

    def test_invalid_shape_raises(self):
        with pytest.raises(ValidationError):
            evaluate({"bogus": []}, {})


class TestEqNeq:
    def test_eq(self):
        assert evaluate({"field": "a", "op": "eq", "value": 1}, {"a": 1}) is True
        assert evaluate({"field": "a", "op": "eq", "value": 1}, {"a": 2}) is False

    def test_eq_missing_field_is_false(self):
        assert evaluate({"field": "a", "op": "eq", "value": None}, {}) is False

    def test_neq_missing_field_is_true(self):
        assert evaluate({"field": "a", "op": "neq", "value": 1}, {}) is True


class TestInNotIn:
    def test_in(self):
        assert evaluate({"field": "a", "op": "in", "value": [1, 2]}, {"a": 1}) is True
        assert evaluate({"field": "a", "op": "in", "value": [1, 2]}, {"a": 3}) is False

    def test_in_requires_list(self):
        with pytest.raises(ValidationError):
            evaluate({"field": "a", "op": "in", "value": "x"}, {"a": "x"})

    def test_not_in_missing_is_true(self):
        assert evaluate({"field": "a", "op": "not_in", "value": [1]}, {}) is True


class TestOrdering:
    def test_gt_lt_gte_lte_numbers(self):
        a = {"a": 5}
        assert evaluate({"field": "a", "op": "gt", "value": 4}, a) is True
        assert evaluate({"field": "a", "op": "lt", "value": 6}, a) is True
        assert evaluate({"field": "a", "op": "gte", "value": 5}, a) is True
        assert evaluate({"field": "a", "op": "lte", "value": 5}, a) is True
        assert evaluate({"field": "a", "op": "gt", "value": 5}, a) is False

    def test_date_compare(self):
        assert (
            evaluate(
                {"field": "d", "op": "gt", "value": "2026-01-01"},
                {"d": "2026-06-01"},
            )
            is True
        )

    def test_incomparable_types_raise(self):
        with pytest.raises(ValidationError):
            evaluate({"field": "a", "op": "gt", "value": 1}, {"a": "x"})


class TestContainsSet:
    def test_contains_string(self):
        assert evaluate({"field": "s", "op": "contains", "value": "lo"}, {"s": "hello"}) is True
        assert evaluate({"field": "s", "op": "contains", "value": "zz"}, {"s": "hello"}) is False

    def test_contains_list(self):
        assert evaluate({"field": "l", "op": "contains", "value": "a"}, {"l": ["a", "b"]}) is True

    def test_is_set_vs_not_set(self):
        assert evaluate({"field": "a", "op": "is_set"}, {"a": "x"}) is True
        assert evaluate({"field": "a", "op": "is_set"}, {"a": ""}) is False
        assert evaluate({"field": "a", "op": "is_set"}, {}) is False
        assert evaluate({"field": "a", "op": "is_not_set"}, {}) is True


class TestUnknownOp:
    def test_unknown_op_raises(self):
        with pytest.raises(ValidationError):
            evaluate({"field": "a", "op": "wat", "value": 1}, {"a": 1})
