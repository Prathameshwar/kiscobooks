# Field-Level Permissions

**Status:** Draft — design agreed, not yet modelled in code
**Date:** 2026-09-03
**Master:** `identity` · **Machinery:** `libs/platform` · **Consumers:** every service
**Related:** [org-model.md](org-model.md) §2.3, §5 · [custom-fields.md](custom-fields.md) §6 (rule tree) · [fiscal-year.md](fiscal-year.md) §4.4 · [audit.md](audit.md)

Motivating cases: a biller who may create invoices but **not change the bill date**; a biller who may not **change the price**; a clerk who may not **change an account opening balance**.

---

## 1. What this is, and what it is not

Three distinct controls, easily conflated. Keep them separate.

| Control | Question it answers | Where it lives |
|---|---|---|
| **Endpoint permission** | May this actor call `invoice.update` at all? | `role` → `permission` ([org-model](org-model.md) §2.3) |
| **Object scope** | May this actor touch *this* company's invoice? | `role_assignment` scope resolution (CLAUDE.md §5.2) |
| **Field policy** ← this doc | Within a permitted update, may this actor change *this field*? | `field_policy` |

And separately from all three:

**Domain immutability is not a permission.** Nobody may change a posted invoice's date in a closed period — that is [fiscal-year.md](fiscal-year.md) §4.4, and it applies to every actor including a platform admin. Field policy answers *who*; domain rules answer *when* and *in what state*. If the answer is "nobody, ever," it is a domain rule and belongs in `domain/`, not in a policy row an admin can delete.

**Field policy narrows; it never widens.** A policy cannot grant access to a field the actor's endpoint permission doesn't already reach. It only subtracts.

---

## 2. Protectable field registry

Not every field is policy-controlled. Making all of them controllable is a combinatorial explosion, an unreviewable admin screen, and a per-field lookup on every write.

Each service **declares in code** which of its fields can carry policies:

```python
register_protectable_fields(
    "billing.invoice",
    ["document_date", "posting_date", "due_date", "discount_pct",
     "tax_override", "narration"],
)
register_protectable_fields(
    "billing.invoice_line",
    ["unit_price", "discount_pct", "tax_code"],
)
register_protectable_fields(
    "billing.account_opening_balance",
    ["debit", "credit"],
)
```

Code-declared, for the same reasons option sources are ([custom-fields.md](custom-fields.md) §4.3):

- Bounds the surface and keeps the admin UI a short list of meaningful choices
- Makes the set of sensitive fields **reviewable in a diff**
- Stops an admin locking a field the domain requires to function — `tenant_id`, `status`, `posting_date` when it is system-derived
- Adding one is a deploy, which is correct: it is a claim about what the domain considers sensitive

**All custom fields are protectable by default**, referenced as `custom_field:<key>` — they are already admin-defined data, so there is nothing to register.

---

## 3. Table

Mastered in `identity`, replicated read-only to every service — the same pattern as permissions and custom-field definitions.

```
field_policy
  id, tenant_id
  subject_type              role | user_group | user
  subject_id
  entity_type               e.g. billing.invoice
  field_key                 native field name, or custom_field:<key>
  access                    read | write
  effect                    deny | allow
  scope_type, scope_id      tenant | company | department
  condition (JSON)          optional rule tree — §7
  reason                    free text; surfaced in the error and the audit event
  is_active                 (rule 4.12)
  created_at/by, updated_at/by

  UNIQUE (subject_type, subject_id, entity_type, field_key, access, scope_type, scope_id)
```

**Attach policies to roles, not users, as standard practice.** `subject_type = user` exists for genuine exceptions, but per-user policies do not scale and will not survive staff turnover. The maintainable expression of "user A can't change price" is a role — `biller_no_price_edit` — assigned to A.

`reason` is not decoration. "You cannot edit this field" with no explanation generates a support ticket every time; "Price changes restricted to Sales Managers (policy: margin control)" does not.

---

## 4. Semantics

**Default is allow.** If no policy matches, the actor may write the field — the endpoint permission already gated entry, and field policy is a refinement inside an existing grant. This deviates from the deny-by-default rule in CLAUDE.md §5.1 deliberately: deny-by-default at field level would mean explicitly granting every field of every entity to every role, which is unusable and would fail closed in ways nobody could debug.

