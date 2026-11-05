# Company — Fields, Tax Registration & Behaviour

**Status:** Draft — design agreed, not yet modelled in code
**Date:** 2026-09-03
**Master:** `identity` · **Replicated read-only to:** every service
**Related:** [org-model.md](org-model.md) §2.1, §4.2 · [fiscal-year.md](fiscal-year.md) §1, §7 · [custom-fields.md](custom-fields.md) §11 · [roles-permissions.md](roles-permissions.md) §2 · [audit.md](audit.md)

Supersedes the `company` field list and `company_tax_registration` sketch in [org-model.md](org-model.md) §4.2.

**Planned India tax extension, 2026-10-10:** [Voucher tax recording](voucher-tax-recording.md)
adds GST statutory dates/location-to-registration mapping and applicable state-VAT profiles.
The catalogue and posting-date behavior below describe current contracts; India state-VAT
support is not present merely because foreign VAT systems are listed. Extend those contracts
explicitly before enabling new profiles. One company may need separate GST and VAT registrations;
its default tax system never classifies all its transactions. Existing registration overlap
restrictions require review before supporting additional supplier registrations in one state.

A company is not a settings bag. It is the **legal entity that issues documents**, and four of its columns silently reinterpret every amount ever posted if changed. §5.2 is the most important section in this doc.

---

## 1. Where each kind of field belongs

Four homes, and the boundary between them is a rule, not a preference:

| Kind of field | Home | Why |
|---|---|---|
| Universal to every company everywhere | Column on `company` | Currency, fiscal start, precision, locale, status |
| Drives tax, money, or posting | Column, always | [custom-fields.md](custom-fields.md) §11 — domain logic never reads a custom field |
| Jurisdiction-specific, one or few, identity-like | `company_statutory_id` row | PAN, TAN, CIN, EIN — differs per country, NULL columns otherwise |
| Jurisdiction-specific, expires, gates trading | `company_licence` row | Drug licence, FSSAI — has behaviour, not just a value |
| Tax registration used on invoices | `company_tax_registration` row | Multiple per company, date-effective |
| Everything else the tenant wants | Custom field | [custom-fields.md](custom-fields.md) |

**The mistake to avoid:** adding forty India-specific columns that are `NULL` for a UK company. §3 is how we avoid it.

---

## 2. Tax type — two axes, not one

Your list (GST, VAT, Composition) mixes two independent things. Keep them separate or the model fights you within a quarter.

| Axis | Question | Changes over time? |
|---|---|---|
| **`tax_system`** | Which tax framework does this entity operate under? | Effectively never — an Indian company doesn't become a UK VAT entity |
| **`regime`** | How is it registered *within* that framework? | **Yes, and mid-year** — Composition → Regular is routine |

Composition is not a peer of GST. It is a **regime inside** `gst_in`.

### 2.1 `tax_system` catalogue

Code-defined, keyed to the jurisdiction:

```
gst_in          India GST
vat_gb          UK VAT
vat_eu          EU VAT (member-state specific rules layered on)
vat_ae          UAE VAT
vat_sa          Saudi VAT
gst_au          Australia GST
gst_ca          Canada GST/HST/PST
sales_tax_us    US state & local sales tax
none            No indirect tax registration
```

### 2.2 `regime` catalogue, per system

**`gst_in`**
```
regular                  Normal registered dealer; charges and collects GST
composition              Flat rate on turnover; CANNOT charge tax on the invoice; quarterly filing
unregistered             Below threshold; no GST on invoices
sez_unit                 Zero-rated supplies
sez_developer
ecommerce_operator       TCS collection obligations
isd                      Input Service Distributor
casual_taxable_person    Time-bound registration
tds_deductor
```

**`vat_gb` / `vat_eu` / `vat_ae` / `vat_sa`**
```
standard                 Normal accrual VAT
flat_rate                Fixed percentage; restricted input reclaim
cash_accounting          VAT due on payment, not invoice date
annual_accounting
margin_scheme            Second-hand goods
exempt
not_registered
```

**`sales_tax_us`**
```
destination_based
origin_based
exempt_reseller
not_registered
```

**A tax system with no regime catalogue accepts no registration.** `gst_au`, `gst_ca` and `none` are in the `tax_system` catalogue (§2.1) but have no regimes listed above, and `get_regime` refuses them with `{"tax_system": "no regime catalogue defined for this system"}` — distinct from `{"tax_system": "not in the platform catalogue"}` for a system that does not exist at all. Silently accepting one would create a registration no posting path could interpret, since `may_charge_tax` has no entry to read. Each VAT system also owns its **own** regime objects rather than sharing one dict, so adding a `vat_ae` regime cannot silently appear under `vat_gb`.

### 2.3 Regime drives money, so it is code and it is date-effective

Two consequences, both non-negotiable.

**It is a code catalogue, never tenant-editable data.** A composition dealer must not charge tax on an invoice; that is a hard rule in `domain/`. If regime were a free-text or admin-created value, no code path could be statically checked against it. This is the same rule as permissions ([roles-permissions.md](roles-permissions.md) §1) and custom-field types ([custom-fields.md](custom-fields.md) §1).

**It must never be a current-value column on `company`.**

> A distributor is on Composition from 1 Apr, crosses the threshold, and migrates to Regular on 1 Oct. On 15 Nov they reprint an invoice dated 20 Aug.
>
> With `company.tax_regime = 'regular'`, that reprint shows the wrong regime and the wrong tax treatment on a document that has already been filed.

So regime lives on `company_tax_registration` with `valid_from` / `valid_to`, and is resolved by the document's **`posting_date`** — never by `now()`, never by `created_at` (CLAUDE.md invariant 4). This is why [org-model.md](org-model.md) §4.5 already specifies `valid_from`/`valid_to` for this table rather than `is_active`.

