"""Restricted template rendering: named variables only, no expression language."""

from __future__ import annotations

import html
import re
from collections.abc import Mapping
from typing import Any, Final

from billing_platform.errors import ValidationFailedError

_VARIABLE: Final = re.compile(r"{{\s*([a-zA-Z][a-zA-Z0-9_]*)\s*}}")
_ANY_EXPRESSION: Final = re.compile(r"{{(.*?)}}", re.DOTALL)


def render(source: str, values: Mapping[str, Any], *, max_bytes: int = 1_000_000) -> str:
    for expression in _ANY_EXPRESSION.findall(source):
        if not re.fullmatch(r"\s*[a-zA-Z][a-zA-Z0-9_]*\s*", expression):
            raise ValidationFailedError("template expressions may only name variables")
    missing = sorted(set(_VARIABLE.findall(source)) - values.keys())
    if missing:
        raise ValidationFailedError(
            "template variables are missing", fields=dict.fromkeys(missing, "required")
        )
    rendered = _VARIABLE.sub(lambda match: str(values[match.group(1)]), source)
    if len(rendered.encode()) > max_bytes:
        raise ValidationFailedError("rendered notification exceeds the channel limit")
    return rendered


def render_html(source: str, values: Mapping[str, Any]) -> str:
    """Escape recipient data while retaining administrator-authored HTML markup."""
    return render(
        source, {key: html.escape(str(value), quote=True) for key, value in values.items()}
    )
