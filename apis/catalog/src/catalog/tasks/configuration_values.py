"""Applicability and explanation of already-authorized native configuration values."""

from typing import Literal

from billing_platform.errors import ConflictError

from catalog.domain.configuration import OptionSetting
from catalog.schemas.configuration import (
    ConfigurationOrigin,
    ConfigurationSetting,
    DraftInput,
)

GOODS_OPTIONS = frozenset({"manufacturer", "measured_units"})
GOODS_PROFILES = frozenset(
    {"inventory_template_revision", "handling_revision", "identifier_profile"}
)


def applicable_layer(body: DraftInput, *, service: bool, shared: bool) -> DraftInput:
    if not service:
        return body
    values = body.model_dump()
    for key in GOODS_OPTIONS:
        mode = getattr(body.options, key + "_mode")
        if not shared and mode not in {"INHERIT", "DISABLED"}:
            raise ConflictError("goods-only options cannot be configured for a service scope")
        if shared:
            values["options"][key + "_mode"] = "INHERIT"
            values["options"][key + "_default"] = None
    for key in GOODS_PROFILES:
        if not shared and getattr(body.profiles, key + "_id") is not None:
            raise ConflictError("services cannot select physical tracking/handling profiles")
        if shared:
            values["profiles"][key + "_mode"] = "INHERIT"
            values["profiles"][key + "_id"] = None
    if not shared and body.pricing.mrp_mode not in {"INHERIT", "DISABLED"}:
        raise ConflictError("service scopes cannot configure product MRP")
    if shared:
        values["pricing"]["mrp_mode"] = "INHERIT"
    return DraftInput.model_validate(values)


def option_setting(
    field: str,
    selected: OptionSetting,
    baseline: OptionSetting,
    baseline_origin: ConfigurationOrigin,
    layers: list[tuple[OptionSetting, ConfigurationOrigin]],
    *,
    applicable: bool = True,
) -> ConfigurationSetting:
    candidates = [(baseline, baseline_origin), *layers]
    if selected.mode in {"REQUIRED", "DISABLED"}:
        origins = [origin for value, origin in candidates if value.mode == selected.mode]
    else:
        origins = [origin for value, origin in candidates if value.mode != "INHERIT"][-1:]
    reason: Literal["goods_only", "service_only", "hard_requirement", "hard_prohibition"] | None = (
        None
    )
    if not applicable:
        reason = "goods_only"
    elif selected.mode == "REQUIRED":
        reason = "hard_requirement"
    elif selected.mode == "DISABLED":
        reason = "hard_prohibition"
    return ConfigurationSetting(
        field=field,
        origins=origins,
        applicable=applicable,
        overrideable=applicable and selected.mode == "OPTIONAL",
        reason=reason,
    )