`company.default_tax_system` exists **only to default the creation form and the UI**. It is not consulted by any posting path — like the proposed per-user selected financial year ([fiscal-year.md](fiscal-year.md) section 4.5).
The implemented fiscal-year model has no `is_current` field. Company calendar/books-begin
settings remain distinct from navigation; see the [financial-year design](voucher-financial-year-design.md).

### 2.4 Where tax *rates* live

Registration is `identity`. Rate and rule resolution is **`catalog`** (`tax_rule`, per [tech-stack.md](tech-stack.md)). `billing` reads both from local replicas. Registration answers *"who am I registered as"*; `tax_rule` answers *"what rate applies to this line"*. Don't merge them.

---

## 3. Jurisdiction profiles — how the field list stays sane

Rather than columns per country, `libs/platform` holds a **code-defined, versioned jurisdiction profile** — static data, no table, the same tier as ISO country/currency ([tech-stack.md](tech-stack.md) § *Reference data ownership*).

Shipped as frozen dataclasses in `billing_platform.jurisdiction`, not dicts, so mypy checks every field and a typo is a boot failure rather than a silent `None`:

```python
JURISDICTION_PROFILES: Final[dict[str, JurisdictionProfile]] = {
    "IN": JurisdictionProfile(
        country_code="IN",
        tax_systems=(
            TaxSystemSpec("gst_in", number_pattern=r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"),
        ),
        tax_registration_is_per="state",          # one GSTIN per state
        statutory_ids=(
            StatutoryIdSpec(kind="pan", label="PAN", pattern=r"^[A-Z]{5}\d{4}[A-Z]$",
                            required=True, prints_on_invoice=True),
            StatutoryIdSpec(kind="tan", label="TAN", pattern=r"^[A-Z]{4}\d{5}[A-Z]$"),
            StatutoryIdSpec(kind="cin", label="CIN",
                            pattern=r"^[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}$"),
            StatutoryIdSpec(kind="udyam", label="Udyam (MSME)"),
            StatutoryIdSpec(kind="iec", label="Import-Export Code"),
            StatutoryIdSpec(kind="aadhaar", label="Aadhaar",
                            pattern=r"^\d{12}$", restricted=True),      # §4.3
        ),
        licences=(
            LicenceSpec(kind="drug_licence_20", label="Drug Licence 20 (retail)",
                        has_expiry=True, prints_on_invoice=True, gates="scheduled_drug"),
            LicenceSpec(kind="drug_licence_21", label="Drug Licence 21 (retail)",
                        has_expiry=True, prints_on_invoice=True, gates="scheduled_drug"),
            LicenceSpec(kind="drug_licence_20b", label="Drug Licence 20B (wholesale)",
                        has_expiry=True, prints_on_invoice=True, gates="scheduled_drug"),
            LicenceSpec(kind="drug_licence_21b", label="Drug Licence 21B (wholesale)",
                        has_expiry=True, prints_on_invoice=True, gates="scheduled_drug"),
            LicenceSpec(kind="narcotic_licence", label="Narcotic Licence",
                        has_expiry=True, gates="narcotic"),
            LicenceSpec(kind="fssai", label="FSSAI", has_expiry=True, prints_on_invoice=True),
            LicenceSpec(kind="lut", label="LUT (zero-rated exports)", has_expiry=True),
        ),
        cash_receipt_limit=Decimal("200000.0000"),  # §269ST
        # What a setup form offers already selected — a suggestion, never a seeding
        # ([company-features.md](company-features.md) §3). `e_invoicing` is absent on
        # purpose: it starts at a turnover threshold and needs IRP credentials.
        default_features=("inventory", "credit_limits", "e_waybill"),
    ),
    "GB": JurisdictionProfile(
        country_code="GB",
        tax_systems=(TaxSystemSpec("vat_gb"),),     # no number_pattern — see below
        tax_registration_is_per="country",
        statutory_ids=(
            StatutoryIdSpec(kind="company_number", label="Company Number",
                            pattern=r"^\d{8}$|^[A-Z]{2}\d{6}$",
                            required=True, prints_on_invoice=True),
            StatutoryIdSpec(kind="utr", label="UTR"),
        ),
        licences=(),
        cash_receipt_limit=None,
        default_features=("inventory", "credit_limits"),
    ),
}
```

**What this buys:**

- The company creation form **generates itself** from the selected country — no per-country UI branching, and `default_features` means not even the capability step's starting selection is a list a client keeps ([company-features.md](company-features.md) §3)
- Validation regex is reviewable in a diff, not typed by an admin
- A new country is one profile entry plus tests, not a migration
- No NULL column graveyard

`kind` values are immutable once shipped; they appear in stored rows.

Four field names differ from the sketch above, and each difference is load-bearing:

- **`pattern`, not `regex`**, and `TaxSystemSpec.number_pattern` is a *separate* field: the registration number's shape belongs to the tax system, not to a statutory identifier. `vat_gb` deliberately declares none — a UK VAT number has several legitimate shapes, and a pattern that admitted only one would reject valid registrations. Where a pattern is absent the number is still normalized and required to be non-empty.
- **`restricted: bool` replaces `sensitivity` + `storage`.** Two coupled string fields can disagree (`"restricted"` with `"full"`); one boolean cannot. `restricted=True` means exactly one thing — `value` is discarded and only `value_last4` is kept — and it is the single flag `prepare_statutory_value` reads.
- **`[LU]`, not `[LUu]`, in the CIN pattern.** A CIN never starts with a lowercase letter, and the third character class is uppercase-only anyway. Harmless in practice because normalization uppercases before the regex runs, but the typo would only ever have widened what the regex admits.
- **`aadhaar` carries `pattern=r"^\d{12}$"`.** The pattern is checked *before* the discard, because verifying the wrong number is worse than not verifying. A restricted identifier is consequently never `required` and never `prints_on_invoice` — it cannot be, since the value is not kept.

