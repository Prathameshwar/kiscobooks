"""Resolving what a company was registered and licensed as on a date.

Three rules are on trial, and each one is a refusal to guess:

* resolution is by ``posting_date`` (CLAUDE.md invariant 4),
* **a gap returns ``None``** and never the nearest row,
* an ambiguous answer raises rather than picking one.

The date arithmetic is where money correctness actually lives here: a
half-open window, an exclusive expiry, or a fallback to the latest row each
produces a document whose tax figures cannot be reproduced from its own
``posting_date``. So the boundaries are tested day by day rather than in the
middle of a range.

No database in this file at all — the module takes value objects precisely so
that is possible (CLAUDE.md §7).
"""

from __future__ import annotations

import datetime as dt
import inspect
import uuid

import pytest

from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.statutory import (
    Licence,
    TaxRegistration,
    assert_company_can_issue,
    assert_no_overlap,
    assert_window_ordered,
    covers,
    licences_valid_on,
    registrations_valid_on,
    resolve_licence,
    resolve_tax_registration,
)

APRIL = dt.date(2026, 4, 1)
SEPTEMBER_30 = dt.date(2026, 9, 30)
OCTOBER = dt.date(2026, 10, 1)
PREMISES_A = uuid.UUID("11111111-1111-4111-8111-111111111111")
PREMISES_B = uuid.UUID("22222222-2222-4222-8222-222222222222")


def registration(
    *,
    number: str = "27AAAPA1234A1Z5",
    regime: str = "regular",
    valid_from: dt.date = APRIL,
    valid_to: dt.date | None = None,
    tax_system: str = "gst_in",
    jurisdiction_code: str = "MH",
    is_primary: bool = False,
) -> TaxRegistration:
    return TaxRegistration(
        tax_system=tax_system,
        regime=regime,
        number=number,
        jurisdiction_code=jurisdiction_code,
        valid_from=valid_from,
        valid_to=valid_to,
        is_primary=is_primary,
    )


def licence(
    *,
    kind: str = "drug_licence_20b",
    number: str = "MH-MUM-20B-4471",
    valid_from: dt.date = APRIL,
    valid_to: dt.date | None = SEPTEMBER_30,
    is_primary: bool = False,
    premises_address_id: uuid.UUID | None = PREMISES_A,
) -> Licence:
    return Licence(
        kind=kind,
        number=number,
        valid_from=valid_from,
        valid_to=valid_to,
        is_primary=is_primary,
        premises_address_id=premises_address_id,
    )


# --- the window ---------------------------------------------------------------


def test_a_window_includes_its_first_day() -> None:
    assert covers(APRIL, SEPTEMBER_30, APRIL) is True


def test_a_window_includes_its_last_day() -> None:
    """A licence expiring on the 30th is valid on the 30th — the certificate says so,
    and an exclusive bound would reject a day's legitimate trading."""
    assert covers(APRIL, SEPTEMBER_30, SEPTEMBER_30) is True


def test_a_window_excludes_the_day_before_it_starts() -> None:
    assert covers(APRIL, SEPTEMBER_30, dt.date(2026, 3, 31)) is False


def test_a_window_excludes_the_day_after_it_ends() -> None:
    assert covers(APRIL, SEPTEMBER_30, OCTOBER) is False


def test_an_open_ended_window_has_no_upper_bound() -> None:
    """``valid_to`` of ``None`` is open-ended, not unknown."""
    assert covers(APRIL, None, dt.date(2099, 1, 1)) is True


def test_a_single_day_window_covers_that_day_only() -> None:
    """A casual-taxable-person registration can genuinely be one day long."""
    assert covers(APRIL, APRIL, APRIL) is True
    assert covers(APRIL, APRIL, dt.date(2026, 4, 2)) is False


def test_a_backwards_window_is_rejected() -> None:
    """Not merely wrong, *invisible*: ``covers`` returns ``False`` for every date, so
    the row resolves for nothing and reads as a gap — the document is then refused, or
    issued with no registration number, with no hint a row exists."""
    with pytest.raises(ValidationFailedError) as raised:
        assert_window_ordered(OCTOBER, APRIL, what="registration")

    assert raised.value.extra["fields"] == {"valid_to": "earlier than valid_from"}


