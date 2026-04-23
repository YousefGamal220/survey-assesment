"""Field-type registry.

Adding a field type = one subclass + one registry entry. No migration needed:
type-specific state lives in `Field.config` (JSONB).
"""

from __future__ import annotations

import re
from datetime import date as _date
from typing import Any

from rest_framework.exceptions import ValidationError


class FieldType:
    name: str = ""

    def validate_config(self, config: dict) -> None:
        """Raise ValidationError if `config` is shaped wrong for this type.

        Subclasses should call `super().validate_config(config)` so generic
        keys (`sensitive`) are checked uniformly.
        """
        _check_sensitive_flag(config)

    def validate_answer(self, value: Any, config: dict) -> None:
        """Raise ValidationError if `value` isn't a valid answer under `config`."""


def is_sensitive(config: dict | None) -> bool:
    """True if this field's config marks it as sensitive → answers get encrypted."""
    return bool((config or {}).get("sensitive"))


class _ShortText(FieldType):
    name = "short_text"
    _max = 255

    def validate_config(self, config: dict) -> None:
        super().validate_config(config)
        _check_length_bounds(config, hard_max=self._max)
        _check_optional_regex(config)

    def validate_answer(self, value: Any, config: dict) -> None:
        _check_string_answer(value, config, hard_max=self._max)


class _LongText(_ShortText):
    name = "long_text"
    _max = 10_000


class _Number(FieldType):
    name = "number"

    def validate_config(self, config: dict) -> None:
        super().validate_config(config)
        for key in ("min", "max"):
            if key in config and not isinstance(config[key], (int, float)):
                raise ValidationError({key: "must be a number"})
        if "integer_only" in config and not isinstance(config["integer_only"], bool):
            raise ValidationError({"integer_only": "must be a boolean"})
        if "min" in config and "max" in config and config["min"] > config["max"]:
            raise ValidationError({"max": "must be >= min"})

    def validate_answer(self, value: Any, config: dict) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValidationError("must be a number")
        if config.get("integer_only") and not isinstance(value, int):
            raise ValidationError("must be an integer")
        if "min" in config and value < config["min"]:
            raise ValidationError(f"must be >= {config['min']}")
        if "max" in config and value > config["max"]:
            raise ValidationError(f"must be <= {config['max']}")


class _Date(FieldType):
    name = "date"

    def validate_config(self, config: dict) -> None:
        super().validate_config(config)

    def validate_answer(self, value: Any, config: dict) -> None:
        if not isinstance(value, str):
            raise ValidationError("must be an ISO-8601 date string")
        try:
            _date.fromisoformat(value)
        except ValueError as exc:
            raise ValidationError("invalid ISO-8601 date") from exc


class _Email(FieldType):
    name = "email"
    _rx = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    def validate_config(self, config: dict) -> None:
        super().validate_config(config)

    def validate_answer(self, value: Any, config: dict) -> None:
        if not isinstance(value, str) or not self._rx.match(value):
            raise ValidationError("invalid email")


class _SingleChoice(FieldType):
    name = "single_choice"
    multi = False

    def validate_config(self, config: dict) -> None:
        super().validate_config(config)
        choices = config.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValidationError({"choices": "required non-empty list"})
        values: set[Any] = set()
        for c in choices:
            if not isinstance(c, dict) or "value" not in c or "label" not in c:
                raise ValidationError({"choices": "each entry needs `value` and `label`"})
            if c["value"] in values:
                raise ValidationError({"choices": "duplicate value"})
            values.add(c["value"])

    def validate_answer(self, value: Any, config: dict) -> None:
        allowed = {c["value"] for c in config["choices"]}
        if not self.multi and isinstance(value, list):
            raise ValidationError("single_choice answer must not be a list")
        if self.multi and not isinstance(value, list):
            raise ValidationError("multi_choice answer must be a list")
        values = value if self.multi else [value]
        for v in values:
            if v not in allowed:
                raise ValidationError(f"invalid choice: {v!r}")


class _MultiChoice(_SingleChoice):
    name = "multi_choice"
    multi = True


def _check_sensitive_flag(config: dict) -> None:
    """Optional `sensitive: bool` flag — answers for sensitive fields are
    encrypted at rest by apps.responses. Only the shape is validated here;
    encryption is opt-in at submit time."""
    if "sensitive" in config and not isinstance(config["sensitive"], bool):
        raise ValidationError({"sensitive": "must be a boolean"})


def _check_length_bounds(config: dict, hard_max: int) -> None:
    for key in ("min_length", "max_length"):
        if key in config and (not isinstance(config[key], int) or config[key] < 0):
            raise ValidationError({key: "must be a non-negative integer"})
    if config.get("max_length", 0) > hard_max:
        raise ValidationError({"max_length": f"must be <= {hard_max}"})
    if (
        "min_length" in config
        and "max_length" in config
        and config["min_length"] > config["max_length"]
    ):
        raise ValidationError({"max_length": "must be >= min_length"})


def _check_optional_regex(config: dict) -> None:
    if "regex" in config:
        try:
            re.compile(config["regex"])
        except re.error as exc:
            raise ValidationError({"regex": f"invalid pattern: {exc}"}) from exc


def _check_string_answer(value: Any, config: dict, hard_max: int) -> None:
    if not isinstance(value, str):
        raise ValidationError("must be a string")
    if len(value) > min(config.get("max_length", hard_max), hard_max):
        raise ValidationError("too long")
    if len(value) < config.get("min_length", 0):
        raise ValidationError("too short")
    if "regex" in config and not re.fullmatch(config["regex"], value):
        raise ValidationError("does not match required pattern")


_FIELD_TYPES: dict[str, FieldType] = {
    ft.name: ft
    for ft in (
        _ShortText(),
        _LongText(),
        _Number(),
        _Date(),
        _Email(),
        _SingleChoice(),
        _MultiChoice(),
    )
}


def get_field_type(name: str) -> FieldType:
    ft = _FIELD_TYPES.get(name)
    if ft is None:
        raise ValidationError({"type": f"unknown field type: {name!r}"})
    return ft


def all_field_type_names() -> list[str]:
    return list(_FIELD_TYPES.keys())
