from __future__ import annotations

import pytest
from rest_framework.exceptions import ValidationError

from apps.surveys.field_types import get_field_type


class TestRegistry:
    def test_unknown_type_raises(self):
        with pytest.raises(ValidationError):
            get_field_type("not_a_real_type")

    def test_known_types_are_registered(self):
        for name in [
            "short_text",
            "long_text",
            "number",
            "date",
            "email",
            "single_choice",
            "multi_choice",
        ]:
            ft = get_field_type(name)
            assert ft.name == name


class TestSensitiveFlag:
    """The `sensitive: bool` flag lives on every field type — it signals that
    answers should be encrypted at rest by the Responses sub-project."""

    def test_accepted_on_every_type(self):
        configs = {
            "short_text": {"sensitive": True},
            "long_text": {"sensitive": True},
            "number": {"sensitive": True},
            "date": {"sensitive": True},
            "email": {"sensitive": True},
            "single_choice": {
                "sensitive": True,
                "choices": [{"value": "a", "label": "A"}],
            },
            "multi_choice": {
                "sensitive": False,
                "choices": [{"value": "a", "label": "A"}],
            },
        }
        for name, cfg in configs.items():
            get_field_type(name).validate_config(cfg)  # must not raise

    def test_non_bool_rejected(self):
        with pytest.raises(ValidationError):
            get_field_type("short_text").validate_config({"sensitive": "yes"})


class TestShortText:
    ft = get_field_type("short_text")

    def test_config_regex_must_compile(self):
        with pytest.raises(ValidationError):
            self.ft.validate_config({"regex": "[invalid"})

    def test_answer_length_bounds(self):
        self.ft.validate_answer("hi", {"min_length": 1, "max_length": 5})
        with pytest.raises(ValidationError):
            self.ft.validate_answer("", {"min_length": 1})
        with pytest.raises(ValidationError):
            self.ft.validate_answer("x" * 10, {"max_length": 5})

    def test_answer_regex(self):
        self.ft.validate_answer("abc123", {"regex": r"[a-z]+\d+"})
        with pytest.raises(ValidationError):
            self.ft.validate_answer("no digits", {"regex": r"[a-z]+\d+"})

    def test_answer_must_be_string(self):
        with pytest.raises(ValidationError):
            self.ft.validate_answer(42, {})


class TestNumber:
    ft = get_field_type("number")

    def test_config_min_must_be_leq_max(self):
        with pytest.raises(ValidationError):
            self.ft.validate_config({"min": 10, "max": 5})

    def test_integer_only(self):
        self.ft.validate_answer(3, {"integer_only": True})
        with pytest.raises(ValidationError):
            self.ft.validate_answer(3.1, {"integer_only": True})

    def test_bounds(self):
        self.ft.validate_answer(5, {"min": 0, "max": 10})
        with pytest.raises(ValidationError):
            self.ft.validate_answer(-1, {"min": 0})
        with pytest.raises(ValidationError):
            self.ft.validate_answer(11, {"max": 10})

    def test_rejects_bools_and_strings(self):
        with pytest.raises(ValidationError):
            self.ft.validate_answer(True, {})
        with pytest.raises(ValidationError):
            self.ft.validate_answer("5", {})


class TestDate:
    ft = get_field_type("date")

    def test_accepts_iso(self):
        self.ft.validate_answer("2026-04-21", {})

    def test_rejects_garbage(self):
        with pytest.raises(ValidationError):
            self.ft.validate_answer("yesterday", {})
        with pytest.raises(ValidationError):
            self.ft.validate_answer(20260421, {})


class TestEmail:
    ft = get_field_type("email")

    def test_accepts(self):
        self.ft.validate_answer("x@y.z", {})

    def test_rejects(self):
        for bad in ["no at", "a@b", "@b.c", "a@.c", ""]:
            with pytest.raises(ValidationError):
                self.ft.validate_answer(bad, {})


class TestChoice:
    single = get_field_type("single_choice")
    multi = get_field_type("multi_choice")
    cfg = {"choices": [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}]}

    def test_config_requires_non_empty_choices(self):
        with pytest.raises(ValidationError):
            self.single.validate_config({})
        with pytest.raises(ValidationError):
            self.single.validate_config({"choices": []})

    def test_config_rejects_duplicate_values(self):
        with pytest.raises(ValidationError):
            self.single.validate_config(
                {"choices": [{"value": "a", "label": "A"}, {"value": "a", "label": "B"}]}
            )

    def test_single_accepts_single_value(self):
        self.single.validate_answer("a", self.cfg)
        with pytest.raises(ValidationError):
            self.single.validate_answer(["a"], self.cfg)
        with pytest.raises(ValidationError):
            self.single.validate_answer("c", self.cfg)

    def test_multi_accepts_list(self):
        self.multi.validate_answer(["a", "b"], self.cfg)
        with pytest.raises(ValidationError):
            self.multi.validate_answer("a", self.cfg)
        with pytest.raises(ValidationError):
            self.multi.validate_answer(["a", "c"], self.cfg)