def test_a_backwards_window_names_both_dates() -> None:
    """A 422 that says only "invalid" leaves the user guessing which end to change."""
    with pytest.raises(ValidationFailedError) as raised:
        assert_window_ordered(OCTOBER, APRIL)

    assert "2026-10-01" in str(raised.value)
    assert "2026-04-01" in str(raised.value)


def test_an_open_ended_window_is_ordered_by_definition() -> None:
    assert_window_ordered(APRIL, None)


def test_a_window_that_starts_and_ends_on_one_day_is_ordered() -> None:
    assert_window_ordered(APRIL, APRIL)


# --- resolution by posting_date -----------------------------------------------


def test_the_registration_in_force_on_the_posting_date_is_the_one_returned() -> None:
    """The distributor from the module docstring: Composition until 30 September,
    Regular from 1 October. An invoice dated 20 August must see Composition — the
    regime the return already reported (CLAUDE.md invariant 4)."""
    rows = [
        registration(number="27AAAPA1234A1Z5", regime="composition", valid_to=SEPTEMBER_30),
        registration(number="27AAAPA1234A2Z4", regime="regular", valid_from=OCTOBER),
    ]

    found = resolve_tax_registration(
        rows, jurisdiction_code="MH", posting_date=dt.date(2026, 8, 20)
    )

    assert found is not None
    assert found.regime == "composition"


def test_resolution_on_the_changeover_day_returns_the_later_row() -> None:
    """The boundary that decides a whole day's tax, so it is asserted rather than
    assumed."""
    rows = [
        registration(regime="composition", valid_to=SEPTEMBER_30),
        registration(number="27AAAPA1234A2Z4", regime="regular", valid_from=OCTOBER),
    ]

    found = resolve_tax_registration(rows, jurisdiction_code="MH", posting_date=OCTOBER)

    assert found is not None
    assert found.regime == "regular"


def test_a_gap_returns_none_and_never_the_nearest_row() -> None:
    """A company genuinely may be unregistered for a stretch. Falling back to the
    closest row would put a GSTIN on an invoice issued when the company held none."""
    rows = [
        registration(valid_to=SEPTEMBER_30),
        registration(number="27AAAPA1234A2Z4", valid_from=dt.date(2027, 1, 1)),
    ]

    assert (
        resolve_tax_registration(rows, jurisdiction_code="MH", posting_date=dt.date(2026, 11, 15))
        is None
    )


def test_a_posting_date_before_every_registration_returns_none() -> None:
    """Backdated entry into the opening period, before the company registered."""
    assert (
        resolve_tax_registration(
            [registration()], jurisdiction_code="MH", posting_date=dt.date(2026, 1, 1)
        )
        is None
    )


def test_no_registrations_at_all_returns_none_rather_than_raising() -> None:
    """ "Not registered" is the *absence* of a row (docs/company.md §2.2), so the empty
    case is an answer and not an error. The caller decides what it means."""
    assert resolve_tax_registration([], jurisdiction_code="MH", posting_date=APRIL) is None


def test_another_states_registration_does_not_resolve() -> None:
    """India issues one GSTIN per state. A Karnataka registration is not the answer for
    a Maharashtra document, and returning it would put the wrong state code — and so
    the wrong intra/inter-state treatment — on the invoice."""
    rows = [registration(jurisdiction_code="KA", number="29AAAPA1234A1Z2")]

    assert resolve_tax_registration(rows, jurisdiction_code="MH", posting_date=APRIL) is None


def test_two_registrations_valid_on_one_date_raise_rather_than_picking() -> None:
    """Overlap is rejected at write time, so two matches mean the write path was
    bypassed. Choosing one by row order would make a document's tax depend on the
    query plan."""
    rows = [registration(), registration(number="27AAAPA1234A2Z4")]

    with pytest.raises(ConflictError) as raised:
        resolve_tax_registration(rows, jurisdiction_code="MH", posting_date=APRIL)

    assert "must not depend on row order" in str(raised.value)


