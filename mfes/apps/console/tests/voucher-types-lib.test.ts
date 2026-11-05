/**
 * What a voucher type's create form promises before a request is made, and what the proxy lets the
 * browser ask for. Both are checked again by the service; they are tested here because a gap in
 * either is the kind that only shows up as a refusal after the person has done the work.
 */
import { describe, expect, it } from 'vitest';
import { allowedVoucherRequest } from '../app/lib/voucher-request-policy';
import { isTypeId, typeHref, TYPES_ROOT } from '../app/lib/voucher-type-routes';
import { assertTypeRow, normaliseCode, validateCreate } from '../app/lib/voucher-types';

const COMPANY = '01990000-0000-7000-8000-00000000000c';
const OTHER = '01990000-0000-7000-8000-00000000000d';
const ID = '01990000-0000-7000-8000-0000000000a1';
const company = `/v1/companies/${COMPANY}`;
const ok = { code: 'RETAIL', name: 'Retail sales', kind: 'SALES', profile: 'STANDARD' };

describe('validateCreate', () => {
  it('has nothing to say about a complete draft', () => {
    expect(validateCreate(ok)).toEqual({});
  });

  it('saves the code in capitals, so a lower-case code is not a mistake', () => {
    expect(normaliseCode('  retail-2_x ')).toBe('RETAIL-2_X');
    expect(validateCreate({ ...ok, code: 'retail-2_x' })).toEqual({});
  });

  it.each(['', '  ', '1RETAIL', '-RETAIL', 'RE TAIL', 'RETAIL!', 'É', 'A'.repeat(41)])('refuses the code %j', (code) => {
    expect(validateCreate({ ...ok, code }).code).toBeTruthy();
  });

  it('accepts the shortest and the longest code', () => {
    expect(validateCreate({ ...ok, code: 'A' })).toEqual({});
    expect(validateCreate({ ...ok, code: 'A'.repeat(40) })).toEqual({});
  });

  it('tells a blank code from a malformed one', () => {
    expect(validateCreate({ ...ok, code: '' }).code).toBe('Enter a code.');
    expect(validateCreate({ ...ok, code: '9' }).code).toMatch(/Start with a letter/);
  });

  it('needs a name, within 120 characters once trimmed', () => {
    expect(validateCreate({ ...ok, name: '   ' }).name).toBe('Enter a name.');
    expect(validateCreate({ ...ok, name: 'x'.repeat(120) })).toEqual({});
    expect(validateCreate({ ...ok, name: `  ${'x'.repeat(120)}  ` })).toEqual({});
    expect(validateCreate({ ...ok, name: 'x'.repeat(121) }).name).toMatch(/within 120/);
  });

  it('needs a kind, and a profile once there is a kind', () => {
    expect(validateCreate({ ...ok, kind: '', profile: '' })).toEqual({ kind: 'Choose the kind of voucher this type is for.' });
    expect(validateCreate({ ...ok, profile: '' })).toEqual({ profile: 'Choose a profile.' });
  });
});

describe('assertTypeRow', () => {
  it('accepts this company’s row, and a row with the id that was asked for', () => {
    expect(() => assertTypeRow({ id: ID, company_id: COMPANY }, COMPANY)).not.toThrow();
    expect(() => assertTypeRow({ id: ID, company_id: COMPANY }, COMPANY, ID)).not.toThrow();
  });

  it.each([
    ['another company’s row', { id: ID, company_id: OTHER }, undefined],
    ['a row with no company', { id: ID }, undefined],
    ['a row with a bad id', { id: 'nope', company_id: COMPANY }, undefined],
    ['a different row from the one asked for', { id: ID, company_id: COMPANY }, '01990000-0000-7000-8000-0000000000a2'],
    ['nothing', null, undefined],
  ])('refuses %s — a reply for the company the reader just left must not be painted under this one', (_name, row, asked) => {
    expect(() => assertTypeRow(row as never, COMPANY, asked)).toThrow(expect.objectContaining({ status: 502 }));
  });
});

describe('the route values', () => {
  it('builds a type’s address and recognises an id', () => {
    expect(typeHref(ID)).toBe(`${TYPES_ROOT}/${ID}`);
    expect(isTypeId(ID)).toBe(true);
    for (const segment of ['new', 'edit', '', ID + 'x', ID.slice(1), '../' + ID]) expect(isTypeId(segment), segment).toBe(false);
  });
});

describe('the proxy', () => {
  it('lets the browser create, revise and retire a voucher type — and only by POST', () => {
    expect(allowedVoucherRequest('POST', `${company}/voucher-types`)).toBe(true);
    expect(allowedVoucherRequest('POST', `${company}/voucher-types/${ID}/revisions`)).toBe(true);
    expect(allowedVoucherRequest('POST', `${company}/voucher-types/${ID}/retire`)).toBe(true);
    for (const method of ['PUT', 'PATCH', 'DELETE']) {
      expect(allowedVoucherRequest(method, `${company}/voucher-types`), method).toBe(false);
      expect(allowedVoucherRequest(method, `${company}/voucher-types/${ID}`), method).toBe(false);
      expect(allowedVoucherRequest(method, `${company}/voucher-types/${ID}/retire`), method).toBe(false);
    }
  });

  it('still lets it read the list, one type, and the kinds', () => {
    expect(allowedVoucherRequest('GET', `${company}/voucher-types?status=ACTIVE&limit=50`)).toBe(true);
    expect(allowedVoucherRequest('GET', `${company}/voucher-types/${ID}`)).toBe(true);
    expect(allowedVoucherRequest('GET', `${company}/voucher-capabilities`)).toBe(true);
  });

  it('does not let a POST reach a single type, or anything the service does not define', () => {
    expect(allowedVoucherRequest('POST', `${company}/voucher-types/${ID}`)).toBe(false);
    expect(allowedVoucherRequest('POST', `${company}/voucher-types/${ID}/delete`)).toBe(false);
    expect(allowedVoucherRequest('POST', `${company}/voucher-types/${ID}/revisions/extra`)).toBe(false);
    expect(allowedVoucherRequest('POST', `${company}/voucher-types/not-an-id/retire`)).toBe(false);
  });

  it('keeps refusing a path that tries to leave the company', () => {
    expect(allowedVoucherRequest('POST', `${company}/voucher-types/../voucher-series`)).toBe(false);
    expect(allowedVoucherRequest('POST', `/v1/companies/${COMPANY}/voucher-types/${ID}/retire#x`)).toBe(false);
    expect(allowedVoucherRequest('POST', `/v1/companies/not-a-company/voucher-types`)).toBe(false);
  });
});