**Validated at import**, so a malformed profile is a boot failure rather than a 500 on the first company created in that country. The checks: the profile key matches `country_code` and is ISO-shaped · at least one tax system, each in the `TAX_SYSTEMS` catalogue · `tax_registration_is_per` is a known scope · no duplicate `kind` among tax systems, identifiers or licences, and each is lowercase snake_case · every pattern compiles · every identifier and licence has a label · **a `restricted` identifier is neither `required` nor `prints_on_invoice`** — that one is the whole point of the module · a non-empty `gates` string · and a `cash_receipt_limit` that is finite, positive, within `DECIMAL(19,4)`, and no more than four decimals, since MariaDB truncates a narrower scale without erroring.

Two things are deliberately *not* import checks. The ISO-country check is **shape only** (`^[A-Z]{2}$`) — validating against `reference.countries()` would pull a JSON load into a catalogue module's import — so "is it a real ISO country" is a test. And "every gating licence expires" is a test too, because it is a property of the catalogue as shipped rather than a rule a new profile must satisfy for the module to work.

---

## 4. Tables

### 4.1 `company`

Refines [org-model.md](org-model.md) §4.2. **Bold = immutable after first posting (§5.2).**

```
company
  id, tenant_id, parent_company_id
  code                              -- short, unique per tenant; USED IN NUMBERING  [immutable]
                                    -- generated at creation, not asked for; see below
  legal_name, trade_name, display_name
  entity_type                       -- pvt_ltd | llp | partnership | sole_prop | public | trust | branch
  incorporation_date
  country_code   CHAR(2)   FK → country.code    -- selects the jurisdiction profile (§3)  [immutable]
  state_code     VARCHAR(6) FK → state.code     -- home state; drives place of supply     [immutable]
  status                            -- active | suspended | closed   (rule 4.12)

  FOREIGN KEY (country_code, state_code) REFERENCES state (country_code, code)

  -- financial [ledger settings immutable after first posting; reporting currency is presentation]
  base_currency  CHAR(3)   FK → currency.code   [immutable]
  reporting_currency          -- optional presentation currency; null means base; mutable
  fiscal_year_start_month           [immutable]
  fiscal_year_start_day             [immutable]
  books_begin_date                  [immutable]
  amount_precision                  [immutable]  -- display/rounding scale, 0–4; storage is always 4
  quantity_precision                [immutable]  -- display/rounding scale, 0–4; storage is always 4
  rounding_mode                     [immutable]

  -- tax posture (defaults for the UI; authoritative values are per-registration)
  default_tax_system                -- §2.1; form default only, never read by a posting path
  tax_treatment_default             -- inclusive | exclusive
  reverse_charge_applicable
  tds_applicable, tcs_applicable
  einvoicing_enabled, e_waybill_applicable

  -- commercial defaults
  default_payment_terms_days
  credit_limit_default
  cash_receipt_limit                -- from the jurisdiction profile; overridable downward only

  -- business nature
  industry_code                     -- NIC / NAICS
  business_nature                   -- trading | manufacturing | service | distribution | retail

  -- locale & display config  (server-owned; clients render from it, never hardcode — §4.5)
  timezone, locale
  date_format                       -- display pattern for _date fields
  datetime_format                   -- display pattern for _at fields
  digit_grouping                    -- indian (12,34,567) | western (1,234,567)
  decimal_separator, thousands_separator
  negative_format                   -- minus | parentheses
  show_amount_in_words              -- boolean; drives the printed words line
  currency_symbol_position          -- prefix | suffix
  currency_symbol_override          -- rare; e.g. "Rs." instead of "₹" on legacy stationery

  -- documents & branding
  logo_url, signature_url, brand_color
  print_template_id
  terms_and_conditions, declaration_text, jurisdiction_text
  signatory_name, signatory_designation
  dsc_thumbprint                    -- certificate THUMBPRINT only; never a key or PFX  (§5 security)

  -- visibility (§6)
  visibility                        -- listed | unlisted
  requires_step_up                  -- boolean
  visibility_changed_at, visibility_changed_by

  -- extensibility
  custom_fields (JSON)
```

**`code` is generated, not asked for.** `NOT NULL`, unique per tenant (`uq_company_tenant_id_code`), and the operator cannot know what is already taken: a typed code either duplicates an existing one or is unique by luck. The creation client derives it from the legal name and appends a short random suffix (`ACME-FGKQ`), shows it on the review step with the fact that it prints in document numbers and freezes on first posting, and draws a new suffix if the code is refused. `code` is still required on `POST /v1/companies`, and it stays editable in company settings until the ratchet in §5.2 closes.

**A taken code is a 409 that names the field.** `POST /v1/companies` pre-checks the code — through the session tenant filter, so another tenant's row neither blocks a code nor leaks its existence — and refuses with `fields: {"code": "already in use"}`. The unique key still backstops the race, but it arrives as the generic conflict envelope, because a constraint name is an internal identifier and is never returned (CLAUDE.md §5.8). The route has a second 409 — an unseeded system-role catalogue — and under one envelope the two are indistinguishable: one is resolved by choosing another code and the other is not. A client that generates the code has to be able to tell them apart, which is the whole reason the field is there.

**Capability toggles are not columns.** Inventory, multi-currency, cost centres, batch tracking, TDS/TCS and similar live in `company_feature` — see [company-features.md](company-features.md). They need `enabled_by`, an audit event each, and an irreversibility lock, none of which a boolean column gives. What a *setup form* arrives with selected comes from the jurisdiction profile's `default_features` (§3) — a suggestion, never a seeded row.

**`invoice_series_prefix` is removed.** One prefix per company cannot express tax invoice / proforma / delivery challan / credit note / export invoice, which every real deployment needs. Series live in `document_sequence`, keyed `(company_id, series_key, fiscal_year_id)` ([fiscal-year.md](fiscal-year.md) §7). Company creation seeds the default set.

### 4.2 `company_tax_registration`