def test_the_ambiguity_error_names_every_candidate() -> None:
    """Whoever has to repair the data needs to know which rows to close."""
    rows = [registration(), registration(number="27AAAPA1234A2Z4")]

    with pytest.raises(ConflictError) as raised:
        resolve_tax_registration(rows, jurisdiction_code="MH", posting_date=APRIL)

    assert "27AAAPA1234A1Z5" in str(raised.value)
    assert "27AAAPA1234A2Z4" in str(raised.value)


def test_two_tax_systems_in_one_jurisdiction_are_separated_by_the_filter() -> None:
    """An Indian company can hold a regular GSTIN and a TDS-deductor registration for
    the same state at once, so ``tax_system`` is how the caller disambiguates — and
    without it, this is correctly ambiguous."""
    rows = [
        registration(tax_system="gst_in"),
        registration(tax_system="none", number="TDS27AAAPA1234A"),
    ]

    found = resolve_tax_registration(
        rows, jurisdiction_code="MH", posting_date=APRIL, tax_system="gst_in"
    )

    assert found is not None
    assert found.tax_system == "gst_in"

    with pytest.raises(ConflictError):
        resolve_tax_registration(rows, jurisdiction_code="MH", posting_date=APRIL)


def test_valid_on_returns_every_match_unfiltered() -> None:
    """The plural form exists for the "show me what was in force" read, where several
    systems at once is the expected answer rather than a conflict."""
    rows = [
        registration(tax_system="gst_in"),
        registration(tax_system="none", number="TDS27AAAPA1234A"),
        registration(jurisdiction_code="KA", number="29AAAPA1234A1Z2"),
    ]

    assert len(registrations_valid_on(rows, posting_date=APRIL)) == 3
    assert len(registrations_valid_on(rows, posting_date=APRIL, jurisdiction_code="MH")) == 2
    assert len(registrations_valid_on(rows, posting_date=APRIL, tax_system="gst_in")) == 2


# --- overlap on the write path ------------------------------------------------


def test_adjacent_windows_do_not_overlap() -> None:
    """The correct way to record a change: close the earlier row the day before the
    later one starts."""
    assert_no_overlap(
        [
            registration(valid_to=SEPTEMBER_30),
            registration(number="27AAAPA1234A2Z4", valid_from=OCTOBER),
        ]
    )


def test_windows_sharing_a_single_day_overlap() -> None:
    """One day of ambiguity is enough: every document posted that day resolves twice."""
    with pytest.raises(ConflictError):
        assert_no_overlap(
            [
                registration(valid_to=OCTOBER),
                registration(number="27AAAPA1234A2Z4", valid_from=OCTOBER),
            ]
        )


def test_an_open_ended_row_overlaps_anything_that_starts_after_it() -> None:
    """The most common real mistake: adding the new registration without closing the
    old one."""
    with pytest.raises(ConflictError) as raised:
        assert_no_overlap(
            [
                registration(valid_to=None),
                registration(number="27AAAPA1234A2Z4", valid_from=OCTOBER),
            ]
        )

    assert "open-ended" in str(raised.value)
    assert "Close the earlier one" in str(raised.value)


def test_overlap_is_detected_regardless_of_the_order_rows_arrive_in() -> None:
    """The caller appends the incoming row to the existing ones, so the new row is
    usually last even when its window starts first."""
    rows = [
        registration(number="27AAAPA1234A2Z4", valid_from=OCTOBER),
        registration(valid_to=None),
    ]

    with pytest.raises(ConflictError):
        assert_no_overlap(rows)


def test_a_fully_contained_window_overlaps() -> None:
    with pytest.raises(ConflictError):
        assert_no_overlap(
            [
                registration(valid_to=dt.date(2027, 3, 31)),
                registration(
                    number="27AAAPA1234A2Z4", valid_from=dt.date(2026, 6, 1), valid_to=OCTOBER
                ),
            ]
        )


def test_two_tax_systems_may_overlap_in_one_jurisdiction() -> None:
    """Legitimate and deliberately left alone: a regular GSTIN and a TDS-deductor
    registration for the same state are both in force."""
    assert_no_overlap(
        [
            registration(tax_system="gst_in"),
            registration(tax_system="none", number="TDS27AAAPA1234A"),
        ]
    )


def test_two_jurisdictions_may_overlap_for_one_tax_system() -> None:
    """A company registered in Maharashtra and Karnataka holds both GSTINs at once."""
    assert_no_overlap(
        [
            registration(jurisdiction_code="MH"),
            registration(jurisdiction_code="KA", number="29AAAPA1234A1Z2"),
        ]
    )