**Deny wins at equal specificity.** Two policies at the same scope, one allow and one deny → deny. Fail safe.

**More specific scope wins.** A `deny` at tenant scope is overridden by an `allow` at company scope. This is the same ancestor-or-self resolution as role assignments ([org-model.md](org-model.md) §2.3), and it is the escape hatch that makes broad denies administrable — restrict globally, permit the one company that needs it.

Resolution order, for one `(field_key, access)` pair:

```
1. Gather policies where subject ∈ {actor, actor's groups, actor's assigned roles}
   AND scope is ancestor-or-self of the target object's scope
   AND is_active
   AND condition evaluates true against the object (§7)
2. Keep only those at the most specific matching scope
3. If any is deny → DENY
4. Else if any is allow → ALLOW
5. Else → ALLOW (default)
```

---

## 5. Resolution and caching

Field policies fold into the **existing permission resolution payload** ([org-model.md](org-model.md) §5.2) — the same Redis cache, keyed by user, invalidated by the same event stream. No new mechanism, no second cache to go stale.

The resolved payload gains a compact map:

```
field_policy: { "billing.invoice": { "write": {"deny": ["document_date"]},
                                     "read":  {"deny": []} } }
```

Unconditional policies resolve at cache time. Policies carrying a `condition` cannot — they depend on the object — so they are carried into the payload and evaluated per record. Keep conditional policies rare for that reason.

---

## 6. Enforcement

**Server-side, on the set of fields the request actually changes.**

```
1. Load the current persisted state of the object
2. Diff it against the incoming payload → changed_fields
3. changed_fields ∩ write-denied  →  403, listing the fields and their `reason`
4. Proceed
```

### Diff against current state, not payload presence

This is the detail that breaks naive implementations. Clients — especially the mobile client and any generated API client — routinely `PUT` the whole object, including fields the user never touched. Rejecting on *presence* means a user with any field deny cannot save the record at all.

**Reject only when the value actually differs.** Sending `document_date` unchanged is not an attempt to change it.

Corollary: comparison must be type-aware. `"100.00"` and `Decimal("100")` are the same price; `"2026-04-01"` and `date(2026,4,1)` are the same date. Coerce through the Pydantic schema *before* diffing, or every decimal field will look changed on every save.

### Where the check sits

In the shared library, called from the service's write path — one call, not per-field checks scattered through handlers:

```python
assert_fields_writable(actor, "billing.invoice", current, payload, scope)
```

Never strip denied fields silently. Silent discard means the user believes they saved a change that was thrown away — worse than an error.

### Bulk operations

Enforce per record. A bulk price update by an actor denied `unit_price` fails wholly, not partially — a half-applied bulk edit on money data is worse than a rejection.

---

## 7. Conditional policies

`condition` reuses the rule tree from [custom-fields.md](custom-fields.md) §6 — same schema, same evaluator, same shared fixtures. No second expression language.

```json
{"op": "and", "rules": [
  {"field": "status", "cmp": "ne", "value": "draft"},
  {"field": "total_amount", "cmp": "gt", "value": 100000}
]}
```

Reads as: this policy applies only once the invoice has left draft and exceeds 100,000. Below that, or while still draft, the actor may edit freely.

Fields referenceable in a condition are the entity's registered `native_fields_for_conditions` whitelist plus its custom fields — nothing else resolves, so a condition cannot probe data the admin shouldn't see.

Use sparingly. Conditional policies defeat cache-time resolution (§5) and are the hardest kind of authorization for an administrator to reason about. State-based restrictions that apply to *everyone* belong in `domain/` as immutability rules, not here.

---

## 8. Read denies

`access = read` is supported in the model from day one so the table shape never changes, but it carries a far larger blast radius than `write`:

- API serializers must omit or mask the field
- **CSV/XLSX exports must honour it**
- **`reports` must honour it** — a masked field in the UI that appears in a report export is theatre, not a control
- Invoice PDFs and any generated document must honour it
- The field must not leak through a filter, search or sort parameter — `?sort=cost_price` reveals ordering even when the value is hidden. The common enforcement contract is [api-conventions.md](api-conventions.md) §2–§3

Implement `write` first. Do not ship `read` until exports, reports, and documents all route through the same masking helper in the shared library. A read control enforced in three places out of five is worse than none, because it is trusted.

