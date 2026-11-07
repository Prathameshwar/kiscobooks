'use client';

import { Checkbox, FieldGroup, FieldPair, Notice, Select, TextField } from '@janso/ui';
import {
  ENTRY_MODES,
  LIMITS,
  NARRATION_MAX,
  PARTY_ROLES,
  SECTIONS,
  type RulesDraft,
} from '../lib/voucher-type-policy';

const toggle = (values: string[], value: string, on: boolean) =>
  on ? [...values.filter((entry) => entry !== value), value] : values.filter((entry) => entry !== value);

/**
 * The general entry rules of a voucher type — which modes and sections it uses, how far a date may
 * stray, and who has to approve — as one controlled form.
 *
 * Presentational: the page owns the draft, the validation and the request. The typed sub-policies a
 * type may also carry (stock, invoice, order, money…) are not here and are never touched by it.
 */
export function VoucherTypeRules({
  draft,
  errors,
  disabled = false,
  kindSections,
  onChange,
}: {
  draft: RulesDraft;
  /** Messages keyed by `RulesDraft` field, from `validateRules` — shown only once a save was tried. */
  errors: Record<string, string>;
  disabled?: boolean;
  /**
   * The sections this kind of voucher can carry, from the service's own list for it. Without it every section is
   * offered — the service still refuses what the kind cannot take, but only after the person has set it.
   */
  kindSections?: readonly string[];
  onChange: (patch: Partial<RulesDraft>) => void;
}) {
  const choices = (
    list: readonly { value: string; label: string; hint?: string }[],
    selected: string[],
    field: 'allowedModes' | 'requiredSections' | 'forbiddenSections' | 'allowedPartyRoles',
  ) => (
    // The shared form grid, so a list of nine boxes is three columns of three rather than a page of its own.
    <div className="janso-form-grid">
      {list.map((choice) => (
        <Checkbox
          key={choice.value}
          checked={selected.includes(choice.value)}
          disabled={disabled}
          hint={choice.hint}
          onChange={(event) => onChange({ [field]: toggle(selected, choice.value, event.target.checked) })}
        >
          {choice.label}
        </Checkbox>
      ))}
    </div>
  );

  const sections = kindSections ? SECTIONS.filter((section) => kindSections.includes(section.value)) : SECTIONS;
  // A kind with no item entry can only start in Accounts.
  const startModes = ENTRY_MODES.filter(
    (mode) => draft.allowedModes.includes(mode.value) && (!kindSections || kindSections.includes('ITEMS') || mode.value === 'ACCOUNTS'),
  );

  const number = (field: 'maxLines' | 'maxParties' | 'backdateDays' | 'futureDays', label: string, hint: string, max: number) => (
    <TextField
      label={label}
      hint={hint}
      value={draft[field]}
      inputMode="numeric"
      maxLength={String(max).length}
      disabled={disabled}
      error={errors[field]}
      onChange={(event) => onChange({ [field]: event.target.value })}
    />
  );

  return (
    <div className="janso-flow">
      <FieldGroup title="Entry modes" hint="What a voucher of this type may contain: ledger lines, stock items, or both.">
        {choices(ENTRY_MODES, draft.allowedModes, 'allowedModes')}
        {errors.allowedModes ? <Notice tone="danger">{errors.allowedModes}</Notice> : null}
        <Select
          label="Starts in"
          value={draft.defaultMode}
          options={startModes.map((mode) => ({ value: mode.value, label: mode.label }))}
          placeholder={draft.allowedModes.length ? undefined : 'Choose an entry mode first'}
          disabled={disabled || startModes.length === 0}
          error={errors.defaultMode}
          onChange={(defaultMode) => onChange({ defaultMode })}
        />
      </FieldGroup>

      <FieldGroup title="Sections" hint="Required means the section must contain data before submission. Selecting Charges requires an entered charge or discount on every bill. These choices do not enable charge entry or tax masters; configure invoice features separately. A section cannot be both required and forbidden.">
        <FieldGroup title="Required">{choices(sections, draft.requiredSections, 'requiredSections')}</FieldGroup>
        {errors.requiredSections ? <Notice tone="danger">{errors.requiredSections}</Notice> : null}
        <FieldGroup title="Forbidden">{choices(sections, draft.forbiddenSections, 'forbiddenSections')}</FieldGroup>
        {errors.forbiddenSections ? <Notice tone="danger">{errors.forbiddenSections}</Notice> : null}
      </FieldGroup>

      <FieldGroup title="Limits" hint="Zero is allowed for each. Dates are measured from the day the voucher is entered.">
        <FieldPair>
          {number('maxLines', 'Most lines', `Up to ${LIMITS.max_lines}.`, LIMITS.max_lines)}
          {number('maxParties', 'Most parties', `Up to ${LIMITS.max_parties}.`, LIMITS.max_parties)}
        </FieldPair>
        <FieldPair>
          {number('backdateDays', 'Days back', `How far back a voucher may be dated — up to ${LIMITS.backdate_days}.`, LIMITS.backdate_days)}
          {number('futureDays', 'Days ahead', `How far ahead — up to ${LIMITS.future_days}.`, LIMITS.future_days)}
        </FieldPair>
      </FieldGroup>

      <FieldGroup title="Approval">
        <Checkbox
          checked={draft.approvalRequired}
          disabled={disabled}
          hint="A voucher of this type must be approved before it can go further."
          onChange={(event) => onChange({ approvalRequired: event.target.checked })}
        >
          Approval required
        </Checkbox>
        <Checkbox
          checked={draft.selfApprovalAllowed}
          disabled={disabled}
          hint="Lets the person who raised a voucher approve it themselves. It only matters while approval is required."
          onChange={(event) => onChange({ selfApprovalAllowed: event.target.checked })}
        >
          Allow self-approval
        </Checkbox>
      </FieldGroup>

      <FieldGroup title="Required details">
        <Checkbox
          checked={draft.narrationRequired}
          disabled={disabled}
          onChange={(event) => onChange({ narrationRequired: event.target.checked })}
        >
          Narration
        </Checkbox>
        <Checkbox
          checked={draft.lineDescriptionRequired}
          disabled={disabled}
          onChange={(event) => onChange({ lineDescriptionRequired: event.target.checked })}
        >
          Description on every line
        </Checkbox>
        <Checkbox
          checked={draft.supplierReferenceRequired}
          disabled={disabled}
          onChange={(event) => onChange({ supplierReferenceRequired: event.target.checked })}
        >
          Supplier reference
        </Checkbox>
      </FieldGroup>

      <FieldGroup title="Parties" hint="The roles a party on this type of voucher may take.">
        {choices(PARTY_ROLES, draft.allowedPartyRoles, 'allowedPartyRoles')}
      </FieldGroup>

      <TextField
        label="Default narration"
        hint={`Filled in on a new voucher of this type. Up to ${NARRATION_MAX} characters.`}
        value={draft.defaultNarration}
        disabled={disabled}
        error={errors.defaultNarration}
        onChange={(event) => onChange({ defaultNarration: event.target.value })}
      />
    </div>
  );
}