def test_one_registration_never_overlaps_itself() -> None:
    assert_no_overlap([registration()])


def test_no_registrations_is_not_an_overlap() -> None:
    assert_no_overlap([])


def test_the_overlap_error_names_both_registrations_and_the_jurisdiction() -> None:
    with pytest.raises(ConflictError) as raised:
        assert_no_overlap([registration(valid_to=None), registration(number="27AAAPA1234A2Z4")])

    message = str(raised.value)
    assert "gst_in" in message
    assert "MH" in message
    assert "27AAAPA1234A1Z5" in message
    assert "27AAAPA1234A2Z4" in message


# --- licences -----------------------------------------------------------------


def test_a_licence_resolves_on_its_last_valid_day() -> None:
    found = resolve_licence([licence()], kind="drug_licence_20b", posting_date=SEPTEMBER_30)

    assert found is not None
    assert found.number == "MH-MUM-20B-4471"


def test_an_expired_licence_does_not_resolve() -> None:
    assert resolve_licence([licence()], kind="drug_licence_20b", posting_date=OCTOBER) is None


def test_a_licence_of_another_kind_does_not_resolve() -> None:
    assert resolve_licence([licence()], kind="fssai", posting_date=APRIL) is None


def test_the_primary_licence_wins_when_several_are_valid() -> None:
    """Several of one kind are legitimately valid at once — a licence is usually per
    premises — so unlike a tax registration this is a choice, not an ambiguity."""
    rows = [
        licence(number="MH-MUM-20B-0001"),
        licence(number="MH-PUN-20B-0002", is_primary=True),
    ]

    found = resolve_licence(rows, kind="drug_licence_20b", posting_date=APRIL)

    assert found is not None
    assert found.number == "MH-PUN-20B-0002"


def test_the_most_recently_issued_licence_wins_when_none_is_primary() -> None:
    rows = [
        licence(number="MH-MUM-20B-0001"),
        licence(number="MH-PUN-20B-0002", valid_from=dt.date(2026, 7, 1)),
    ]

    found = resolve_licence(rows, kind="drug_licence_20b", posting_date=dt.date(2026, 8, 1))

    assert found is not None
    assert found.number == "MH-PUN-20B-0002"


def test_the_choice_is_stable_when_two_licences_start_on_the_same_day() -> None:
    """A reprint must show the same licence every time, so the number breaks the tie
    rather than row order."""
    first = [licence(number="MH-MUM-20B-0001"), licence(number="MH-PUN-20B-0002")]
    reversed_order = list(reversed(first))

    chosen = resolve_licence(first, kind="drug_licence_20b", posting_date=APRIL)
    chosen_again = resolve_licence(reversed_order, kind="drug_licence_20b", posting_date=APRIL)

    assert chosen is not None
    assert chosen_again is not None
    assert chosen.number == chosen_again.number


def test_a_primary_licence_outranks_a_newer_non_primary_one() -> None:
    """The tie-break order matters: primary first, then recency. A renewal recorded
    for another premises must not displace the nominated one."""
    rows = [
        licence(number="MH-MUM-20B-0001", is_primary=True),
        licence(number="MH-PUN-20B-0002", valid_from=dt.date(2026, 7, 1)),
    ]

    found = resolve_licence(rows, kind="drug_licence_20b", posting_date=dt.date(2026, 8, 1))

    assert found is not None
    assert found.number == "MH-MUM-20B-0001"


def test_licences_valid_on_narrows_to_the_kinds_asked_for() -> None:
    rows = [licence(), licence(kind="fssai", number="10012345678901")]

    assert len(licences_valid_on(rows, posting_date=APRIL)) == 2
    assert len(licences_valid_on(rows, posting_date=APRIL, kinds=("fssai",))) == 1
    assert licences_valid_on(rows, posting_date=OCTOBER) == ()


# --- the posting gate ---------------------------------------------------------


