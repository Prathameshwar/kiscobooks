/**
 * The general entry rules of a voucher type, as a form edits them.
 *
 * What can go wrong here is not the form but the *document*: a type's policy carries typed
 * sub-policies the form never shows, and a policy saved in the service's v2 form stores only the
 * keys somebody supplied, so that "inherited" stays different from "explicitly this". A save that
 * flattened either would change a type in ways nobody asked for, so most of these pin what is left
 * alone.
 */
import { describe, expect, it } from 'vitest';
import {
  ENTRY_MODES,
  PARTY_ROLES,
  SECTIONS,
  draftFromPolicy,
  otherControls,
  policyFromDraft,
  rulesChanged,
  summarise,
  validateRules,
  type RulesDraft,
} from '../app/lib/voucher-type-policy';

const v1 = {
  schema_version: 1,
  allowed_modes: ['ACCOUNTS', 'ITEMS', 'MIXED'],
  required_sections: [],
  forbidden_sections: [],
  max_lines: 200,
  max_parties: 20,
  narration_required: false,
  line_description_required: false,
  approval_required: true,
  self_approval_allowed: false,
  backdate_days: 3650,
  future_days: 365,
  supplier_reference_required: false,
  allowed_party_roles: ['CARRIER', 'CONSIGNEE', 'CUSTOMER', 'OTHER', 'PRINCIPAL', 'SUPPLIER', 'WORKER'],
  default_mode: 'ACCOUNTS',
  default_narration: '',
};

const base = (): RulesDraft => draftFromPolicy(null);

describe('draftFromPolicy', () => {
  it('starts from the service’s own defaults when there is no policy', () => {
    expect(base()).toEqual({
      allowedModes: ['ACCOUNTS', 'ITEMS', 'MIXED'],
      defaultMode: 'ACCOUNTS',
      requiredSections: [],
      forbiddenSections: [],
      allowedPartyRoles: PARTY_ROLES.map((role) => role.value),
      maxLines: '200',
      maxParties: '20',
      backdateDays: '3650',
      futureDays: '365',
      narrationRequired: false,
      lineDescriptionRequired: false,
      supplierReferenceRequired: false,
      approvalRequired: true,
      selfApprovalAllowed: false,
      defaultNarration: '',
    });
  });

  it('reads what a saved policy says and fills only the gaps', () => {
    const draft = draftFromPolicy({ allowed_modes: ['ITEMS'], default_mode: 'ITEMS', max_lines: 12, approval_required: false, required_sections: ['TAX'] });

    expect(draft).toMatchObject({
      allowedModes: ['ITEMS'],
      defaultMode: 'ITEMS',
      maxLines: '12',
      approvalRequired: false,
      requiredSections: ['TAX'],
      // not in the policy → the default
      maxParties: '20',
      futureDays: '365',
    });
  });

  it('picks the first allowed mode when a v2 policy leaves the default unset and ACCOUNTS is not allowed', () => {
    // The service accepts this; a form needs *some* selection, and the first allowed mode is the honest one.
    expect(draftFromPolicy({ schema_version: 2, allowed_modes: ['ITEMS', 'MIXED'] }).defaultMode).toBe('ITEMS');
  });

  it('ignores values of the wrong type rather than showing them', () => {
    const draft = draftFromPolicy({ max_lines: '12', approval_required: 'yes', allowed_modes: 'ITEMS', default_narration: 4 });

    expect(draft).toMatchObject({ maxLines: '200', approvalRequired: true, allowedModes: ['ACCOUNTS', 'ITEMS', 'MIXED'], defaultNarration: '' });
  });
});

