/**
 * The voucher vocabulary the print pages are built from.
 *
 * It is restated in the console rather than fetched, so the one thing that can go wrong with it is
 * drifting from the list the `vouchers` service defines — a kind missing here has no card and no
 * routing option, and nothing would say so. The first test reads the service's own registry and
 * compares; the rest pin the grouping and the URL segment, which is what keeps a card from being
 * listed twice, not at all, or under a path that 404s.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { allowedDesignRequest } from '../app/lib/design-request-policy';
import {
  VOUCHER_KINDS,
  VOUCHER_KIND_GROUPS,
  kindFromSlug,
  kindLabel,
  kindSlug,
  kindSummary,
  profileLabel,
} from '../app/lib/voucher-kinds';

const REGISTRY = join(__dirname, '..', '..', '..', '..', 'apis', 'vouchers', 'src', 'vouchers', 'domain', 'registry.py');

describe('the vocabulary', () => {
  it('lists exactly the kinds the vouchers service defines', () => {
    // A registry row is `("CODE", "FAMILY", ("SECTION", ...), ...` — whatever the family is called. The
    // section tuple that follows it is what tells a row from a section list such as
    // `("ITEMS", "INVENTORY")`, so a kind in a family this test has never heard of is still counted.
    const row = /\(\s*"([A-Z][A-Z0-9_]*)",\s*"[A-Z][A-Z0-9_]*",\s*\(/g;
    const registry = [...readFileSync(REGISTRY, 'utf8').matchAll(row)].map((match) => match[1]!);

    // Not a count: the comparison below is the alarm. This only says the pattern found something.
    expect(registry.length).toBeGreaterThan(0);
    expect([...VOUCHER_KINDS.map((kind) => kind.value)].sort()).toEqual([...registry].sort());
  });

  it('has no kind twice', () => {
    const codes = VOUCHER_KINDS.map((kind) => kind.value);
    expect(new Set(codes).size).toBe(codes.length);
  });

  it('names every kind and says what it is', () => {
    for (const { value, label } of VOUCHER_KINDS) {
      expect(kindLabel(value), value).not.toBe(value);
      expect(kindSummary(value), value).not.toBe('');
      // A summary is a sentence fragment that starts a sentence.
      expect(kindSummary(value)[0], value).toBe(kindSummary(value)[0]!.toUpperCase());
      expect(label.startsWith(kindLabel(value))).toBe(true);
    }
  });

  it('falls back to the raw code for a kind it does not know', () => {
    expect(kindLabel('FUTURE_KIND')).toBe('FUTURE_KIND');
    expect(kindSummary('FUTURE_KIND')).toBe('');
  });

  it('reads the short name and the description from the one label', () => {
    expect(kindLabel('CREDIT_NOTE')).toBe('Credit note');
    expect(kindSummary('CREDIT_NOTE')).toBe('Sales return or supplier credit');
  });
});

describe('profileLabel', () => {
  it('words a service code', () => {
    expect(profileLabel('PRO_FORMA')).toBe('Pro forma');
    expect(profileLabel('STANDARD')).toBe('Standard');
    expect(profileLabel('TRANSFER_DISPATCH')).toBe('Transfer dispatch');
  });
});

describe('the console proxy', () => {
  it('lets the browser ask the design service for any kind’s rules', () => {
    // The per-kind page filters by `voucher_kind`; a kind the allowlist's pattern refuses would
    // be a card that opens onto a page which can never load.
    const company = '01990000-0000-7000-8000-00000000000c';
    for (const { value } of VOUCHER_KINDS) {
      const path = `/v1/companies/${company}/assignments?include_inactive=true&limit=200&voucher_kind=${encodeURIComponent(value)}`;
      expect(allowedDesignRequest('GET', path), value).toBe(true);
    }
  });
});

describe('the groups', () => {
  it('place every kind in exactly one group', () => {
    const grouped = VOUCHER_KIND_GROUPS.flatMap((group) => group.kinds);

    expect(new Set(grouped).size).toBe(grouped.length);
    expect([...grouped].sort()).toEqual(VOUCHER_KINDS.map((kind) => kind.value).sort());
  });

  it('follow the four families of the voucher plan, in its order', () => {
    expect(VOUCHER_KIND_GROUPS.map((group) => [group.title, group.kinds.length])).toEqual([
      ['Accounting', 8],
      ['Inventory', 8],
      ['Orders and commitments', 4],
      ['General and non-posting', 2],
    ]);
  });
});

describe('the URL segment', () => {
  it('is the kebab-case of the code', () => {
    expect(kindSlug('SALES')).toBe('sales');
    expect(kindSlug('JOB_WORK_IN_ORDER')).toBe('job-work-in-order');
  });

  it('round-trips for every kind', () => {
    for (const { value } of VOUCHER_KINDS) expect(kindFromSlug(kindSlug(value))).toBe(value);
  });

  it('refuses a segment that names no kind rather than guessing', () => {
    expect(kindFromSlug('sail')).toBeNull();
    expect(kindFromSlug('')).toBeNull();
    expect(kindFromSlug('SALES')).toBeNull();
    expect(kindFromSlug('credit_note')).toBeNull();
    expect(kindFromSlug('sales/../routing')).toBeNull();
  });
});
