import { describe, expect, it } from 'vitest';
import { allowedProductRequest as allowed } from '../app/lib/product-request-policy';
import { masterConfig } from '../app/lib/catalog-masters';
import { masterReturnTo } from '../app/components/CatalogMasterDirectory';
import {
  identifierBody,
  identifierLink,
  identifierReceipt,
  identifierResources,
  identifierReturn,
  initialRequirement,
  ratioPart,
  reducedRatio,
} from '../app/lib/units-identifiers';
import {
  COMPANY,
  RECORD,
  ROOT,
  SOURCE,
  fields,
  row,
} from './units-identifiers-fixtures';
const base = '/v1/companies/' + COMPANY;

describe('units and identifiers request boundary', () => {
  it.each(identifierResources)(
    'allows the supported %s workflow',
    (resource) => {
      expect(
        allowed('catalog', 'GET', base + '/' + resource + '?limit=25&sort=-id'),
      ).toBe(true);
      expect(allowed('catalog', 'POST', base + '/' + resource)).toBe(true);
      expect(
        allowed('catalog', 'GET', base + '/' + resource + '/' + RECORD),
      ).toBe(true);
      expect(
        allowed('catalog', 'PATCH', base + '/' + resource + '/' + RECORD),
      ).toBe(resource !== 'unit-conversions');
      expect(
        allowed(
          'catalog',
          'POST',
          base + '/' + resource + '/' + RECORD + '/activate',
        ),
      ).toBe(resource !== 'unit-conversions');
      expect(
        allowed('catalog', 'DELETE', base + '/' + resource + '/' + RECORD),
      ).toBe(false);
      expect(allowed('identity', 'GET', base + '/' + resource)).toBe(false);
    },
  );
  it.each([
    'unit_conversion',
    'pack_type',
    'identifier_type',
    'identifier_namespace',
    'identifier_profile',
    'identifier_profile_requirement',
  ])('allows only native %s field operations', (entity) => {
    const route = base + '/entities/catalog.' + entity + '/field-set';
    expect(allowed('catalog', 'GET', route + '?operation=create')).toBe(true);
    expect(allowed('catalog', 'GET', route + '?operation=update')).toBe(true);
    expect(allowed('catalog', 'GET', route + '?object_id=' + RECORD)).toBe(
      false,
    );
    expect(allowed('catalog', 'POST', route)).toBe(false);
  });
  it.each([
    '?q=x',
    '?limit=201',
    '?limit=0',
    '?sort=name',
    '?sort=code,name',
    '?tenant_id=' + COMPANY,
    '?is_active=true&is_active=false',
    '?is_barcode=1',
    '?offset=20',
    '?custom_filters=[]',
    '?cursor=',
  ])('rejects an unsupported type query %s', (query) =>
    expect(allowed('catalog', 'GET', base + '/identifier-types' + query)).toBe(
      false,
    ),
  );
  it('allows exact conversions and closed requirement paging without invented commands', () => {
    expect(allowed('catalog', 'POST', base + '/units/convert')).toBe(true);
    expect(allowed('catalog', 'GET', base + '/units/convert')).toBe(false);
    expect(allowed('catalog', 'POST', base + '/units/convert?q=aa')).toBe(
      false,
    );
    expect(
      allowed(
        'catalog',
        'GET',
        base + '/unit-conversions?from_unit_id=' + SOURCE,
      ),
    ).toBe(true);
    expect(allowed('catalog', 'GET', base + '/unit-conversions?q=aa')).toBe(
      false,
    );
    const rules = base + '/identifier-profiles/' + RECORD + '/requirements';
    expect(
      allowed(
        'catalog',
        'GET',
        rules +
          '?identifier_type=IMEI&namespace_rule=COMPANY&sort=identifier_type',
      ),
    ).toBe(true);
    expect(allowed('catalog', 'POST', rules)).toBe(false);
    expect(allowed('catalog', 'GET', rules + '?q=aa')).toBe(false);
    expect(
      allowed(
        'catalog',
        'GET',
        base + '/pack-types/' + RECORD + '/requirements',
      ),
    ).toBe(false);
  });
  it.each([
    '//v1/companies/',
    '/v1/companies/bad/',
    '/v1/companies/' + COMPANY + '/identifier-types/%2f',
    '/v1/companies/' + COMPANY + '/identifier-types/' + '-'.repeat(36),
    base + '/identifier-types/../pack-types',
    base + '/identifier-types?limit=25?x=1',
  ])('rejects malformed routes %s', (path) =>
    expect(allowed('catalog', 'GET', path)).toBe(false),
  );
});