describe('validateRules', () => {
  it('has nothing to say about the defaults', () => {
    expect(validateRules(base())).toEqual({});
  });

  it('asks for at least one entry mode, and says nothing else about the default then', () => {
    expect(validateRules({ ...base(), allowedModes: [] })).toEqual({ allowedModes: 'Choose at least one entry mode.' });
  });

  it('needs the starting mode to be one of the allowed ones', () => {
    expect(validateRules({ ...base(), allowedModes: ['ITEMS'], defaultMode: 'ACCOUNTS' })).toEqual({
      defaultMode: 'The default mode must be one of the allowed modes.',
    });
  });

  it('refuses a section that is both required and forbidden, naming it', () => {
    expect(validateRules({ ...base(), requiredSections: ['TAX', 'ITEMS'], forbiddenSections: ['TAX'] })).toEqual({
      forbiddenSections: 'Tax cannot be both required and forbidden.',
    });
  });

  it.each([
    ['maxLines', '200', '201'],
    ['maxParties', '20', '21'],
    ['backdateDays', '3650', '3651'],
    ['futureDays', '365', '366'],
  ] as const)('accepts 0 and the most for %s, and refuses one more', (field, most, over) => {
    expect(validateRules({ ...base(), [field]: '0' })).toEqual({});
    expect(validateRules({ ...base(), [field]: most })).toEqual({});
    expect(validateRules({ ...base(), [field]: over })[field]).toMatch(/whole number from 0 to /);
  });

  it.each(['', '  ', '-1', '1.5', 'abc', '1e2', '0x10'])('refuses %j as a limit — blank is not “no limit”', (value) => {
    expect(validateRules({ ...base(), maxLines: value }).maxLines).toBe('Enter a whole number from 0 to 200.');
  });

  it('keeps the default narration within the service’s length', () => {
    expect(validateRules({ ...base(), defaultNarration: 'x'.repeat(2000) })).toEqual({});
    expect(validateRules({ ...base(), defaultNarration: 'x'.repeat(2001) }).defaultNarration).toMatch(/within 2000 characters/);
  });

  it('reports every wrong field at once', () => {
    const errors = validateRules({ ...base(), allowedModes: [], maxLines: 'x', futureDays: '-3' });
    expect(Object.keys(errors).sort()).toEqual(['allowedModes', 'futureDays', 'maxLines']);
  });
});

describe('validateRules for a kind of voucher', () => {
  // The service's own sections for a Receipt: no items, charges or tax.
  const receipt = ['ACCOUNTS', 'ATTACHMENTS', 'BILL_ALLOCATIONS', 'PARTIES', 'REFERENCES', 'TENDERS'];
  const sales = [...receipt, 'ITEMS', 'CHARGES', 'TAX'];

  it('has nothing to say about the defaults for any kind', () => {
    expect(validateRules(base(), receipt)).toEqual({});
    expect(validateRules(base(), sales)).toEqual({});
  });

  it('lets a kind with no item entry start only in Accounts', () => {
    expect(validateRules({ ...base(), defaultMode: 'MIXED' }, receipt).defaultMode).toBe('This kind of voucher has no item entry, so it can only start in Accounts.');
    expect(validateRules({ ...base(), defaultMode: 'MIXED' }, sales)).toEqual({});
  });

  it('does not pile a second message on a default mode that is already wrong', () => {
    expect(validateRules({ ...base(), allowedModes: ['ACCOUNTS'], defaultMode: 'MIXED' }, receipt).defaultMode).toBe('The default mode must be one of the allowed modes.');
  });

  it('refuses to require a section the kind does not have, naming it', () => {
    expect(validateRules({ ...base(), requiredSections: ['ITEMS', 'TAX'] }, receipt).requiredSections).toBe('Items, Tax are not part of this kind of voucher, so they cannot be required.');
    expect(validateRules({ ...base(), requiredSections: ['TAX'] }, receipt).requiredSections).toBe('Tax is not part of this kind of voucher, so it cannot be required.');
    expect(validateRules({ ...base(), requiredSections: ['TAX'] }, sales)).toEqual({});
  });

  it('says nothing about kinds it was not told about', () => {
    expect(validateRules({ ...base(), requiredSections: ['TAX'], defaultMode: 'MIXED' })).toEqual({});
  });

  it('refuses required items with no lines, and required parties with no parties — for any kind', () => {
    expect(validateRules({ ...base(), requiredSections: ['ITEMS'], maxLines: '0' }).maxLines).toBe('Items are required, so the line limit cannot be zero.');
    expect(validateRules({ ...base(), requiredSections: ['PARTIES'], maxParties: '0' }).maxParties).toBe('Parties are required, so the party limit cannot be zero.');
    expect(validateRules({ ...base(), maxLines: '0', maxParties: '0' })).toEqual({});
  });

  it('refuses to forbid references while a supplier reference is required', () => {
    expect(validateRules({ ...base(), forbiddenSections: ['REFERENCES'], supplierReferenceRequired: true }).forbiddenSections).toBe(
      'References cannot be forbidden while a supplier reference is required.',
    );
    expect(validateRules({ ...base(), forbiddenSections: ['REFERENCES'] })).toEqual({});
  });

  it('keeps the clash message when a section is both required and forbidden', () => {
    const errors = validateRules({ ...base(), requiredSections: ['REFERENCES'], forbiddenSections: ['REFERENCES'], supplierReferenceRequired: true });
    expect(errors.forbiddenSections).toBe('References cannot be both required and forbidden.');
  });
});

