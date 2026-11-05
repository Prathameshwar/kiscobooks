/**
 * How a rule is described, and which rule is a kind's default.
 *
 * Two screens read these — the routing page and a voucher kind's print page — and both used to
 * describe a rule by three of its five criteria. A rule scoped to a voucher type or a branch read
 * as "Any", which is the word for *the default*, so it looked like the kind's default and was
 * counted as one.
 */
import { describe, expect, it } from 'vitest';
import {
  compareRules,
  isDefaultRule,
  isPublished,
  layoutInUse,
  ruleConditions,
  sameCriteria,
} from '../app/lib/design-routing';

const base = {
  id: '01990000-0000-7000-8000-0000000000a1',
  company_id: '01990000-0000-7000-8000-00000000000c',
  voucher_kind: 'SALES',
  template_id: '01990000-0000-7000-8000-000000000001',
  priority: 100,
  is_active: true,
  created_at: '2026-10-27T00:00:00Z',
};
const TYPE = '01990000-0000-7000-8000-0000000000e1';
const BRANCH = '01990000-0000-7000-8000-0000000000e2';

describe('ruleConditions', () => {
  it('says Any for a rule with no criteria — the kind’s default', () => {
    expect(ruleConditions(base as never)).toBe('Any');
  });

  it('names every criterion a rule narrows on, in a fixed order', () => {
    const rule = {
      ...base,
      voucher_type_id: TYPE,
      branch_id: BRANCH,
      currency_code: 'USD',
      customer_tax_category: 'export',
      specific_version_id: '01990000-0000-7000-8000-0000000000f1',
    };
    expect(ruleConditions(rule as never)).toBe(
      'Specific voucher type · Specific branch · Currency USD · Tax category export · Pinned to one version',
    );
  });

  it.each([
    ['a voucher type', { voucher_type_id: TYPE }, 'Specific voucher type'],
    ['a branch', { branch_id: BRANCH }, 'Specific branch'],
  ])('does not call a rule scoped to %s “Any”', (_name, extra, words) => {
    expect(ruleConditions({ ...base, ...extra } as never)).toBe(words);
  });
});

describe('isDefaultRule', () => {
  it('is true only when none of the four criteria the service compares is set', () => {
    expect(isDefaultRule(base as never)).toBe(true);
    // null is how the service sends an absent criterion.
    expect(
      isDefaultRule({ ...base, voucher_type_id: null, branch_id: null, currency_code: null, customer_tax_category: null } as never),
    ).toBe(true);
  });

  it.each([
    ['voucher type', { voucher_type_id: TYPE }],
    ['branch', { branch_id: BRANCH }],
    ['currency', { currency_code: 'INR' }],
    ['tax category', { customer_tax_category: 'b2b' }],
  ])('is false once a %s is set', (_name, extra) => {
    expect(isDefaultRule({ ...base, ...extra } as never)).toBe(false);
  });

  it('is not changed by pinning a version, which the service does not compare', () => {
    expect(isDefaultRule({ ...base, specific_version_id: '01990000-0000-7000-8000-0000000000f1' } as never)).toBe(true);
  });
});

describe('compareRules — the order the service resolves in', () => {
  const rule = (overrides: Record<string, unknown> = {}) => ({ ...base, ...overrides }) as never;
  const order = (...rules: never[]) => [...rules].sort(compareRules);

  it('puts priority before how many criteria a rule pins', () => {
    const specific = rule({ id: 'a', priority: 100, currency_code: 'USD', customer_tax_category: 'B2B' });
    const general = rule({ id: 'b', priority: 200 });

    expect(order(specific, general).map((r) => (r as { id: string }).id)).toEqual(['b', 'a']);
  });

  it('breaks a priority tie by how many criteria are pinned', () => {
    const specific = rule({ id: 'a', currency_code: 'USD' });
    const general = rule({ id: 'b' });

    expect(order(general, specific).map((r) => (r as { id: string }).id)).toEqual(['a', 'b']);
  });

  it('breaks that tie by the newer rule, then by the larger id', () => {
    const older = rule({ id: 'a', created_at: '2026-10-26T00:00:00Z' });
    const newer = rule({ id: 'b', created_at: '2026-10-27T00:00:00Z' });
    const sameTimeLargerId = rule({ id: 'c', created_at: '2026-10-27T00:00:00Z' });

    expect(order(older, newer, sameTimeLargerId).map((r) => (r as { id: string }).id)).toEqual(['c', 'b', 'a']);
  });

  it('counts only the four criteria the service counts', () => {
    const pinnedToAVersion = rule({ id: 'a', specific_version_id: '01990000-0000-7000-8000-0000000000f1' });
    const plain = rule({ id: 'b', created_at: '2026-10-28T00:00:00Z' });

    // Equal on everything the service counts, so the newer wins — a version pin does not make a rule more specific.
    expect(order(pinnedToAVersion, plain).map((r) => (r as { id: string }).id)).toEqual(['b', 'a']);
  });
});

