/**
 * The general entry rules of a voucher type, as a form can edit them.
 *
 * A type's `policy` is one document: these base controls *and* the typed sub-policies (stock,
 * invoice, order, money, manufacturing, job process, sales workflow, counter, notification). The
 * console edits only the base controls, so the one thing this module must never do is lose the
 * rest — `policyFromDraft` starts from the policy as it was read and changes the keys the form owns.
 *
 * Not a client module: it is pure, and the Server Components that gate a page may want its kinds.
 *
 * The defaults and ranges below are `vouchers/schemas/configuration.py` `Policy`, restated; the
 * service validates again and is the authority. The point of mirroring them is that a person is
 * told *which field* is wrong before a round trip, not that the console decides what is valid.
 */

export const ENTRY_MODES = [
  { value: 'ACCOUNTS', label: 'Accounts', hint: 'Ledger lines only' },
  { value: 'ITEMS', label: 'Items', hint: 'Stock items only' },
  { value: 'MIXED', label: 'Mixed', hint: 'Items and ledger lines together' },
] as const;

export const SECTIONS = [
  { value: 'ITEMS', label: 'Items' },
  { value: 'PARTIES', label: 'Parties' },
  { value: 'REFERENCES', label: 'References' },
  { value: 'ATTACHMENTS', label: 'Attachments' },
  { value: 'ACCOUNTS', label: 'Accounts' },
  { value: 'CHARGES', label: 'Charges' },
  { value: 'TAX', label: 'Tax' },
  { value: 'TENDERS', label: 'Tenders' },
  { value: 'BILL_ALLOCATIONS', label: 'Bill allocations' },
] as const;

export const PARTY_ROLES = [
  { value: 'CUSTOMER', label: 'Customer' },
  { value: 'SUPPLIER', label: 'Supplier' },
  { value: 'CONSIGNEE', label: 'Consignee' },
  { value: 'PRINCIPAL', label: 'Principal' },
  { value: 'WORKER', label: 'Worker' },
  { value: 'CARRIER', label: 'Carrier' },
  { value: 'OTHER', label: 'Other' },
] as const;

type Policy = Record<string, unknown>;

export type RulesDraft = {
  allowedModes: string[];
  defaultMode: string;
  requiredSections: string[];
  forbiddenSections: string[];
  allowedPartyRoles: string[];
  maxLines: string;
  maxParties: string;
  backdateDays: string;
  futureDays: string;
  narrationRequired: boolean;
  lineDescriptionRequired: boolean;
  supplierReferenceRequired: boolean;
  approvalRequired: boolean;
  selfApprovalAllowed: boolean;
  defaultNarration: string;
};

const all = <T extends { value: string }>(list: readonly T[]) => list.map((entry) => entry.value);

/** `Policy` field defaults, in the service's own words. */
const DEFAULTS = {
  allowed_modes: all(ENTRY_MODES),
  default_mode: 'ACCOUNTS',
  required_sections: [] as string[],
  forbidden_sections: [] as string[],
  allowed_party_roles: all(PARTY_ROLES),
  max_lines: 200,
  max_parties: 20,
  backdate_days: 3650,
  future_days: 365,
  narration_required: false,
  line_description_required: false,
  supplier_reference_required: false,
  approval_required: true,
  self_approval_allowed: false,
  default_narration: '',
};

/** The most each number may be. Zero is allowed for all of them. */
export const LIMITS = { max_lines: 200, max_parties: 20, backdate_days: 3650, future_days: 365 } as const;
export const NARRATION_MAX = 2000;

const list = (value: unknown, fallback: string[]): string[] =>
  Array.isArray(value) ? value.filter((entry): entry is string => typeof entry === 'string') : fallback;
const digits = (value: unknown, fallback: number): string => String(typeof value === 'number' ? value : fallback);
const flag = (value: unknown, fallback: boolean): boolean => (typeof value === 'boolean' ? value : fallback);

/** What the form starts from: the saved policy, with the service's default for any key it lacks. */
export function draftFromPolicy(policy: Policy | null): RulesDraft {
  const base = policy ?? {};
  const allowedModes = list(base.allowed_modes, DEFAULTS.allowed_modes);
  const savedDefault = typeof base.default_mode === 'string' ? base.default_mode : null;
  return {
    allowedModes,
    // A v2 policy may leave the default unset, which the service accepts even when ACCOUNTS is not
    // allowed; the form needs *some* selection, and the first allowed mode is the honest one.
    defaultMode: savedDefault ?? (allowedModes.includes(DEFAULTS.default_mode) ? DEFAULTS.default_mode : (allowedModes[0] ?? '')),
    requiredSections: list(base.required_sections, DEFAULTS.required_sections),
    forbiddenSections: list(base.forbidden_sections, DEFAULTS.forbidden_sections),
    allowedPartyRoles: list(base.allowed_party_roles, DEFAULTS.allowed_party_roles),
    maxLines: digits(base.max_lines, DEFAULTS.max_lines),
    maxParties: digits(base.max_parties, DEFAULTS.max_parties),
    backdateDays: digits(base.backdate_days, DEFAULTS.backdate_days),
    futureDays: digits(base.future_days, DEFAULTS.future_days),
    narrationRequired: flag(base.narration_required, DEFAULTS.narration_required),
    lineDescriptionRequired: flag(base.line_description_required, DEFAULTS.line_description_required),
    supplierReferenceRequired: flag(base.supplier_reference_required, DEFAULTS.supplier_reference_required),
    approvalRequired: flag(base.approval_required, DEFAULTS.approval_required),
    selfApprovalAllowed: flag(base.self_approval_allowed, DEFAULTS.self_approval_allowed),
    defaultNarration: typeof base.default_narration === 'string' ? base.default_narration : DEFAULTS.default_narration,
  };
}

