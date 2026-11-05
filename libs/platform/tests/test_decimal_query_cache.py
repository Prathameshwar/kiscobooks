import pytest
from sqlalchemy import select

from tests.models import TenantThing


@pytest.mark.filterwarnings("error::sqlalchemy.exc.SAWarning")
def test_money_quantity_queries_can_use_compiled_cache() -> None:
    statement = select(TenantThing.id).where(TenantThing.amount >= 1, TenantThing.qty >= 1)
    assert statement._generate_cache_key() is not None