def test_retail_drug_issue_rejects_wholesale_licence() -> None:
    with pytest.raises(ConflictError):
        assert_company_can_issue(
            [licence(kind="drug_licence_20b")],
            country_code="IN",
            posting_date=APRIL,
            line_gates=("scheduled_drug",),
            operation="RETAIL",
            premises_address_id=PREMISES_A,
            drug_class="OTHER_THAN_C_C1_X",
        )


def test_drug_issue_rejects_other_premises_and_missing_context() -> None:
    with pytest.raises(ConflictError):
        assert_company_can_issue(
            [licence(kind="drug_licence_20")],
            country_code="IN",
            posting_date=APRIL,
            line_gates=("scheduled_drug",),
            operation="RETAIL",
            premises_address_id=PREMISES_B,
            drug_class="OTHER_THAN_C_C1_X",
        )
    with pytest.raises(ConflictError):
        assert_company_can_issue(
            [licence(kind="drug_licence_20")],
            country_code="IN",
            posting_date=APRIL,
            line_gates=("scheduled_drug",),
        )


def test_retail_drug_issue_accepts_same_premises_retail_licence() -> None:
    assert_company_can_issue(
        [licence(kind="drug_licence_20")],
        country_code="IN",
        posting_date=APRIL,
        line_gates=("scheduled_drug",),
        operation="RETAIL",
        premises_address_id=PREMISES_A,
        drug_class="OTHER_THAN_C_C1_X",
    )


def test_drug_issue_needs_class_and_matching_form() -> None:
    with pytest.raises(ConflictError):
        assert_company_can_issue(
            [licence(kind="drug_licence_20")],
            country_code="IN", posting_date=APRIL, line_gates=("scheduled_drug",),
            operation="RETAIL", premises_address_id=PREMISES_A,
        )
    with pytest.raises(ConflictError):
        assert_company_can_issue(
            [licence(kind="drug_licence_20")],
            country_code="IN", posting_date=APRIL, line_gates=("scheduled_drug",),
            operation="RETAIL", premises_address_id=PREMISES_A,
            drug_class="C_C1_EXCLUDING_X",
        )


def test_mixed_drug_classes_need_both_licence_forms() -> None:
    with pytest.raises(ConflictError):
        assert_company_can_issue(
            [licence(kind="drug_licence_20b")],
            country_code="IN",
            posting_date=APRIL,
            line_gates=("scheduled_drug", "scheduled_drug"),
            operation="WHOLESALE",
            premises_address_id=PREMISES_A,
            drug_classes=("OTHER_THAN_C_C1_X", "C_C1_EXCLUDING_X"),
        )
    assert_company_can_issue(
        [
            licence(kind="drug_licence_20b"),
            licence(kind="drug_licence_21b", number="MH-MUM-21B-9001"),
        ],
        country_code="IN",
        posting_date=APRIL,
        line_gates=("scheduled_drug", "scheduled_drug"),
        operation="WHOLESALE",
        premises_address_id=PREMISES_A,
        drug_classes=("OTHER_THAN_C_C1_X", "C_C1_EXCLUDING_X"),
    )


def test_schedule_x_does_not_inherit_the_general_drug_forms() -> None:
    with pytest.raises(ConflictError):
        assert_company_can_issue(
            [licence(kind="drug_licence_20"), licence(kind="drug_licence_21")],
            country_code="IN",
            posting_date=APRIL,
            line_gates=("scheduled_drug",),
            operation="RETAIL",
            premises_address_id=PREMISES_A,
            drug_class="SCHEDULE_X",
        )


def test_licence_selection_filters_by_premises_before_primary_rank() -> None:
    rows = [
        licence(number="WRONG", is_primary=True, premises_address_id=PREMISES_B),
        licence(number="RIGHT", premises_address_id=PREMISES_A),
    ]
    selected = resolve_licence(
        rows,
        kind="drug_licence_20b",
        posting_date=APRIL,
        premises_address_id=PREMISES_A,
    )
    assert selected is not None and selected.number == "RIGHT"


def test_a_document_with_no_gated_lines_needs_no_licence() -> None:
    """The overwhelmingly common case, and it must not require a profile lookup to
    succeed."""
    assert_company_can_issue([], country_code="IN", posting_date=APRIL, line_gates=())