describe('exact inputs, protected metadata and local navigation', () => {
  it('reduces ratios beyond JavaScript safe integers without rounding', () => {
    expect(reducedRatio('9007199254740993', '3')).toEqual({
      numerator: '3002399751580331',
      denominator: '1',
    });
    expect(ratioPart('9223372036854775807')).toBe(true);
    for (const value of [
      '9223372036854775808',
      '0',
      '-1',
      '1.5',
      '1e3',
      '01',
      12,
    ])
      expect(ratioPart(value)).toBe(false);
    expect(reducedRatio('0', '1')).toBeNull();
  });
  it('validates ratios, labels, immutable headers and supported field access', () => {
    const config = masterConfig('unit-conversions')!;
    const body = identifierBody(config, fields(config.entity), {
      from_unit_id: SOURCE,
      canonical_unit_id: ROOT,
      numerator: '9007199254740993',
      denominator: '2',
    });
    expect(body.errors).toEqual({});
    expect(body.body.numerator).toBe('9007199254740993');
    expect(
      identifierBody(config, fields(config.entity), {
        from_unit_id: SOURCE,
        canonical_unit_id: SOURCE,
        numerator: '2',
        denominator: '1',
      }).errors.numerator,
    ).toBeTruthy();
    const type = masterConfig('identifier-types')!;
    expect(
      identifierBody(
        type,
        fields(type.entity, 'update'),
        {
          ...row(type.resource),
          code: 'CHANGED',
          name: 'Renamed',
          is_barcode: true,
        },
        [],
        [],
        row(type.resource),
      ).body,
    ).toEqual({ name: 'Renamed', expected_version: 4 });
    expect(
      identifierBody(type, fields(type.entity), {
        code: 'lower',
        name: '\n',
        is_barcode: 'true',
      }).errors,
    ).toHaveProperty('is_barcode');
    const protectedFields = fields(type.entity).map((field) =>
      field.key === 'name' ? { ...field, conditional_access: true } : field,
    );
    expect(
      identifierBody(type, protectedFields, {
        code: 'TEST',
        name: 'Hidden',
        is_barcode: false,
      }).body,
    ).not.toHaveProperty('name');
  });
  it('validates bounded distinct immutable profile requirements', () => {
    const config = masterConfig('identifier-profiles')!,
      header = fields(config.entity),
      child = fields('catalog.identifier_profile_requirement');
    const valid = () =>
      identifierBody(
        config,
        header,
        { code: 'PHONE', name: 'Phone' },
        [initialRequirement()],
        child,
      );
    expect(valid().body.requirements).toEqual([
      {
        identifier_type: 'SERIAL',
        namespace_rule: 'COMPANY',
        min_count: 1,
        max_count: 1,
        requires_slot: false,
      },
    ]);
    for (const requirements of [
      [],
      [initialRequirement(), initialRequirement()],
      [{ ...initialRequirement(), max_count: '2' }],
      [{ ...initialRequirement(), min_count: '2' }],
      [
        {
          ...initialRequirement(),
          identifier_type: 'IMEI',
          namespace_rule: 'MANUFACTURER_SKU',
        },
      ],
      [{ ...initialRequirement(), max_count: '9' }],
    ])
      expect(
        Object.keys(
          identifierBody(
            config,
            header,
            { code: 'PHONE', name: 'Phone' },
            requirements,
            child,
          ).errors,
        ).length,
      ).toBeGreaterThan(0);
    expect(
      identifierBody(
        config,
        header,
        { code: 'PHONE', name: 'Phone' },
        [initialRequirement()],
        [],
      ).errors.requirements,
    ).toBeTruthy();
  });
  it('verifies company, identity and version receipts', () => {
    expect(() =>
      identifierReceipt(row('pack-types'), COMPANY, false, RECORD, 4),
    ).toThrow();
    expect(() =>
      identifierReceipt(
        { ...row('pack-types'), company_id: SOURCE },
        COMPANY,
        false,
      ),
    ).toThrow();
    expect(() =>
      identifierReceipt(row('unit-conversions'), COMPANY, true, RECORD),
    ).not.toThrow();
  });
  it('preserves bounded internal callers and removes external destinations', () => {
    const back =
      '/masters/unit-conversions?from_unit_id=' + SOURCE + '&q=wrong&limit=25';
    const detail = identifierLink('/masters/unit-conversions/' + RECORD, back);
    expect(identifierReturn(detail)).toBe(detail);
    expect(masterReturnTo(masterConfig('units')!, detail)).toBe(detail);
    for (const value of [
      'https://evil.invalid',
      '//evil.invalid',
      '/masters/unit-conversions%2fnew',
      '/masters/identifier-types/../../users',
      '/masters/identifier-types/' + RECORD + '#bad',
    ])
      expect(identifierReturn(value)).toBe('/masters/units');
    expect(identifierReturn('/settings')).toBe('/settings');
  });
});
