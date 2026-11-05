import { expect, it } from 'vitest';
import { allowedProductProfileRequest as allowed } from '../app/lib/product-profile-request-policy';
import { allowedProductRequest } from '../app/lib/product-request-policy';
import {
  productProfileResources,
  profileDefinitions,
} from '../app/lib/product-profile-resources';
import {
  profileBody,
  profileDefaults,
  profileReturn,
  profileTemperature,
  verifyProfileConditions,
  verifyProfileRevision,
} from '../app/lib/product-profiles';
import {
  COMPANY,
  RECORD,
  SOURCE,
  fields,
  revision,
  page,
} from './product-profile-fixtures';
const base = '/v1/companies/' + COMPANY;
it.each(productProfileResources)(
  'allows only native %s commands and bounded queries',
  (resource) => {
    const root = base + '/' + resource,
      entity = profileDefinitions[resource].entity;
    for (const [method, path] of [
      ['GET', root + '?q=st&is_active=true&sort=name&limit=200'],
      ['POST', root],
      ['PATCH', root + '/' + RECORD],
      ['POST', root + '/' + RECORD + '/deactivate'],
      ['POST', root + '/' + RECORD + '/revisions'],
      ['PATCH', root + '/' + RECORD + '/revisions/' + SOURCE],
      ['POST', root + '/' + RECORD + '/revisions/' + SOURCE + '/publish'],
      [
        'GET',
        base + '/entities/' + entity + '_revision/field-set?operation=publish',
      ],
    ])
      expect(allowedProductRequest('catalog', method!, path!)).toBe(true);
    for (const [method, tail] of [
      ['DELETE', ''],
      ['POST', '?limit=25'],
      ['GET', '?q=x'],
      ['GET', '?limit=201'],
      ['GET', '?sort=published_at'],
      ['GET', '?cursor='],
      ['GET', '?is_active=1'],
      ['GET', '?q=ok&q=twice'],
      ['GET', '/' + RECORD + '/revisions?q=st'],
      ['POST', '/' + RECORD + '/revisions/' + SOURCE + '/conditions'],
      ['PATCH', '/' + RECORD + '/activate'],
      ['GET', '/' + RECORD + '/revisions/' + SOURCE + '/publish'],
      ['GET', '/bad-id'],
    ])
      expect(allowed(method!, root + tail)).toBe(false);
    expect(
      allowed(
        'GET',
        base + '/entities/' + entity + '/field-set?operation=publish',
      ),
    ).toBe(false);
    expect(
      allowed(
        'GET',
        root + '/' + RECORD + '/revisions/' + SOURCE + '/conditions?limit=5',
      ),
    ).toBe(resource === 'return-policies');
  },
);
it.each([
  '//evil.test/masters/handling-profiles',
  'https://evil.test',
  '/masters/handling-profiles/../users',
  '/masters/handling-profiles/%2fusers',
  '/masters/handling-profiles#fragment',
])('rejects unsafe back navigation %s', (value) =>
  expect(profileReturn(value)).toBe('/settings'),
);
it('retains bounded directory state and clears unknown parameters', () =>
  expect(
    profileReturn(
      '/masters/handling-profiles?q=cold&is_active=true&token=secret',
    ),
  ).toBe('/masters/handling-profiles?q=cold&is_active=true'));
