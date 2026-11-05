"""Product custom-value readiness; descriptive values never select business rules."""

from billing_platform.custom_fields import validate_stored_values
from billing_platform.errors import ValidationFailedError

from catalog.tasks.product_commands import ProductWork
from catalog.tasks.products import native


async def requirements(work: ProductWork) -> list[str]:
    assert work.item is not None
    missing = []
    for row in (work.family, work.item):
        context = await work.access.context(type(row))
        values = native(row, context)
        readable = context.readable(values)
        readable |= {key.removeprefix("custom_field:") for key in readable}
        currencies = frozenset(
            {
                context.company.base_currency,
                *(value for value in (context.company.reporting_currency,) if value),
            }
        )
        for definition in context.definitions:
            try:
                validate_stored_values(
                    context.definitions,
                    values=row.custom_fields or {},
                    native_values=values,
                    readable_fields=readable,
                    currencies=currencies,
                    keys=frozenset({definition.key}),
                )
            except ValidationFailedError:
                missing.append(f"{context.native.entity_type}.custom_fields.{definition.key}")
    return missing