```
company_tax_registration
  id, tenant_id, company_id
  tax_system                -- §2.1  [immutable after create]
  regime                    -- §2.2  [immutable after create]
  number                    -- GSTIN / VAT number / etc.  [immutable after create]
  jurisdiction_code         -- state or country code this registration covers  [immutable after create]
  legal_name_on_registration
  registered_address_id     -- FK to company_address
  valid_from, valid_to      -- rule 4.12: dates, NOT is_active  [valid_from immutable after create]
  is_primary                -- at most one per (tax_system, jurisdiction_code) on any date
  registration_class        -- derived from regime; set in domain/ on create, read-only
  verified_at, verified_by, verification_reference

  UNIQUE (company_id, tax_system, registration_class, jurisdiction_code, valid_from)
```

- **Resolution is by `posting_date`** (§2.3). One helper, in the shared library:
  `resolve_tax_registration(registrations, *, jurisdiction_code, posting_date)`
  It takes the **rows**, not a `company_id`. It has to: the caller is `billing`, inside a money transaction, reading its own local replica — a helper that accepted a `company_id` would have to query, and a query from inside `libs/platform` is either a second data path with no tenant scope of its own or a synchronous cross-service call in a posting transaction (CLAUDE.md invariant 7). The same shape applies to `resolve_licence` and `assert_no_overlap`.
- Overlapping validity for the same `(tax_system, registration class, jurisdiction_code)` is rejected at write time. The **registration class** (`supplier`, `isd`, `tds_deductor`, `tcs_collector`) is a property of the regime in the shared `Regime` catalogue (`billing_platform.tax`), so a regular GSTIN and a TDS-deductor or ISD registration may run side by side in one state; two supplier-class registrations (regular, composition, SEZ, …) may not. Resolution callers that charge tax pass `registration_class="supplier"`. Without the check, resolution is ambiguous and the answer depends on row order. Two matches on the same date raise, and the message names **every** candidate, because the fix is to close one window and the user needs to know which rows are in play.
- What a registration *is* — `tax_system`, `regime`, `number`, `jurisdiction_code`, `valid_from` — is **immutable after create** (a 422, `ImmutableFieldError`, enforced in identity `domain/` for every actor, not a 403 — no role can lift it). Judged on the diff, so echoing the unchanged values back is not an edit. A framework, regime, number or state change is "close this row (`valid_to`), add a new one", which is what keeps the old documents resolvable by `posting_date`. Only `valid_to`, `legal_name_on_registration`, `registered_address_id` and `is_primary` are amendable, and the amendment audit event carries the changed-field set (values outside the audit allowlist redacted).
- **At most one `is_primary` per `(tax_system, jurisdiction_code)` on any date**, across classes — a 409, checked under the company `FOR UPDATE` lock on create and amend.
- **GSTIN numbers are verified, not only pattern-matched** (`billing_platform.jurisdiction.validate_gstin`): the mod-36 check character over the first 14 characters, the two-digit state prefix against the jurisdiction's `state.tax_jurisdiction_code`, and entity code `0` rejected. A `tds_deductor` registration also accepts the TAN-based GSTIN shape (literal `D`), and a `tcs_collector` (regime `ecommerce_operator`) the TCS shape — state + PAN + entity + literal `C` + check character; each shape is accepted for its class only. A state with no GST state code cannot take a GSTIN registration (422) rather than being stored unchecked.
- The class is stored (`registration_class`, derived from the regime, never client-supplied) so the unique key groups exactly as the overlap rule does: a regular and a TDS-deductor or TCS registration in one state may start on the same day.
- **A gap is not an error.** A company genuinely may be unregistered for a stretch. Resolution returns `None` and the domain decides; it must not silently fall back to the nearest row.
- Never deleted. An invoice issued under an old GSTIN must still resolve it years later.

### 4.3 `company_statutory_id`

```
company_statutory_id
  id, tenant_id, company_id
  kind                      -- from the jurisdiction profile (§3)
  value                     -- see the restriction below
  value_last4               -- populated for restricted kinds
  holder_name               -- for proprietor-held IDs
  issued_on, valid_to
  verified_at, verified_by, verification_reference
  is_active

  UNIQUE (company_id, kind, value_last4)
```

#### AADHAAR and SSN — store the last four, never the full number

**Do not store full AADHAAR or SSN-class national identity numbers.** This is the same rule as card data (CLAUDE.md §5.10), for the same reason and with sharper legal teeth:

- India's Aadhaar Act restricts who may store the number at all. UIDAI requires any stored Aadhaar to sit in an encrypted **Aadhaar Data Vault** with separate key management. A general billing platform has no basis to hold it.
- The same applies to SSN, and to national ID numbers in most jurisdictions with a data-protection regime.
- **You almost never need the number.** You need to know the holder was verified. That is `value_last4` + `verification_reference`.

So: `restricted=True` in the jurisdiction profile means the field **accepts** a full value, derives `value_last4`, records the verification reference, and **discards the rest**. It is never persisted, never logged (CLAUDE.md §5.11), never returned by an API, and never exported.

**One function implements this: `prepare_statutory_value(country_code, kind, value)`.** Every caller in every service goes through it, because a second code path that writes `company_statutory_id.value` directly is the entire failure — the discard has to happen before the value reaches a model at all. Three details that are part of the rule, not implementation trivia:

- The **pattern is checked before the discard**, so a restricted identifier is still validated. Verifying the wrong number is worse than not verifying.
- **The rejected value never appears in the error.** A message echoing it puts a full AADHAAR into an error response and from there into whatever logs the client's failures, which is the exposure the rule exists to prevent. `fields` names the field and the expected format, never the input.
- **`value_last4` is populated for every kind**, not only restricted ones — see [identity-schema.md](identity-schema.md) §3.7 for why the unique key needs it.

`assert_statutory_row_storable` repeats the check where the row is persisted. The redundancy is deliberate: it catches a caller that built the row some other way, and a full AADHAAR reaching the table is a legal exposure rather than a bug to be found in review later.

If a specific legal obligation to hold the full number ever appears, that is a separate, deliberate change with a vault, its own key rotation, and its own retention policy — not a column added quietly.

