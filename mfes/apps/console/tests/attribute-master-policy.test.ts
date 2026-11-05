import { describe, expect, it } from 'vitest';
import { allowedAttributeRequest } from '../app/lib/attribute-request-policy';
import { allowedProductRequest } from '../app/lib/product-request-policy';
import {
  attributeBody,
  attributeMemberErrors,
  attributeReturn,
  exactAttributeDecimal,
  exactAttributeInteger,
} from '../app/lib/attribute-masters';
import { masterConfig } from '../app/lib/catalog-masters';
import {
  COMPANY,
  RECORD,
  SOURCE,
  FRESH,
  definition,
  fields,
  row,
} from './attribute-master-fixtures';
const base = '/v1/companies/' + COMPANY;
describe('closed native attribute route policy', () => {
  it.each(['definitions', 'options', 'sets'])(
    'admits all native %s master methods',
    (resource) => {
      for (const [method, path] of [
        ['GET', ''],
        ['POST', ''],
        ['GET', '/' + RECORD],
        ['PATCH', '/' + RECORD],
        ['POST', '/' + RECORD + '/activate'],
        ['POST', '/' + RECORD + '/deactivate'],
      ])
        expect(
          allowedProductRequest(
            'catalog',
            method!,
            base + '/attribute-' + resource + path,
          ),
        ).toBe(true);
    },
  );
  it.each([
    ['GET', ''],
    ['POST', ''],
    ['GET', '/' + FRESH],
    ['GET', '/' + FRESH + '/members?sort=position&limit=128'],
    ['PUT', '/' + FRESH + '/members'],
    ['POST', '/' + FRESH + '/publish'],
  ])('admits revision %s %s', (method, suffix) =>
    expect(
      allowedProductRequest(
        'catalog',
        method,
        base + '/attribute-sets/' + RECORD + '/revisions' + suffix,
      ),
    ).toBe(true),
  );
  it.each([
    '?q=x',
    '?limit=201',
    '?q=blue&q=red',
    '?sort=value_text',
    '?unexpected=1',
    '?definition_id=bad',
    '?value_type=OBJECT',
    '?is_active=yes',
    '?limit=2?limit=3',
  ])('rejects bad option query %s', (suffix) =>
    expect(
      allowedProductRequest(
        'catalog',
        'GET',
        base + '/attribute-options' + suffix,
      ),
    ).toBe(false),
  );
  it.each(['?q=blue', '?sort=name', '?published=yes', '?limit=0'])(
    'rejects revision query %s',
    (suffix) =>
      expect(
        allowedProductRequest(
          'catalog',
          'GET',
          base + '/attribute-sets/' + RECORD + '/revisions' + suffix,
        ),
      ).toBe(false),
  );
  it.each(['PATCH', 'DELETE', 'PUT'])(
    'rejects unsupported revision method %s',
    (method) =>
      expect(
        allowedProductRequest(
          'catalog',
          method,
          base + '/attribute-sets/' + RECORD + '/revisions/' + FRESH,
        ),
      ).toBe(false),
  );
  it.each([
    'attribute_definition',
    'attribute_option',
    'attribute_set',
    'attribute_set_revision',
    'attribute_set_member',
  ])('closes metadata %s', (entity) => {
    const route = base + '/entities/catalog.' + entity + '/field-set';
    expect(
      allowedProductRequest('catalog', 'GET', route + '?operation=update'),
    ).toBe(true);
    expect(
      allowedProductRequest('catalog', 'GET', route + '?operation=publish'),
    ).toBe(
      entity === 'attribute_set_revision' || entity === 'attribute_set_member',
    );
    expect(
      allowedProductRequest(
        'catalog',
        'GET',
        route + '?operation=create&operation=update',
      ),
    ).toBe(false);
  });
  it('preserves product assignment and rejects route escapes', () => {
    expect(
      allowedAttributeRequest(
        'GET',
        base + '/items/' + RECORD + '/attribute-form',
      ),
    ).toBeUndefined();
    expect(
      allowedProductRequest(
        'catalog',
        'GET',
        base + '/items/' + RECORD + '/attribute-form',
      ),
    ).toBe(true);
    for (const path of [
      '//api.invalid' + base + '/attribute-options',
      base + '/attribute-sets/' + RECORD + '/revisions/../../items',
      base + '/attribute-options/%2f',
      base.replace(COMPANY, '-'.repeat(36)) + '/attribute-options',
    ])
      expect(allowedProductRequest('catalog', 'GET', path)).toBe(false);
  });
});
describe('exact values, changed fields and safe navigation', () => {
  it.each([
    '0',
    '-0',
    '9007199254740993',
    '-9223372036854775808',
    '9223372036854775807',
  ])('retains integer %s exactly', (value) =>
    expect(exactAttributeInteger(value)).toBe(true),
  );
  it.each([
    '9223372036854775808',
    '-9223372036854775809',
    '1e3',
    '1.2',
    '',
    '01',
  ])('rejects integer %s', (value) =>
    expect(exactAttributeInteger(value)).toBe(false),
  );
  it('validates decimals without rounding', () => {
    expect(exactAttributeDecimal('999999999999999.9999')).toBe(true);
    expect(exactAttributeDecimal('0.00001')).toBe(false);
    expect(exactAttributeDecimal('1e4')).toBe(false);
  });
  it('renames an option without sending protected typed values', () => {
    const previous = row('attribute-options');
    const result = attributeBody(
      masterConfig('attribute-options')!,
      fields('attribute_option', 'update').filter(
        (field) => !field.key.startsWith('value_'),
      ),
      { ...previous, name: 'Renamed' },
      previous,
    );
    expect(result).toEqual({
      body: { expected_version: 4, name: 'Renamed' },
      errors: {},
    });
  });
  it('checks duplicate definitions and variant eligibility', () => {
    const member = {
      definition_id: SOURCE,
      position: 0,
      is_required: true,
      allow_variant_axis: true,
    };
    expect(
      attributeMemberErrors([member, member], {
        [SOURCE]: { ...definition(), is_variant_capable: false },
      }),
    ).toHaveProperty('members.1.definition_id');
    expect(attributeMemberErrors([], {}, true).members).toMatch(/at least one/);
  });
  it('keeps template callers and strips external redirects', () => {
    const route = '/masters/attribute-sets/' + RECORD + '/revisions/' + FRESH;
    expect(attributeReturn(route)).toBe(route);
    expect(attributeReturn('https://evil.invalid')).toBe('/settings');
    expect(
      attributeReturn('/masters/attribute-options?definition_id=' + SOURCE),
    ).toContain(SOURCE);
  });
});
