"""Per-request tenant context. Backed by `contextvars` so it is safe under
async, threads, and Celery workers (each task sets+resets the context).
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.organizations.models import Organization


_current_org_var: ContextVar[Organization | None] = ContextVar(
    "survey_current_organization", default=None
)


def current_organization() -> Organization | None:
    return _current_org_var.get()


def set_current_organization(org: Organization | None) -> Token:
    return _current_org_var.set(org)


def reset_current_organization(token: Token) -> None:
    _current_org_var.reset(token)