PAN, TAN, CIN, EIN, and company registration numbers are **business** identifiers, printed on invoices, and are stored in full. The restriction applies to personal identity numbers.

### 4.4 `company_licence`

```
company_licence
  id, tenant_id, company_id
  kind                      -- from the jurisdiction profile (§3)
  number
  issuing_authority
  premises_address_id       -- licences are usually per premises
  issued_on
  valid_from, valid_to      -- dates, not is_active
  renewal_reminder_days
  document_url
  is_primary

  UNIQUE (company_id, kind, number, valid_from)
```

**A licence is behaviour, not a text field.** Drug licences are the clearest case:

1. **Prints on the invoice.** For scheduled drugs the licence number is legally required on the document. It comes from the licence valid on the invoice's `posting_date`, not the current one.
2. **Gates the sale.** `gates: "scheduled_drug"` means posting an invoice containing a scheduled-drug item with no licence valid on that `posting_date` is **rejected**. Not warned — rejected.
3. **Expiry is a scheduled concern.** A Celery Beat job raises `notification` events at `renewal_reminder_days`. An expiry discovered at the till, mid-invoice, is a shop that has stopped trading.
4. **Never deleted.** An invoice issued under a licence must resolve it forever.

Because §2 and §4.4 both gate posting, both resolve by `posting_date`, and both must be local to the writing service, the guard lives beside `assert_postable` in the shared library:

```python
assert_company_can_issue(licences, *, country_code, posting_date, line_gates)
```

Two changes from the sketch. It takes the **rows** rather than a `company_id`, for the reason §4.2 gives. And **`document_kind` is gone**: the gate is decided entirely by the gates the *lines* carry, so a document kind was a second input that could only ever disagree with the first — and disagreeing in the permissive direction is a scheduled drug sold without a licence.

**The gate fails closed.** A `line_gates` entry that no licence kind in the jurisdiction declares is a **refusal**, not permission — so the UK profile, which declares no licences at all, cannot post a gated line rather than posting every gated line freely. Every gate on the document is checked, not only the first. `assert_licence_writable` is the write-side counterpart: a licence the profile marks `has_expiry` **must** carry `valid_to`, because left open-ended it satisfies every gate forever and turns the gate into decoration.

### 4.5 Amount presentation — a real requirement, not polish

#### Scale: storage is fixed at 4, display is configured

**Amounts and quantities both store four decimal places. Always four, everywhere, regardless of what the company displays.**

```
money     DECIMAL(19,4)  + sibling currency column
quantity  DECIMAL(19,4)
```

Four is not a maximum to be chosen per column — it is the fixed storage scale, and it must be identical across every service, every replica, and every API payload. A column declared `DECIMAL(19,2)` somewhere downstream truncates silently on insert; MariaDB rounds to the target scale without erroring, so the loss surfaces months later as a subledger that will not tie.

Why quantity needs four as much as money does: a pharma pack broken into strips, a 0.3333 hour time entry, a per-1000-units rate. Two decimals forces the rounding into the *quantity*, which then multiplies into the line amount, and the error is no longer traceable to a rounding rule.

`company.amount_precision` and `company.quantity_precision` (0–4) are **presentation/rounding configuration, not storage scale.** For the planned Catalog/Billing paths:

- amount_precision governs computed monetary line/document rounding with rounding_mode;
- quantity_precision is the default quantity presentation scale, never a stock conversion or input-granularity rule;
- native unit/price numeric context retains enough displayed/exported digits to reproduce exact transaction quantities and declared rates;
- none of these fields changes the column scale or permits silent alteration of stored/input values.

The [Product Configuration extension](catalog-product-configuration.md) adds separate accepted
quantity/price decimal places, exact increments and price-basis quantities. Rate entry may use four
decimals while monetary totals use two. Product settings cannot override company monetary rounding
or its post-use immutability. Exact API/import/export values retain their numeric context; a default
two-place quantity display cannot conceal a valid 0.001 stock quantity. This is a planned Catalog
contract, not a claim that the existing Identity API already exposes these product settings.

So a company with `amount_precision = 2` stores `1234.5000` and shows `1,234.50`. Both are `[immutable]` after first posting (§5.2) for the same reason `rounding_mode` is — change the scale and recomputed totals stop matching filed documents.

Rounding happens **once, at the documented boundary** (line total, then document total), never progressively through intermediate arithmetic. All of it goes through the `libs/platform` `Decimal` helpers with an explicit context; no service sets its own.

#### Display formats are config, resolved server-side

**Neither client formats an amount or a date from its own locale defaults.** A hardcoded `toLocaleString()` in web and a different one in mobile produce two renderings of the same invoice, and the PDF worker produces a third.

The display config resolves server-side — user preference over company default over tenant default — and both clients consume it:

```
GET /companies/{id}/display-config
  { amount_precision, quantity_precision, rounding_mode,
    digit_grouping, decimal_separator, thousands_separator, negative_format,
    currency_code, currency_symbol, currency_symbol_position,
    date_format, datetime_format, timezone, locale,
    show_amount_in_words }
```

Formatting itself is a **shared function per platform** — one in `libs/platform` for Python (PDF, exports, reports), one in the generated client package for TypeScript (web and mobile import the same one). Both are driven by this payload and both are tested against a shared fixture set, including a non-`en` locale (CLAUDE.md §7). That fixture set is what stops the three renderings drifting.

Consequence for the UI work later: components take a formatted string or the config, never a raw number plus an inline format call.

#### Words and grouping

Indian invoices print **"Rupees Twenty Three Thousand Four Hundred and Forty Paise Only"**, and the minor unit is named per currency: paise, cents, fils, satang. That name is not derivable from `minor_unit` (a digit count), so `currency` carries it ([org-model.md](org-model.md) §6.1):

```
currency  (+ these columns)
  minor_unit_name         -- "paise" | "cents" | "fils"
  minor_unit_name_plural
  major_unit_name         -- "Rupees" | "Dollars"
```