describe('isPublished', () => {
  it('needs the template to be published and to have a version', () => {
    expect(isPublished({ status: 'PUBLISHED', current_version_id: 'v' } as never)).toBe(true);
    expect(isPublished({ status: 'PUBLISHED', current_version_id: null } as never)).toBe(false);
    expect(isPublished({ status: 'DRAFT', current_version_id: 'v' } as never)).toBe(false);
    expect(isPublished(undefined)).toBe(false);
  });
});

describe('sameCriteria — what the service’s duplicate check compares', () => {
  const rule = (overrides: Record<string, unknown> = {}) => ({ ...base, ...overrides }) as never;

  it('is the same company and the same four criteria, whatever the template or priority', () => {
    expect(sameCriteria(rule(), rule({ id: 'x', template_id: 'other', priority: 7 }))).toBe(true);
    expect(sameCriteria(rule({ currency_code: 'USD' }), rule({ currency_code: 'USD' }))).toBe(true);
  });

  it('treats an absent criterion and a null one as the same', () => {
    expect(sameCriteria(rule({ currency_code: null }), rule())).toBe(true);
  });

  it('differs on any criterion, or on the company', () => {
    expect(sameCriteria(rule({ currency_code: 'USD' }), rule())).toBe(false);
    expect(sameCriteria(rule({ customer_tax_category: 'B2B' }), rule())).toBe(false);
    expect(sameCriteria(rule({ voucher_type_id: TYPE }), rule())).toBe(false);
    expect(sameCriteria(rule({ branch_id: BRANCH }), rule())).toBe(false);
    expect(sameCriteria(rule({ company_id: '00000000-0000-0000-0000-000000000000' }), rule())).toBe(false);
  });
});

describe('layoutInUse — what an ordinary document prints on', () => {
  const COMPANY = base.company_id;
  const ORG = '00000000-0000-0000-0000-000000000000';
  const published = { status: 'PUBLISHED', current_version_id: 'v' };
  const draft = { status: 'DRAFT', current_version_id: null };
  const templates = (map: Record<string, unknown>) => new Map(Object.entries(map)) as never;
  const rule = (overrides: Record<string, unknown> = {}) => ({ ...base, ...overrides }) as never;

  it('is the standard layout — no winner — when nothing is in force', () => {
    expect(layoutInUse([], templates({}), COMPANY)).toEqual({ winner: undefined, without: undefined, special: false });
  });

  it('is the default rule in force on a published template', () => {
    const own = rule({ template_id: 't1' });

    expect(layoutInUse([own], templates({ t1: published }), COMPANY).winner).toBe(own);
  });

  it('skips a retired rule and a rule on a draft, so the next candidate applies', () => {
    const retired = rule({ id: 'r', template_id: 't1', is_active: false, priority: 900 });
    const onDraft = rule({ id: 'd', template_id: 't2', priority: 500 });
    const live = rule({ id: 'l', template_id: 't1', priority: 100 });

    expect(layoutInUse([retired, onDraft, live], templates({ t1: published, t2: draft }), COMPANY).winner).toBe(live);
  });

  it('skips a rule whose template is not in the list', () => {
    expect(layoutInUse([rule({ template_id: 'gone' })], templates({}), COMPANY).winner).toBeUndefined();
  });

  it('lets a default set for the whole organisation outrank the company’s own', () => {
    const own = rule({ id: 'own', template_id: 't1', priority: 100 });
    const org = rule({ id: 'org', template_id: 't2', company_id: ORG, priority: 300 });

    const { winner, without } = layoutInUse([own, org], templates({ t1: published, t2: published }), COMPANY);

    expect(winner).toBe(org);
    expect(without).toBe(org);
  });

  it('lets the newer of two equal defaults win, whoever owns it', () => {
    const org = rule({ id: 'org', template_id: 't2', company_id: ORG, created_at: '2026-10-26T00:00:00Z' });
    const own = rule({ id: 'own', template_id: 't1', created_at: '2026-10-27T00:00:00Z' });

    expect(layoutInUse([org, own], templates({ t1: published, t2: published }), COMPANY).winner).toBe(own);
  });

  it('reports what would decide it were the company’s own defaults retired', () => {
    const own = rule({ id: 'own', template_id: 't1', priority: 500 });
    const org = rule({ id: 'org', template_id: 't2', company_id: ORG, priority: 100 });

    const { winner, without } = layoutInUse([own, org], templates({ t1: published, t2: published }), COMPANY);

    expect(winner).toBe(own);
    expect(without).toBe(org);
  });

  it('knows a rule for particular documents is in force without letting it decide the ordinary layout', () => {
    const usd = rule({ template_id: 't1', currency_code: 'USD' });

    expect(layoutInUse([usd], templates({ t1: published }), COMPANY)).toEqual({ winner: undefined, without: undefined, special: true });
  });

  it('does not count a particular-case rule that is retired or on a draft', () => {
    const retired = rule({ id: 'a', template_id: 't1', currency_code: 'USD', is_active: false });
    const onDraft = rule({ id: 'b', template_id: 't2', currency_code: 'EUR' });

    expect(layoutInUse([retired, onDraft], templates({ t1: published, t2: draft }), COMPANY).special).toBe(false);
  });
});