describe('policyFromDraft', () => {
  it('passes the typed sub-policies and unknown keys through untouched', () => {
    const saved = { ...v1, schema_version: 2, stock: { reserve: true }, invoice: { rounding: 'LINE' }, future_key: [1, 2] };
    const policy = policyFromDraft(saved, { ...draftFromPolicy(saved), maxLines: '50' });

    expect(policy.stock).toEqual({ reserve: true });
    expect(policy.invoice).toEqual({ rounding: 'LINE' });
    expect(policy.future_key).toEqual([1, 2]);
    expect(policy.max_lines).toBe(50);
  });

  it('does not mutate the policy it was given', () => {
    const saved = { ...v1 };
    policyFromDraft(saved, { ...base(), maxLines: '5' });
    expect(saved).toEqual(v1);
  });

  it('writes a v1 policy in full, as numbers and sorted lists', () => {
    const policy = policyFromDraft(v1, { ...base(), allowedModes: ['MIXED', 'ITEMS'], defaultMode: 'ITEMS', maxParties: '3', requiredSections: ['TAX', 'ITEMS'] });

    expect(policy).toMatchObject({
      allowed_modes: ['ITEMS', 'MIXED'],
      default_mode: 'ITEMS',
      max_parties: 3,
      required_sections: ['ITEMS', 'TAX'],
    });
    expect(Object.keys(policy).sort()).toEqual(Object.keys(v1).sort());
  });

  it('leaves a v2 key absent while the form still agrees with the default', () => {
    // v2 stores supplied keys only, so "inherited" and "explicitly the default" are different things.
    const saved = { schema_version: 2, max_lines: 10 };
    const policy = policyFromDraft(saved, { ...draftFromPolicy(saved), futureDays: '365' });

    expect(policy).toEqual({ schema_version: 2, max_lines: 10 });
  });

  it('adds a v2 key once the form moves it off the default', () => {
    const saved = { schema_version: 2, max_lines: 10 };
    const policy = policyFromDraft(saved, { ...draftFromPolicy(saved), futureDays: '30', narrationRequired: true });

    expect(policy).toMatchObject({ schema_version: 2, max_lines: 10, future_days: 30, narration_required: true });
    expect('backdate_days' in policy).toBe(false);
  });

  it('does not write a starting mode the form only chose as a stand-in', () => {
    // The service accepts a v2 policy with no default mode even when ACCOUNTS is not allowed; the form shows the
    // first allowed mode for want of a blank, and an unrelated edit must not turn that into a setting.
    const saved = { schema_version: 2, allowed_modes: ['ITEMS', 'MIXED'] };
    const policy = policyFromDraft(saved, { ...draftFromPolicy(saved), maxLines: '5' });

    expect(policy).toEqual({ schema_version: 2, allowed_modes: ['ITEMS', 'MIXED'], max_lines: 5 });
    expect('default_mode' in policy).toBe(false);
  });

  it('writes the starting mode once somebody chooses it', () => {
    const saved = { schema_version: 2, allowed_modes: ['ITEMS', 'MIXED'] };
    expect(policyFromDraft(saved, { ...draftFromPolicy(saved), defaultMode: 'MIXED' }).default_mode).toBe('MIXED');
  });

  it('keeps a key the saved policy already carries even if it now equals the default', () => {
    const policy = policyFromDraft({ schema_version: 2, max_lines: 10 }, { ...base(), maxLines: '200' });
    expect(policy.max_lines).toBe(200);
  });
});