`digit_grouping` matters too: Indian lakh/crore grouping is `12,34,567`, not `1,234,567`. Getting it wrong on a printed invoice is immediately visible to every Indian user and is the kind of detail that decides whether the product feels native.

**Amount-in-words is a `libs/platform` function, not a per-client one.** Web, mobile, and the PDF worker must produce byte-identical words for the same `Decimal`, so it lives beside the money helpers with a shared fixture set — the same reasoning as the rule-tree evaluator ([custom-fields.md](custom-fields.md) §6).

### 4.6 Existing child tables

`company_address`, `company_contact`, `company_bank_account`, `company_document` are unchanged from [org-model.md](org-model.md) §4.2. Two notes:

- `company_bank_account.account_number` and `iban` are redaction targets in logs (CLAUDE.md §5.11).
- Payroll and state registrations — PF, ESI, professional tax, shops & establishment — are `company_statutory_id` rows, not columns. They are jurisdiction-specific and several are per state.

---

## 5. Behaviour — what a company *does*

### 5.1 Creation

Ordered, in one transaction plus one outbox write:

1. Validate against the jurisdiction profile for `country_code` (§3) — required statutory IDs present, regex satisfied.
2. Insert `company`, `status = active`, `visibility = listed`.
3. Insert the **first** `company_tax_registration` with `valid_from = books_begin_date`. This is what the creation form's "tax type" answer becomes — it is never a column on `company`.
4. Insert statutory IDs and licences.
5. Generate the first `fiscal_year` and its periods from `fiscal_year_start_month/_day` ([fiscal-year.md](fiscal-year.md) §2).
6. Seed the default `document_sequence` rows.
7. Assign the creating actor `company_admin` at this company's scope.
8. Emit `company.created` and the audit event **in the same transaction, via the outbox** (CLAUDE.md invariant 8, 10).

No number is allocated and no ledger row is written. A company with no postings is fully editable — which is exactly the window §5.2 closes.

### 5.2 Immutable after first posting — the critical rule

Once **any** document is posted for a company, these become immutable:

| Field | What changing it breaks |
|---|---|
| `base_currency` | Silently reinterprets every amount already stored. ₹100,000 becomes $100,000 |
| `fiscal_year_start_month` / `_day` | Periods must be regenerated; every posted document's period assignment moves; prior-year comparatives become meaningless |
| `books_begin_date` | Postings would exist before the books open |
| `amount_precision`, `quantity_precision`, `rounding_mode` | Recomputed totals stop matching filed documents (§4.5) |
| `code` | Already embedded in issued document numbers |
| `country_code` | Changes the jurisdiction profile under which existing rows were validated |
| `state_code` | Flips every issued invoice between intra-state and inter-state GST ([org-model.md](org-model.md) §6.2) |

Enforced in `domain/`, not the UI, and **not as a permission**. Nobody may change these — not a tenant admin, not a platform admin. This is the same class of rule as "a posted document in a closed period is never edited" ([field-permissions.md](field-permissions.md) §1: *domain immutability is not a permission*).

`has_posted_documents` is derived, cached on the company row as `first_posted_at`, set once by the first posting and never cleared.

Changing any of these after posting means **a new company** and a migration of opening balances — a deliberate, supported, audited operation, never a settings edit.

### 5.3 Company is replicated, not called

Every service renders company details on documents. `identity` is master; each service holds a read-only replica of the fields it needs, maintained from `company.created` / `company.updated`. No synchronous call to `identity` inside a money transaction (CLAUDE.md invariant 7).

Replica lag is benign for branding and locale. It is **not** benign for tax registration and licences, because they gate posting — so those two tables replicate with the same discipline as `fiscal_period`: publish before the change takes effect, and treat a missing replica row as a hard failure rather than an implicit allow.

### 5.4 Lifecycle

`status` ∈ `active | suspended | closed` (rule 4.12 — one mechanism, so no `is_active` here).

- `suspended` — no new documents; existing data fully readable. Reversible.
- `closed` — terminal for new activity. History stays queryable and printable forever.
- **Never hard-deleted** (CLAUDE.md invariant 12). A company referenced by a posted document cannot go away.
- Closing a company does not close its fiscal periods; those follow their own lifecycle ([fiscal-year.md](fiscal-year.md) §3).

### 5.5 Cash receipt limit

`cash_receipt_limit` defaults from the jurisdiction profile (₹2,00,000 for India, per §269ST) and may be lowered by the tenant, never raised above the profile value. Enforced in `payments` on cash-method receipts, aggregated per counterparty per day. A real statutory rule, so a real column — never a custom field ([custom-fields.md](custom-fields.md) §11).

---

## 6. Visibility — hide / unhide a company

### 6.1 What is being asked for

An owner wants a company that does not appear in the default company list, and wants something asked of them before it opens.

That is two requirements, and they need different mechanisms:

| Requirement | Mechanism |
|---|---|
| "Don't show it in the list" | `company.visibility = unlisted` — a **UI listing preference** |
| "Ask me before opening it" | **Step-up re-authentication** — a fresh auth against Authentik |
| "Not everyone may open it" | **Already built.** `role_assignment` scoped to the company ([org-model.md](org-model.md) §2.3) |

### 6.2 `visibility` is a display preference, not a security boundary

```
visibility  ∈  listed | unlisted
```

- `unlisted` companies are omitted from the default company switcher and from default list responses.
- They **are** returned when explicitly requested by id, or when the caller passes `include_unlisted=true` and holds a role on that company.
- Document this in the code where the flag is read: **`unlisted` is not access control.** The only thing that decides who reaches a company is whether they hold a scoped role assignment on it.

Treating `unlisted` as a security boundary is how it becomes one in someone's head and then gets relied upon. The API is still there; the id is guessable-adjacent; scope resolution is the control.

### 6.3 Step-up re-authentication, not a company password