Masking convention: omit the key entirely rather than sending `null`, and have the client render "restricted" from the resolved policy — `null` is indistinguishable from an empty value.

---

## 9. Client contract

`GET /field-policy?entity_type=billing.invoice` returns the resolved map for the current actor, so both clients can disable inputs and show the `reason` as a tooltip.

**This is UX, never enforcement.** The server re-resolves and re-checks on every write (CLAUDE.md §5.5). A client that hides a field does not stop a crafted request; the §6 diff check does.

Clients must render restriction generically from the map. A client hard-coding "hide price for role X" has moved authorization into the frontend, where it cannot be audited.

---

## 10. Audit

- **Policy changes are `security`-category audit events** — they are authorization changes, and belong with role assignments in retention and access terms ([audit.md](audit.md) §3).
- **Denied write attempts are `access`-category events**, recording actor, entity, field, and policy id. A user repeatedly hitting a field deny is either a UI bug or someone probing; both are worth seeing.
- Successful changes to protected fields should be audited even where they are permitted — that is the point of marking a field sensitive in the first place.

---

## 11. Limitations

- Protectable fields are code-registered — adding one is a deploy. Deliberate (§2).
- Read denies are only as strong as the least careful export path (§8).
- Conditional policies bypass cache-time resolution and cost a rule evaluation per record.
- No field-level policy on *create* beyond required/default handling — on create there is no current state to diff, so a denied field falls back to its default and the actor cannot set it.
- Policies do not apply to system writes. Celery jobs, event consumers, and migrations act as `system` and are not subject to field policy; they are constrained by domain rules instead.
- Per-user policies are supported and discouraged (§3).

---

## 12. Open questions

- [ ] Should a denied field on **create** be rejected outright, or silently take its default? Current design says default. Rejecting may be less surprising
- [ ] Does `deny write` on a field imply `deny read`? Assumed no — you may see a price you cannot change, which is usually the point
- [ ] Approval-based override: should a denied change be submittable *for approval* rather than rejected? Real requirement in some billing shops; significant machinery
- [ ] Should field policy apply to `reports` column selection, i.e. can a user build a report over a field they cannot read? Follows from §8 but needs confirming as a product rule
- [ ] Cap on policies per role, to keep the resolved payload small
- [ ] Do we need `deny delete` at row level as a sibling concept, or is that adequately covered by endpoint permissions?

## 13. Delegation enforcement correction — 2026-10-22

Decision: direct policy changes and indirect role/group access changes use one
Identity field-authority check. The editor must hold the endpoint permission,
field-policy administration at its supported scope and the actual field access
being delegated. Conditional denies remain conservative; conditional allows do
not establish unrestricted delegation. Membership removal and role revocation
are checked too, because removing a deny may restore access. Role policies are
checked over the intersection of policy and assignment scopes.

Catalog and Vouchers policies can be updated/deactivated through the existing
policy endpoint for all registered document entities. Subject, field, access and
scope stay immutable. Updates audit before/after active state and allow/deny
effect, and a condition change as a changed-field marker — narrowing a deny's
condition relaxes it as surely as flipping the effect, while the clause itself can
name a business value and so is not stored (§10). This correction adds no entity
registrations or field-policy scope types.

Two consequences of using one check for both paths, accepted deliberately:

- **Administering an exception requires the access it concerns, in both
  directions.** This is the direct path's existing rule — creating a deny also
  requires holding the field access — so withdrawing an exception requires what
  granting it did. An exception nobody still holds the access for therefore cannot
  be withdrawn through these APIs. That was already true of the policy endpoint;
  the indirect paths now match it rather than offering a quieter way around it.
- **Only an entity this installation still carries is checked.** The direct path
  never needs this, since the request schema rejects an unknown entity. The
  indirect paths read `field_policy.entity_type` as *stored*, so a policy left
  behind by a contract revision is skipped rather than turning every edit of the
  role that carries it into a validation failure naming an entity the caller never
  mentioned. No such row can exist today — the request schema admits exactly the
  entities `registered()` accepts, and policy creation is the only writer. **A
  contract revision that drops an entity must deactivate the policies naming it**:
  a consuming service matches stored `entity_type` against its own resource list,
  not against this registry, so an orphaned row could stay enforced downstream
  while the delegation check above skips it.
See [access-control-fixes](access-control-fixes.md) for the implementation and
regression evidence.