def test_a_gated_line_passes_with_a_valid_licence() -> None:
    assert_company_can_issue(
        [licence()], country_code="IN", posting_date=APRIL, line_gates=("scheduled_drug",),
        operation="WHOLESALE", premises_address_id=PREMISES_A,
        drug_class="OTHER_THAN_C_C1_X",
    )


def test_another_wholesale_drug_licence_satisfies_the_gate() -> None:
    """Form 21B covers the C/C1 wholesale class at this premises."""
    assert_company_can_issue(
        [licence(kind="drug_licence_21b", number="MH-MUM-21B-9001")],
        country_code="IN",
        posting_date=APRIL,
        line_gates=("scheduled_drug",),
        operation="WHOLESALE",
        premises_address_id=PREMISES_A,
        drug_class="C_C1_EXCLUDING_X",
    )


def test_a_gated_line_is_rejected_when_the_licence_expired_the_day_before() -> None:
    """An expiry discovered at the till is a shop that has stopped trading, which is
    what ``renewal_reminder_days`` and the Beat sweep exist to prevent — but once it
    has happened, the posting is *rejected*, never warned (docs/company.md §4.4)."""
    with pytest.raises(ConflictError) as raised:
        assert_company_can_issue(
            [licence()], country_code="IN", posting_date=OCTOBER, line_gates=("scheduled_drug",),
            operation="WHOLESALE", premises_address_id=PREMISES_A,
            drug_class="OTHER_THAN_C_C1_X",
        )

    assert "drug_licence_20b" in str(
        raised.value
    )
    assert "2026-10-01" in str(raised.value)


def test_a_gated_line_is_rejected_when_the_company_holds_no_licence_at_all() -> None:
    with pytest.raises(ConflictError):
        assert_company_can_issue(
            [], country_code="IN", posting_date=APRIL, line_gates=("scheduled_drug",),
            operation="WHOLESALE", premises_address_id=PREMISES_A,
            drug_class="OTHER_THAN_C_C1_X",
        )


def test_a_licence_of_the_wrong_kind_does_not_satisfy_a_gate() -> None:
    """FSSAI is a real licence with a real expiry and gates nothing. Holding it must
    not let a scheduled drug through."""
    with pytest.raises(ConflictError):
        assert_company_can_issue(
            [licence(kind="fssai", number="10012345678901")],
            country_code="IN",
            posting_date=APRIL,
            line_gates=("scheduled_drug",),
            operation="WHOLESALE",
            premises_address_id=PREMISES_A,
            drug_class="OTHER_THAN_C_C1_X",
        )


def test_a_gate_the_jurisdiction_profile_does_not_cover_fails_closed() -> None:
    """**The load-bearing one.** An incomplete profile must not become permission to
    sell a controlled item unlicensed: "this platform does not know what permits that
    here" is read as refusal."""
    with pytest.raises(ConflictError) as raised:
        assert_company_can_issue(
            [licence()], country_code="IN", posting_date=APRIL, line_gates=("firearm",)
        )

    assert "no licence in the IN jurisdiction profile permits" in str(raised.value)


def test_a_gate_fails_closed_in_a_jurisdiction_with_no_licences_at_all() -> None:
    """The UK profile declares none, so every gate there refuses — a scheduled-drug
    line cannot be posted from a UK company until that profile is written."""
    with pytest.raises(ConflictError):
        assert_company_can_issue(
            [], country_code="GB", posting_date=APRIL, line_gates=("scheduled_drug",),
            operation="RETAIL", premises_address_id=PREMISES_A,
            drug_class="OTHER_THAN_C_C1_X",
        )


def test_every_gate_on_the_document_is_checked_not_only_the_first() -> None:
    """A document holding a permitted line and a forbidden one is refused: the loop
    covers all gates, so a satisfied one cannot mask an unsatisfied one."""
    with pytest.raises(ConflictError):
        assert_company_can_issue(
            [licence()],
            country_code="IN",
            posting_date=APRIL,
            line_gates=("scheduled_drug", "narcotic"),
            operation="WHOLESALE",
            premises_address_id=PREMISES_A,
            drug_class="OTHER_THAN_C_C1_X",
        )


