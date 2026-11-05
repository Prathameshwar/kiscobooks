from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

spec = spec_from_file_location(
    "verify_sync", Path(__file__).parents[1] / "verify_sync.py"
)
verify = module_from_spec(spec)
spec.loader.exec_module(verify)


def test_environment_is_not_ambiguous_or_echoed(tmp_path):
    path = tmp_path / "service.env"
    path.write_text("APP_DATABASE_URL=private-one\nAPP_DATABASE_URL=private-two\n")
    with pytest.raises(ValueError) as failure:
        verify.database_environment(path, "APP_DATABASE_URL")
    assert "private" not in str(failure.value)
    path.write_text("APP_DATABASE_URL=mysql+asyncmy://local/database\n")
    assert (
        verify.database_environment(path, "APP_DATABASE_URL")
        == "mysql+asyncmy://local/database"
    )


def test_native_rendering_is_equivalent_but_literals_remain_distinct():
    assert verify.canonical_sql(
        "`status` IN ('ACTIVE', 'DRAFT')"
    ) == verify.canonical_sql("status in ('DRAFT','ACTIVE')")
    assert verify.canonical_sql("code != _utf8mb4' A (B) '") == verify.canonical_sql(
        "(code <> ' A (B) ')"
    )
    assert verify.canonical_sql("code = ' A (B) '") != verify.canonical_sql(
        "code = 'AB'"
    )
    assert verify.canonical_sql("id=x'00AA'") == verify.canonical_sql("id=0x00aa")


def test_foreign_key_defaults_are_equivalent_without_hiding_cascades():
    assert verify.foreign_key_action(None) == verify.foreign_key_action("NO ACTION")
    assert verify.foreign_key_action("RESTRICT") != verify.foreign_key_action("CASCADE")
    assert verify.foreign_key_action("SET NULL") != verify.foreign_key_action(None)


def test_sql_grouping_cannot_hide_constraint_changes():
    assert verify.canonical_sql("(a=1 OR b=2) AND c=3") != verify.canonical_sql(
        "a=1 OR (b=2 AND c=3)"
    )
    assert verify.canonical_sql("(a+b)*c") != verify.canonical_sql("a+(b*c)")
    assert verify.canonical_sql("a-(b-c)") != verify.canonical_sql("(a-b)-c")
    assert verify.canonical_sql("label='a AND b'") != verify.canonical_sql(
        "label='aANDb'"
    )


def test_generated_case_cast_and_between_native_rendering():
    model = "CASE WHEN entity='journal_line' THEN CAST(json_extract(data, '$.sequence') AS SIGNED) ELSE NULL END"
    native = "((case when (`entity` = _utf8mb4'journal_line') then cast(json_extract(`data`,_utf8mb4'$.sequence') as signed) else NULL end))"
    assert verify.canonical_sql(model) == verify.canonical_sql(native)
    assert verify.canonical_sql(model) != verify.canonical_sql(
        model.replace("SIGNED", "UNSIGNED")
    )
    assert verify.canonical_sql(
        "(n between 1 and 2) AND (x=1)"
    ) == verify.canonical_sql("n BETWEEN 1 AND 2 AND x = 1")
    assert verify.canonical_sql("NOT (a=1 OR b=2)") != verify.canonical_sql(
        "(NOT a=1) OR b=2"
    )
    assert verify.canonical_sql("label IN ('a,b','c')") == verify.canonical_sql(
        "label IN ('c', 'a,b')"
    )
    # Unsupported syntax retains grouping and literal spelling conservatively.
    assert verify.canonical_sql("(a & b) | c") != verify.canonical_sql("a & (b | c)")


def test_all_layers_must_agree_before_reporting_alignment():
    report = {
        "migration_head": "0008",
        "database_head": ["0008"],
        "readiness_head": "0008",
        "alembic_check_exit": 0,
        "missing_tables": [],
        "extra_tables": [],
        "native_differences": [],
    }
    assert verify.aligned(report)
    for field, value in (
        ("database_head", ["0007"]),
        ("readiness_head", "0009"),
        ("alembic_check_exit", 1),
        ("missing_tables", ["outbox"]),
        ("extra_tables", ["legacy"]),
        ("native_differences", [{"kind": "check"}]),
    ):
        assert not verify.aligned({**report, field: value})


@pytest.mark.parametrize("operator, inverse", [("AND", "OR"), ("OR", "AND")])
def test_mysql_demorgan_rewrites_preserve_constraint_meaning(operator, inverse):
    model = f"NOT (changes_basket = 1 {operator} selection = 'BEST_SINGLE')"
    native = f"changes_basket <> 1 {inverse} selection <> _utf8mb4'BEST_SINGLE'"
    assert verify.canonical_sql(model) == verify.canonical_sql(native)
    assert verify.canonical_sql(model) != verify.canonical_sql(
        native.replace("<> 1", "<> 0")
    )
    assert verify.canonical_sql(model) != verify.canonical_sql(
        native.replace(f" {inverse} ", f" {operator} ")
    )
    # NOT NOT numeric expressions yield a boolean, not the original number.
    assert verify.canonical_sql("NOT NOT amount") != verify.canonical_sql("amount")
