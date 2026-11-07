"""Additive warehouse fields must keep existing verified source cuts readable."""

import pytest
from fixtures import manifest
from inventory_fixture import inventory_dataset
from pydantic import ValidationError
from reporting_contract.contract import Fact, Manifest

RETAINED_0140_HASH = "c3beeba41f88f5d4596d8d775e473da4e6609c25bafc0f62c2cbb9822391a0bd"


def test_retained_warehouse_feed_preserves_its_original_evidence():
    facts, _ = inventory_dataset()
    original = manifest(facts).model_dump(mode="json")
    original["schema_hash"] = RETAINED_0140_HASH
    restored = Manifest.model_validate(original)
    assert restored.model_dump(mode="json") == original
    assert restored.control.counts["inventory_report_record"] > 0


def test_unknown_feed_and_tampered_facts_remain_rejected():
    facts, _ = inventory_dataset()
    unknown = manifest(facts).model_dump(mode="json")
    unknown["schema_hash"] = "f" * 64
    with pytest.raises(ValidationError, match="unsupported financial feed schema"):
        Manifest.model_validate(unknown)
    tampered = facts[0].model_dump(mode="json")
    tampered["content_hash"] = "0" * 64
    with pytest.raises(ValidationError, match="source content hash mismatch"):
        Fact.model_validate(tampered)