describe('rulesChanged', () => {
  it('is false for an untouched draft, whatever order its lists are in', () => {
    expect(rulesChanged(v1, draftFromPolicy(v1))).toBe(false);
    expect(rulesChanged(v1, { ...draftFromPolicy(v1), allowedModes: ['MIXED', 'ITEMS', 'ACCOUNTS'] })).toBe(false);
    expect(rulesChanged(null, base())).toBe(false);
  });

  it.each([
    ['allowedModes', ['ITEMS']],
    ['requiredSections', ['TAX']],
    ['forbiddenSections', ['TAX']],
    ['allowedPartyRoles', ['CUSTOMER']],
    ['maxLines', '10'],
    ['maxParties', '10'],
    ['backdateDays', '10'],
    ['futureDays', '10'],
    ['narrationRequired', true],
    ['lineDescriptionRequired', true],
    ['supplierReferenceRequired', true],
    ['approvalRequired', false],
    ['selfApprovalAllowed', true],
    ['defaultNarration', 'Goods as per order'],
  ] as const)('is true when %s changes', (field, value) => {
    expect(rulesChanged(v1, { ...draftFromPolicy(v1), [field]: value })).toBe(true);
  });

  it('is true when only the starting mode changes', () => {
    expect(rulesChanged(v1, { ...draftFromPolicy(v1), defaultMode: 'ITEMS' })).toBe(true);
  });

  it('does not count surrounding spaces in a number as a change', () => {
    expect(rulesChanged(v1, { ...draftFromPolicy(v1), maxLines: ' 200 ' })).toBe(false);
  });
});

describe('otherControls and summarise', () => {
  it('names the typed sub-policies a type carries, and nothing it does not', () => {
    expect(otherControls({ stock: {}, job_process: { role: 'WORKER' }, order: null, money: undefined })).toEqual(['Stock', 'Job process']);
    expect(otherControls(null)).toEqual([]);
  });

  it('also names the issue-series, print-template and custom-field restrictions it keeps', () => {
    expect(otherControls({ allowed_series_ids: ['01990000-0000-7000-8000-0000000000f1'] })).toEqual(['Issue series']);
    expect(otherControls({ default_template_revision_id: '01990000-0000-7000-8000-0000000000f2', required_item_fields: ['cf_batch'] })).toEqual([
      'Print template',
      'Custom field',
    ]);
    // An empty list is no restriction, and so not worth a line.
    expect(otherControls({ required_header_fields: [], header_field_keys: null, allowed_series_ids: null })).toEqual([]);
  });

  it('says All for every choice, None for no choice, and names a subset', () => {
    expect(summarise(['ACCOUNTS', 'ITEMS', 'MIXED'], ENTRY_MODES)).toBe('All');
    expect(summarise([], SECTIONS)).toBe('None');
    expect(summarise([], SECTIONS, 'Nothing')).toBe('Nothing');
    expect(summarise(['TAX', 'ITEMS'], SECTIONS)).toBe('Items, Tax');
  });
});
