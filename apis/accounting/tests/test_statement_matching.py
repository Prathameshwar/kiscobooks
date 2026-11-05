"""B43 exact partial/grouped preflight with no cash posting."""

from dataclasses import replace
from decimal import Decimal

import pytest
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7

from accounting.domain.statement_matching import MatchPart, MatchSource, preview


def sources():
    tenant, company, account = uuid7(), uuid7(), uuid7()
    bank = MatchSource(uuid7(), tenant, company, account, "INR", "CREDIT", Decimal("100"))
    first = MatchSource(uuid7(), tenant, company, account, "INR", "CREDIT", Decimal("40"))
    second = MatchSource(uuid7(), tenant, company, account, "INR", "CREDIT", Decimal("80"))
    return bank, first, second


def test_grouped_and_partial_matches_conserve_both_residuals():
    bank, first, second = sources()
    result = preview(
        (bank,),
        (first, second),
        (MatchPart(bank.id, first.id, Decimal(40)), MatchPart(bank.id, second.id, Decimal(60))),
    )
    assert result.statement_residuals[bank.id] == Decimal(0)
    assert result.instrument_residuals[first.id] == Decimal(0)
    assert result.instrument_residuals[second.id] == Decimal(20)


def test_overallocation_duplicate_pair_and_cross_company_are_refused():
    bank, first, second = sources()
    with pytest.raises(ValidationFailedError, match="residual"):
        preview((bank,), (first,), (MatchPart(bank.id, first.id, Decimal(41)),))
    with pytest.raises(ValidationFailedError, match="distinct"):
        preview(
            (bank,), (first,),
            (MatchPart(bank.id, first.id, Decimal(10)), MatchPart(bank.id, first.id, Decimal(10))),
        )
    with pytest.raises(ValidationFailedError, match="crosses"):
        preview(
            (bank,), (replace(second, company_id=uuid7()),),
            (MatchPart(bank.id, second.id, Decimal(1)),),
        )
    with pytest.raises(ValidationFailedError, match="crosses"):
        preview(
            (bank,), (replace(second, tenant_id=uuid7()),),
            (MatchPart(bank.id, second.id, Decimal(1)),),
        )