For a company with `requires_step_up = true`, opening it demands a **fresh authentication of the actual user** — OIDC re-prompt against the sign-in provider (`prompt=login` / `max_age=0`; the local provider always asks for the password, so a fresh sign-in is the proof), or an MFA challenge where the provider has one. Success mints a short-lived, company-scoped session claim (suggest 15 minutes, re-challenged after).

This gives the owner exactly the felt experience they asked for — "it asks me for something before it opens" — with none of the problems below.

**Why not a per-company password:**

1. **It doesn't actually restrict anything.** The API endpoint still exists. Anyone holding `company.read` and the company id reaches the data without ever seeing the UI that prompts. A password checked in the frontend is theatre; checked in the backend it is a second authorization path that scope resolution, field policies, and permission caching know nothing about.
2. **A shared secret destroys attribution.** The audit row would read "someone who knew the password." That is worthless in the one place it matters most — and this company is, by construction, the one whose audit trail matters most.
3. **It contradicts a decision already made.** Credentials live in Authentik ([org-model.md](org-model.md) §4.3: do not store what Authentik owns). A `company.password_hash` column is a second credential store with its own rotation, reset, and brute-force surface.
4. **Operationally it decays.** Company passwords get shared over WhatsApp, reused across companies, never rotated, and survive the departure of the person who set them.

Step-up re-auth is tied to a real identity, is audited with a real `actor_user_id`, reuses the IdP, and cannot be shared.

### 6.4 Hard limits — what `unlisted` does not do

These are architectural constraints, not configuration. An `unlisted` company is a company whose *row in a dropdown* is hidden. Nothing else changes:

1. **Audit rows are written identically.** Same events, same categories, same retention, same hash chain ([audit.md](audit.md) §4.2). There is no audit-suppression flag and there will not be one.
2. **Tenant-wide reports and exports include it** for any actor authorized on that company — `tenant_auditor`, `controller`, `tenant_admin` ([roles-permissions.md](roles-permissions.md) §4). Consolidated figures are not silently short.
3. **Ledger, numbering, and period rules apply unchanged.** Same `assert_postable`, same sequences, same close and lock lifecycle.
4. **It is not excluded from statutory output.** Filings, e-invoicing, and returns are driven by tax registration, never by visibility.
5. **Every visibility change is a `security`-category audit event** (§6.5) — permanently, on the same footing as a role assignment change.

Stated plainly: visibility controls what a list renders. It does not control what the books say. A request to make a company's records absent from its own audit trail or from an authorized reader's reports is out of scope for this design.

### 6.5 Audit

| Event | Category |
|---|---|
| `visibility` changed either way, with actor and reason | `security` |
| `requires_step_up` toggled | `security` |
| Step-up challenge succeeded | `access` |
| Step-up challenge failed | `security` |
| An `unlisted` company opened, with actor and session id | `access` |

Per [audit.md](audit.md), these are append-only and the audit service holds `INSERT` and `SELECT` grants only, so none of them can be removed after the fact.

---

## 7. Permissions

Added to the catalogue ([roles-permissions.md](roles-permissions.md) §2):

```
company.tax_registration.manage
company.statutory_id.manage
company.licence.manage
company.visibility.manage
```

Assignment:

- `company_admin` — `tax_registration.manage`, `statutory_id.manage`, `licence.manage` at its own company scope
- `tenant_admin` — all four, tenant scope
- `company.visibility.manage` is **tenant scope only.** A company admin must not be able to unlist the company they administer; that is a change the tenant owner makes, and separating it keeps the audit trail meaningful.

**There is deliberately no `company.open_unlisted` permission.** Holding a scoped role on the company *is* the grant. A separate permission would imply visibility is authorization, which §6.2 says it is not.

---

## 8. Implementation order

Phases, per CLAUDE.md §2. Each ends green.

| Phase | Content |
|---|---|
| **A** | Jurisdiction profiles (§3) and the `tax_system` / `regime` catalogues in `libs/platform` — pure data plus validators, no DB. Fully unit-testable with no database (CLAUDE.md §7) |
| **B** | `company` model + migration; the §5.2 immutability guard in `domain/` with `first_posted_at`; cross-tenant isolation test |
| **C** | `company_tax_registration` + `resolve_tax_registration(...)` by `posting_date`; overlap rejection; gap returns `None` |
| **D** | `company_statutory_id`, including the restricted-storage path for AADHAAR/SSN (§4.3) — test that the full value is never persisted, logged, or returned |
| **E** | `company_licence` + `assert_company_can_issue(...)`; expiry reminder task |
| **F** | Creation orchestration (§5.1) — fiscal year, sequences, first role assignment, outbox event; idempotency key on create |
| **G** | Replication: `company.created` / `updated` events, replica tables, hard-fail on missing tax/licence replica rows |
| **H** | Visibility: `visibility`, `requires_step_up`, step-up flow against Authentik, the five audit events, and the §6.4 tests — explicitly asserting an `unlisted` company still appears in an authorized tenant-wide report |
| **I** | Web + mobile: jurisdiction-driven creation form, company switcher honouring `unlisted`, step-up prompt |

**Phase H's tests are the point of Phase H.** Assert positively that hiding does not remove audit rows and does not remove the company from an authorized reader's consolidated report. Without those, the next change to the list query quietly turns a display preference into concealment.

---

## 9. Open questions

- [ ] Pharmacy licence registration is in scope. Full product-specific posting enforcement remains separate: is §4.4 illustrative? It implies batch tracking and expiry in `catalog`, which is a significant addition
- [ ] Can `parent_company_id` cross a tax system — an Indian parent with a UK subsidiary in one tenant? Affects consolidated reporting and `reporting_currency`
- [x] `reporting_currency` is a presentation setting; it does not enable transaction FX or consolidation. Translation/rate execution is separate work; see [company setup](company-setup.md).
- [ ] Step-up session lifetime — 15 minutes assumed. Per company, or one tenant-wide setting?
- [ ] Should `requires_step_up` be settable on `listed` companies too? No reason not to, and it decouples the two concepts cleanly
- [ ] Is `verified_at` / `verification_reference` on tax registrations backed by a real verification API (GSTIN lookup, HMRC), or manual attestation for v1?
- [ ] Cash receipt limit — enforced per counterparty per day (assumed), per transaction, or per financial year?