const sameList = (left: string[], right: string[]) =>
  left.length === right.length && [...left].sort().every((entry, index) => entry === [...right].sort()[index]);

/**
 * The messages for a draft, keyed by the field they belong to. Empty means it can be sent.
 *
 * Only what the service would refuse — a person who has typed something it accepts is never told
 * it is wrong. An empty number is an error rather than zero: a blank limit is not "no limit".
 */
export function validateRules(draft: RulesDraft, kindSections?: readonly string[]): Record<string, string> {
  const errors: Record<string, string> = {};
  if (draft.allowedModes.length === 0) errors.allowedModes = 'Choose at least one entry mode.';
  else if (!draft.allowedModes.includes(draft.defaultMode)) {
    errors.defaultMode = 'The default mode must be one of the allowed modes.';
  }
  // What the kind of voucher itself can take (`kindSections` is the service's own list for it).
  if (kindSections && !errors.defaultMode && !kindSections.includes('ITEMS') && draft.defaultMode !== 'ACCOUNTS') {
    errors.defaultMode = 'This kind of voucher has no item entry, so it can only start in Accounts.';
  }
  if (kindSections) {
    const missing = draft.requiredSections.filter((section) => !kindSections.includes(section));
    if (missing.length) {
      const names = missing.map((section) => SECTIONS.find((entry) => entry.value === section)?.label ?? section);
      errors.requiredSections = `${names.join(', ')} ${missing.length === 1 ? 'is' : 'are'} not part of this kind of voucher, so ${missing.length === 1 ? 'it' : 'they'} cannot be required.`;
    }
  }
  const clash = draft.requiredSections.filter((section) => draft.forbiddenSections.includes(section));
  if (clash.length) {
    const names = clash.map((section) => SECTIONS.find((entry) => entry.value === section)?.label ?? section);
    errors.forbiddenSections = `${names.join(', ')} cannot be both required and forbidden.`;
  }
  const limits: [keyof typeof LIMITS, keyof RulesDraft][] = [
    ['max_lines', 'maxLines'],
    ['max_parties', 'maxParties'],
    ['backdate_days', 'backdateDays'],
    ['future_days', 'futureDays'],
  ];
  for (const [key, field] of limits) {
    const text = String(draft[field]).trim();
    const value = Number(text);
    // Digits only: `Number` would read "1e2" as 100 and "0x10" as 16, and what is typed is what is sent.
    if (!/^\d+$/.test(text) || value > LIMITS[key]) {
      errors[field] = `Enter a whole number from 0 to ${LIMITS[key]}.`;
    }
  }
  // Combinations the service refuses whatever the kind.
  const zero = (text: string) => /^\d+$/.test(text.trim()) && Number(text) === 0;
  if (draft.requiredSections.includes('ITEMS') && zero(draft.maxLines)) {
    errors.maxLines = 'Items are required, so the line limit cannot be zero.';
  }
  if (draft.requiredSections.includes('PARTIES') && zero(draft.maxParties)) {
    errors.maxParties = 'Parties are required, so the party limit cannot be zero.';
  }
  if (draft.forbiddenSections.includes('REFERENCES') && draft.supplierReferenceRequired) {
    errors.forbiddenSections ??= 'References cannot be forbidden while a supplier reference is required.';
  }
  if (draft.defaultNarration.length > NARRATION_MAX) {
    errors.defaultNarration = `Keep the default narration within ${NARRATION_MAX} characters.`;
  }
  return errors;
}

/**
 * The policy to send: the one that was read, with the form's keys changed.
 *
 * A key the saved policy does not carry is added only when the form moved it off the service's
 * default. A v2 policy stores *supplied* keys so that "inherited" stays distinguishable from
 * "explicitly this", and writing every default would turn each inherited value into a setting.
 */
