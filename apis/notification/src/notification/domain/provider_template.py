"""Compare approved positional WhatsApp text templates with the local immutable version."""

from __future__ import annotations

import re
from typing import Any


def matches(body: str, payload: dict[str, Any] | None, remote: object) -> bool:
    if not isinstance(remote, list) or len(remote) > 12:
        return False
    local: dict[tuple[str, str], list[str]] = {}
    for component in (payload or {}).get("components", []):
        local[(component["type"], component.get("index", ""))] = [
            item["variable"] for item in component["parameters"]
        ]
    if (payload or {}).get("template_parameters"):
        local[("body", "")] = payload["template_parameters"] if payload else []
    expected: dict[tuple[str, str], int] = {}
    provider_body = None
    for component in remote:
        if not isinstance(component, dict):
            return False
        kind = component.get("type")
        if kind in ("HEADER", "BODY"):
            if kind == "HEADER" and component.get("format", "TEXT") != "TEXT":
                return False  # Media requires the separately gated artifact handoff.
            text = component.get("text", "")
            if not isinstance(text, str):
                return False
            expressions = re.findall(r"{{\s*(.*?)\s*}}", text)
            if any(
                not value.isascii() or not value.isdigit() or len(value) > 3
                for value in expressions
            ):
                return False  # Named provider parameters need a distinct typed contract.
            positions = {int(value) for value in expressions}
            if positions and (min(positions) < 1 or max(positions) > 100):
                return False
            if positions and positions != set(range(1, max(positions) + 1)):
                return False
            expected[(kind.lower(), "")] = max(positions, default=0)
            if kind == "BODY":
                provider_body = text
        elif kind == "BUTTONS":
            buttons = component.get("buttons")
            if not isinstance(buttons, list):
                return False
            for index, button in enumerate(buttons):
                if not isinstance(button, dict):
                    return False
                url = button.get("url", "")
                if not isinstance(url, str):
                    return False
                parameters = re.findall(r"{{\s*(.*?)\s*}}", url)
                if parameters and (button.get("type") != "URL" or parameters != ["1"]):
                    return False
                expected[("button", str(index))] = len(parameters)
        elif kind != "FOOTER":
            return False
    if provider_body is None:
        return False
    if any(len(local.get(key, [])) != count for key, count in expected.items()):
        return False
    if any(key not in expected for key in local):
        return False
    parameters = local.get(("body", ""), [])
    resolved = re.sub(
        r"{{\s*([0-9]+)\s*}}",
        lambda match: "{{" + parameters[int(match[1]) - 1] + "}}",
        provider_body,
    )
    canonical = re.sub(r"{{\s*([a-zA-Z][a-zA-Z0-9_]*)\s*}}", r"{{\1}}", body)
    return resolved == canonical