def test_a_repeated_gate_is_checked_once_and_still_passes() -> None:
    """Every line on a fifty-line pharmacy invoice carries the same gate."""
    assert_company_can_issue(
        [licence()],
        country_code="IN",
        posting_date=APRIL,
        line_gates=("scheduled_drug",) * 50,
        operation="WHOLESALE",
        premises_address_id=PREMISES_A,
        drug_class="OTHER_THAN_C_C1_X",
    )


def test_an_unsupported_country_cannot_post_a_gated_line() -> None:
    """``profile`` refuses the country, which is the same fail-closed answer by a
    different route."""
    with pytest.raises(ValidationFailedError):
        assert_company_can_issue(
            [], country_code="FR", posting_date=APRIL, line_gates=("scheduled_drug",),
            operation="WHOLESALE", premises_address_id=PREMISES_A,
            drug_class="OTHER_THAN_C_C1_X",
        )


def test_the_gate_takes_no_document_kind() -> None:
    """No document kind exempts the gate, and a parameter accepted but never read
    reads as an exemption mechanism that does not exist. A delivery challan for a
    scheduled drug needs the licence exactly as much as the invoice does."""
    parameters = set(inspect.signature(assert_company_can_issue).parameters)

    assert "document_kind" not in parameters
    assert not parameters & {"actor", "force", "override", "is_platform_admin"}


# --- the value objects are frozen ---------------------------------------------


def test_a_registration_cannot_be_mutated_while_being_resolved() -> None:
    """Resolution decides what a posted document says. A resolver that could edit its
    input would be able to change history on read."""
    with pytest.raises(AttributeError):
        registration().regime = "composition"  # type: ignore[misc]


def test_a_licence_cannot_be_mutated_while_being_resolved() -> None:
    with pytest.raises(AttributeError):
        licence().valid_to = None  # type: ignore[misc]


# --- registration classes -----------------------------------------------------


def test_a_regular_gstin_and_a_tds_deductor_registration_may_coexist_in_one_state() -> None:
    """Regression: both are ``gst_in``, so grouping by ``(tax_system, jurisdiction)``
    alone rejected the pairing the docstring promised. The deductor registration is a
    different *class* of registration and never competes with the supplier one."""
    assert_no_overlap(
        [
            registration(regime="regular"),
            registration(regime="tds_deductor", number="27DELA12345B1DX"),
        ]
    )


def test_an_isd_registration_may_coexist_with_the_regular_one() -> None:
    assert_no_overlap([registration(regime="regular"), registration(regime="isd")])


def test_two_supplier_regimes_still_overlap() -> None:
    """Composition and regular are the same class — one is the other's replacement,
    and a document must resolve to exactly one of them."""
    with pytest.raises(ConflictError):
        assert_no_overlap(
            [registration(regime="regular"), registration(regime="composition", valid_from=OCTOBER)]
        )


def test_an_ecommerce_tcs_registration_may_coexist_with_the_regular_one() -> None:
    assert_no_overlap([registration(regime="regular"), registration(regime="ecommerce_operator")])


def test_two_tds_deductor_registrations_overlap() -> None:
    with pytest.raises(ConflictError):
        assert_no_overlap(
            [registration(regime="tds_deductor"), registration(regime="tds_deductor")]
        )


def test_an_uncatalogued_regime_is_grouped_as_a_supplier() -> None:
    """Fail towards more rejections: an unknown pairing is never allowed to coexist."""
    with pytest.raises(ConflictError):
        assert_no_overlap(
            [
                registration(tax_system="none", regime="x"),
                registration(tax_system="none", regime="y"),
            ]
        )


def test_resolution_can_be_narrowed_to_one_registration_class() -> None:
    supplier = registration(regime="regular")
    deductor = registration(regime="tds_deductor", number="27DELA12345B1DX")

    with pytest.raises(ConflictError):
        resolve_tax_registration([supplier, deductor], jurisdiction_code="MH", posting_date=APRIL)

    assert (
        resolve_tax_registration(
            [supplier, deductor],
            jurisdiction_code="MH",
            posting_date=APRIL,
            registration_class="supplier",
        )
        == supplier
    )
    assert registrations_valid_on(
        [supplier, deductor], posting_date=APRIL, registration_class="tds_deductor"
    ) == (deductor,)
    assert supplier.registration_class == "supplier"
    assert deductor.registration_class == "tds_deductor"