export function policyFromDraft(saved: Policy | null, draft: RulesDraft): Policy {
  const policy: Policy = { ...(saved ?? {}) };
  const set = (key: string, value: unknown, fallback: unknown) => {
    if (key in policy || JSON.stringify(value) !== JSON.stringify(fallback)) policy[key] = value;
  };
  const sorted = (values: string[]) => [...values].sort();
  set('allowed_modes', sorted(draft.allowedModes), sorted(DEFAULTS.allowed_modes));
  // A v2 policy may leave the starting mode unset; picking a stand-in for the form must not write one.
  const standIn = !saved || !('default_mode' in saved) ? draftFromPolicy(saved).defaultMode : null;
  if (draft.defaultMode !== standIn) set('default_mode', draft.defaultMode, DEFAULTS.default_mode);
  set('required_sections', sorted(draft.requiredSections), DEFAULTS.required_sections);
  set('forbidden_sections', sorted(draft.forbiddenSections), DEFAULTS.forbidden_sections);
  set('allowed_party_roles', sorted(draft.allowedPartyRoles), sorted(DEFAULTS.allowed_party_roles));
  set('max_lines', Number(draft.maxLines), DEFAULTS.max_lines);
  set('max_parties', Number(draft.maxParties), DEFAULTS.max_parties);
  set('backdate_days', Number(draft.backdateDays), DEFAULTS.backdate_days);
  set('future_days', Number(draft.futureDays), DEFAULTS.future_days);
  set('narration_required', draft.narrationRequired, DEFAULTS.narration_required);
  set('line_description_required', draft.lineDescriptionRequired, DEFAULTS.line_description_required);
  set('supplier_reference_required', draft.supplierReferenceRequired, DEFAULTS.supplier_reference_required);
  set('approval_required', draft.approvalRequired, DEFAULTS.approval_required);
  set('self_approval_allowed', draft.selfApprovalAllowed, DEFAULTS.self_approval_allowed);
  set('default_narration', draft.defaultNarration, DEFAULTS.default_narration);
  return policy;
}

/** Whether sending the draft would change anything, so an untouched form cannot publish a no-op revision. */
export function rulesChanged(saved: Policy | null, draft: RulesDraft): boolean {
  const before = draftFromPolicy(saved);
  return (
    !sameList(before.allowedModes, draft.allowedModes) ||
    before.defaultMode !== draft.defaultMode ||
    !sameList(before.requiredSections, draft.requiredSections) ||
    !sameList(before.forbiddenSections, draft.forbiddenSections) ||
    !sameList(before.allowedPartyRoles, draft.allowedPartyRoles) ||
    before.maxLines !== draft.maxLines.trim() ||
    before.maxParties !== draft.maxParties.trim() ||
    before.backdateDays !== draft.backdateDays.trim() ||
    before.futureDays !== draft.futureDays.trim() ||
    before.narrationRequired !== draft.narrationRequired ||
    before.lineDescriptionRequired !== draft.lineDescriptionRequired ||
    before.supplierReferenceRequired !== draft.supplierReferenceRequired ||
    before.approvalRequired !== draft.approvalRequired ||
    before.selfApprovalAllowed !== draft.selfApprovalAllowed ||
    before.defaultNarration !== draft.defaultNarration
  );
}

/** The typed sub-policies a type carries that this form does not edit — named, so nothing is silently out of sight. */
const SUB_POLICIES: Record<string, string> = {
  stock: 'Stock',
  financial: 'Financial',
  invoice: 'Invoice',
  order: 'Order',
  money: 'Money',
  manufacturing: 'Manufacturing',
  job_process: 'Job process',
  sales_workflow: 'Sales workflow',
  commercial_attribution: 'Commercial attribution',
  counter: 'Counter',
  notification: 'Notification',
};

/** Restrictions a policy keeps that are not these controls either: issue series, templates, custom fields. */
const BINDINGS: [string[], string][] = [
  [['allowed_series_ids', 'default_series_id'], 'Issue series'],
  [['allowed_template_revision_ids', 'default_template_revision_id'], 'Print template'],
  [['header_field_keys', 'item_field_keys', 'required_header_fields', 'required_item_fields'], 'Custom field'],
];

const present = (value: unknown) => (Array.isArray(value) ? value.length > 0 : value != null);

export function otherControls(policy: Policy | null): string[] {
  return [
    ...Object.entries(SUB_POLICIES)
      .filter(([key]) => policy?.[key] != null)
      .map(([, label]) => label),
    ...BINDINGS.filter(([keys]) => keys.some((key) => present(policy?.[key]))).map(([, label]) => label),
  ];
}

/** A short phrase for a list of values — "Accounts, Items", or "All" when it is every choice. */
export function summarise<T extends { value: string; label: string }>(
  values: string[],
  choices: readonly T[],
  none = 'None',
): string {
  if (values.length === 0) return none;
  if (values.length === choices.length) return 'All';
  return choices
    .filter((choice) => values.includes(choice.value))
    .map((choice) => choice.label)
    .join(', ');
}