## 10. Decision log

- 2026-10-27: `code` is **generated at creation rather than asked for** (§4.1), and the
  jurisdiction profile gained `default_features` — what a setup form offers already selected
  (§3, [company-features.md](company-features.md) §3). Neither changes a stored contract:
  `code` is still required by `POST /v1/companies`, still unique per tenant, still immutable
  after posting; a suggested capability is still enabled by its own call with its own audit
  event. Both were driven by the second
  [company creation review](company-create-ux-review.md), which also found that the console's
  shell-level `body { overflow: hidden }` made most of the wizard unreachable.

- 2026-10-24: [Company configuration](company-configuration-ui-api.md) adds scoped
  settings/directory/detail entry points and reviewed enable/disable actions. It reuses
  existing metadata-driven company editing, with safe return context. Actual feature
  changes advance the company review version so an older profile edit conflicts.
  Active status, dependencies, tax gates and first-use/pending-use locks are enforced
  under the company row lock. No model/schema change or live activation was required.

- 2026-10-23: [Company/year management](company-year-management.md) adds scoped
  Manage years links and generated-year/period pages. Creation and edits validate
  fiscal month/day together, including partial edits; impossible anchors are rejected.
  Books bootstrap initializes its required Accounting foundation and opens the period
  containing books start. Unused-book reconciliation requires a reviewed explicit command.
  New statutory/setup children require an active company under its row lock; lifecycle
  commands acquire the same lock. Existing historical child reads stay available.

- 2026-10-23: Added [company management](company-management-review.md): the console
  has a management directory and dedicated view/edit routes, alongside the existing
  creation wizard and working-company chooser. Active tenant/company grants and
  field policies govern access for every account classification. Existing-company
  writes require active status; optional `expected_updated_at` protects clients
  against stale edits. Field metadata includes native validation and custom field
  contracts. No company table change or migration was required.

- 2026-10-10: User confirmed India GST/VAT recording for Vouchers. Added a planned extension
  for statutory dates, registration/location mapping and state-specific VAT; current registry
  and implementation are unchanged. The date/registration compatibility contract is a T0 gate.
- 2026-09-11: Clarified the planned Catalog/Billing distinction between company monetary
  rounding, quantity presentation and native quantity/rate entry precision. Fixed DECIMAL(19,4)
  storage and company post-use locks remain; Product Configuration owns the new native controls.

- 2026-09-11: Added optional seeded business category/store-format references and multiple
  business-role bindings; see [company-classification.md](company-classification.md).
  Legacy industry/nature fields remain supported; classification does not drive tax or posting.

- 2026-09-11: [Company setup review](company-setup.md) documents country/currency selectors, pharmacy licence forms, validation and remaining client/Billing boundaries.

- 2026-10-05: §4.2 tax registrations ([tax-accounting-plan](tax-accounting-plan.md) Phase 1). `regime`, `number`, `jurisdiction_code` and `valid_from` joined `tax_system` as immutable after create (422, every actor). Overlap is per `(tax_system, registration class, jurisdiction)` with the class on the `Regime` catalogue, so TDS-deductor/ISD registrations coexist with the regular GSTIN. At most one `is_primary` per `(tax_system, jurisdiction)` on any date. GSTIN check character, state prefix and entity code are enforced. Amendment audit carries the changed-field set. `billing-platform` 0.27.0. Same day: the class is now stored and part of the unique key (identity revisions 0060–0063); `ecommerce_operator` is class `tcs_collector` and accepts the `C`-shaped TCS GSTIN.

### Financial-year planning decision - 2026-10-10

Corrected the fiscal UI analogy: selected year is a proposed user preference, not an
implemented year-status/current flag or a change to company calendar/books-start settings.

### Company creator access decision - 2026-10-27

Company creation now atomically gives the creator the fixed system Company
Administrator role at the new company's scope, with security outbox evidence.
Missing/inactive system-role setup aborts creation rather than leaving an owner
unable to use business masters. The wizard plans default chart/calendar, warehouse,
pricing setup using that post-create grant and checks the automatically provisioned
Default product type/group; every owning
API still resolves current permission and company scope. Tenant-wide grants and
ordinary self-assignment rules remain unchanged. Existing companies need an
explicit bounded ownership correction; revoked assignments are preserved. See
[company-owner-access.md](company-owner-access.md).

### Company product defaults decision - 2026-10-30

Catalog provisions one initially named Default product type and one Default product
group for every active company enrolled with its verified Identity source. The
normal refresh catches up existing enrolled companies and repeats safely without
duplicate masters or changed user configuration. Company creation remains native
to Identity; Catalog starter provisioning is asynchronous and the wizard waits for
readiness using bounded reads, including the type's published revision. It no
longer creates a General group from the browser. Existing General and custom masters
remain available. A named Default with another code is reused; inactive/conflicting
or unpublished defaults require review.

The [Catalog decision](catalog-product-design.md#company-starter-masters---decision-2026-10-30)
defines the safe initial revision and preservation rules. A reusable signed-source
catch-up command is documented in
[the review](company-product-defaults-review-2026-10-30.md). Live application catch-up
has not run successfully while the local Identity API is offline.

### Company display cache decision - 2026-11-01

Identity may cache only the already-authorized, field-policy-projected response of
`GET /companies/{id}/display-config`. Keys bind tenant, company, user, company and user
row versions, and the live field-access fingerprint. Redis failure falls back to the
database; committed source or policy changes select a new key. The cache never supplies
posting, tax, price, stock, permission or write validation. The API contract is unchanged.
Current field denials are reapplied on cache hits, including conditional policies and
schema-valid cache corruption. Source reloads refresh retained ORM identities.
See [company-display-cache](company-display-cache.md).