it.each(['-273.1500', '0', '25.1234', '999999999999999.9999', '-0.0001'])(
  'compares exact temperature %s without rounding',
  (value) => expect(profileTemperature(value)).not.toBeNull(),
);
it.each([273.15, '1e2', 'NaN', '12.12345', '1000000000000000', ' 1', '+1'])(
  'rejects invalid exact temperature %s',
  (value) => expect(profileTemperature(value)).toBeNull(),
);
it.each([
  ['inventory-templates', { shelf_life_days: '30' }],
  ['inventory-templates', { issue_strategy: 'FEFO' }],
  ['inventory-templates', { valuation_method: 'SPECIFIC' }],
  [
    'inventory-templates',
    {
      lot_tracking: true,
      expiry_required: true,
      shelf_life_days: '5',
      minimum_remaining_life_days: '6',
    },
  ],
  ['warranty-policies', { duration: '101', duration_unit: 'YEARS' }],
  ['warranty-policies', { duration: '1201', duration_unit: 'MONTHS' }],
  ['warranty-policies', { duration: '36501', duration_unit: 'DAYS' }],
  ['return-policies', { returns_allowed: true, window_days: null }],
  ['return-policies', { returns_allowed: false, window_days: '1' }],
  ['return-policies', { condition_codes: ['UNUSED', 'UNUSED'] }],
  [
    'handling-profiles',
    { temperature_min: '-273.1501', temperature_unit: 'CELSIUS' },
  ],
  [
    'handling-profiles',
    {
      temperature_min: '0.0002',
      temperature_max: '0.0001',
      temperature_unit: 'CELSIUS',
    },
  ],
  ['handling-profiles', { temperature_unit: 'CELSIUS' }],
  ['handling-profiles', { temperature_min: '1', temperature_unit: null }],
] as const)('rejects invalid %s revision rules', (resource, value) =>
  expect(
    Object.keys(
      profileBody(
        resource,
        fields(profileDefinitions[resource].entity + '_revision', 'create'),
        { ...profileDefaults[resource], ...value },
        undefined,
        true,
      ).errors,
    ).length,
  ).toBeGreaterThan(0),
);
it.each([
  [
    'inventory-templates',
    {
      lot_tracking: true,
      serial_tracking: true,
      expiry_required: true,
      shelf_life_days: '30',
      minimum_remaining_life_days: '0',
      issue_strategy: 'FEFO',
      valuation_method: 'SPECIFIC',
    },
  ],
  ['warranty-policies', { duration: '100', duration_unit: 'YEARS' }],
  ['warranty-policies', { duration: '1200', duration_unit: 'MONTHS' }],
  [
    'return-policies',
    { returns_allowed: true, window_days: '0', condition_codes: ['UNUSED'] },
  ],
  [
    'handling-profiles',
    {
      temperature_min: '-273.1500',
      temperature_max: '999999999999999.9999',
      temperature_unit: 'CELSIUS',
      instructions: 'Keep dry.\nStore upright.',
    },
  ],
] as const)('accepts valid native %s terms', (resource, value) =>
  expect(
    profileBody(
      resource,
      fields(profileDefinitions[resource].entity + '_revision', 'create'),
      { ...profileDefaults[resource], ...value },
      undefined,
      true,
    ).errors,
  ).toEqual({}),
);
it('saves only changed writable fields and exact strings', () => {
  const previous = revision('handling-profiles'),
    metadata = fields('catalog.handling_profile_revision', 'update').map(
      (field) => ({ ...field, writable: field.key === 'instructions' }),
    );
  expect(
    profileBody(
      'handling-profiles',
      metadata,
      {
        ...previous,
        instructions: '  Keep upright.\nUse care.  ',
        fragile: true,
      },
      previous,
    ).body,
  ).toEqual({ expected_version: 4, instructions: 'Keep upright.\nUse care.' });
});
it('validates a unit edit against protected temperature bounds in the API', () => {
  const previous = revision('handling-profiles');
  delete previous.temperature_min;
  delete previous.temperature_max;
  previous.temperature_unit = null;
  const metadata = fields('catalog.handling_profile_revision', 'update').filter(
    (field) => !['temperature_min', 'temperature_max'].includes(field.key),
  );
  expect(
    profileBody(
      'handling-profiles',
      metadata,
      { ...previous, temperature_unit: 'CELSIUS' },
      previous,
    ).errors,
  ).toEqual({});
});
it('does not replace protected condition sets', () => {
  const previous = {
    ...revision('return-policies'),
    condition_codes: ['UNUSED', 'UNDAMAGED'],
  };
  expect(
    profileBody(
      'return-policies',
      fields('catalog.return_policy_revision', 'update'),
      { ...previous, window_days: '15', condition_codes: [] },
      previous,
      false,
    ).body,
  ).toEqual({ expected_version: 4, window_days: 15 });
});
it('verifies complete conditions before replacing or publishing', () => {
  const valid = {
    items: [{ id: RECORD, revision_id: SOURCE, condition_code: 'UNUSED' }],
    page,
  };
  expect(verifyProfileConditions(valid, SOURCE, 1)).toEqual(['UNUSED']);
  for (const invalid of [
    { ...valid, page: { ...page, has_more: true } },
    { ...valid, items: [] },
    { ...valid, items: [{ ...valid.items[0], revision_id: RECORD }] },
    { ...valid, items: [{ ...valid.items[0], condition_code: 'UNKNOWN' }] },
  ])
    expect(() => verifyProfileConditions(invalid, SOURCE, 1)).toThrow();
});
it('rejects foreign, stale or unconfirmed publication receipts', () => {
  const current = revision('handling-profiles');
  for (const invalid of [
    { ...current, company_id: RECORD },
    { ...current, profile_id: SOURCE },
    { ...current, row_version: 0 },
    current,
  ])
    expect(() =>
      verifyProfileRevision(
        invalid,
        COMPANY,
        'handling-profiles',
        RECORD,
        SOURCE,
        true,
        4,
        true,
      ),
    ).toThrow();
  expect(() =>
    verifyProfileRevision(
      { ...current, published_at: '2026-10-25T10:00:00Z' },
      COMPANY,
      'handling-profiles',
      RECORD,
      SOURCE,
      true,
      4,
      true,
    ),
  ).not.toThrow();
});
