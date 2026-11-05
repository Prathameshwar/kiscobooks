from billing_platform.reference import DATASETS, load, register_language


def test_opt_in_language_dataset_is_bounded_and_does_not_change_legacy_seed_order() -> None:
    register_language()
    rows = load("language")
    assert 180 <= len(rows) <= 200
    assert DATASETS == ("currency", "country", "state")
    assert all(len(row["code"]) == 2 and len(row["iso3"]) == 3 for row in rows)
    assert len({row["code"] for row in rows}) == len(rows)
    assert len({row["iso3"] for row in rows}) == len(rows)
