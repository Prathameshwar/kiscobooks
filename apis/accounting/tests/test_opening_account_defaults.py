"""Opening automation uses separate equity offset and zero-net chunk clearing accounts."""

from accounting.schemas.setup import TemplateSelection
from accounting.seeds.templates import HIGH_PRIORITY
from accounting.tasks.templates import content


def test_opening_defaults_have_distinct_balance_sheet_purposes():
    defaults = {row[0]: row for row in HIGH_PRIORITY}
    assert defaults["OPENING_BALANCE_OFFSET"][2:] == ("CAPITAL", "GENERAL")
    assert defaults["MIGRATION_CLEARING"][2:] == ("CURRENT_ASSETS", "GENERAL")
    _, _, accounts, _ = content(TemplateSelection(business_accounts=True))
    assert sum(row[0] == "OPENING_BALANCE_OFFSET" for row in accounts) == 1
    assert sum(row[0] == "MIGRATION_CLEARING" for row in accounts) == 1
