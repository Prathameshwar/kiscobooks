import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';

import { ProductCatalogField } from '../app/components/ProductCatalogCommon';
import { masterConfig } from '../app/lib/catalog-masters';
import { serviceCall } from '../app/lib/service-call';
import { COMPANY, RECORD, SOURCE, access, fields, response } from './product-classification-fixtures';
import { entryConfiguration, entryDefaults } from './product-entry-fixtures';
import { ProductProfileRevision } from '../app/components/ProductProfileRevision';
import { access as profileAccess, response as profileResponse } from './product-profile-fixtures';
import controls from './company-product-controls-fields.json';
import type { MasterField } from '../app/lib/catalog-masters';
let optionOverrides: Record<string, unknown>;
let invalidCompany: boolean;
let denied: string[];
const writes = () =>
  vi
    .mocked(serviceCall)
    .mock.calls.map(([, request]) => request)
    .filter((request) =>
      ['POST', 'PATCH', 'PUT'].includes(request.method ?? 'GET'),
    );
vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
beforeEach(() => {
  vi.clearAllMocks();
  optionOverrides = {};
  invalidCompany = false;
  denied = [];
  vi.mocked(serviceCall).mockImplementation(async (_, request) => {
    const url = new URL(request.path, 'https://console.invalid');
    if (url.pathname.endsWith('/authoring-defaults')) {
      const value = entryDefaults(url.searchParams);
      Object.assign(value.configuration.options, optionOverrides);
      if (invalidCompany) value.configuration.company_id = SOURCE;
      return value as never;
    }
    if (
      url.pathname.endsWith('/configuration') ||
      url.pathname.endsWith('/product-configuration/effective')
    ) {
      const value = entryConfiguration(url.searchParams.get('as_of')!);
      Object.assign(value.options, optionOverrides);
      if (invalidCompany) value.company_id = SOURCE;
      return value as never;
    }
    const value = response(request);
    if (url.pathname.endsWith('/field-set'))
      for (const field of (
        value as { fields: { key: string; writable: boolean }[] }
      ).fields)
        if (denied.includes(field.key)) field.writable = false;
    return value as never;
  });
});
it('disables company-incompatible inventory tracking in a new profile revision', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_, request) => {
    if (
      request.path.includes(
        '/entities/catalog.inventory_profile_template_revision/field-set',
      )
    )
      return {
        company_id: COMPANY,
        entity_type: 'catalog.inventory_profile_template_revision',
        source_version: 8,
        fields: controls[
          'inventory_profile_template_revision:create'
        ] as MasterField[],
      } as never;
    return profileResponse(request) as never;
  });
  render(
    <ProductProfileRevision
      company={COMPANY}
      config={masterConfig('inventory-templates')!}
      parentId={RECORD}
      canManage
      access={profileAccess}
    />,
  );
  const serial = await screen.findByRole('checkbox', {
    name: 'Serial tracking',
  });
  expect(serial).toBeDisabled();
  expect(serial).not.toBeChecked();
  expect(
    screen.getByRole('checkbox', { name: 'Batch / lot tracking' }),
  ).toBeDisabled();
  expect(
    screen.getByRole('checkbox', { name: 'Expiry required' }),
  ).toBeDisabled();
  expect(
    screen.getAllByText(/Enable.*Company configuration before using/).length,
  ).toBeGreaterThan(0);
});
it('retains historical tracking selections after company choices narrow', () => {
  const field = fields('catalog.product_type_revision').find(
    (field) => field.key === 'tracking_modes',
  )!;
  render(
    <ProductCatalogField
      company={COMPANY}
      field={field}
      values={{ tracking_modes: ['SERIAL'] }}
      access={access}
      disabled
      readView
      onChange={vi.fn()}
    />,
  );
  expect(screen.getByText('Retained selection: SERIAL.')).toBeVisible();
});
it('displays a retained conversion mode while preventing its new selection', () => {
  const field = fields('catalog.item_unit_revision').find(
    (field) => field.key === 'conversion_mode',
  )!;
  field.control!.choices = field.control!.choices!.filter(
    (choice) => choice.value === 'FIXED',
  );
  render(
    <ProductCatalogField
      company={COMPANY}
      field={field}
      values={{ conversion_mode: 'MEASURED' }}
      access={access}
      disabled
      readView
      onChange={vi.fn()}
    />,
  );
  expect(screen.getByRole('combobox', { name: 'Conversion mode' })).toHaveValue(
    'MEASURED',
  );
  expect(
    screen.getByRole('option', { name: 'Retained: Measured' }),
  ).toBeDisabled();
});
it.each([true, false])(
  'offers explicit clearing of unavailable tracking choices only with native write access %s',
  async (writable) => {
    const onChange = vi.fn(),
      field = fields('catalog.product_type_revision', 'create').find(
        (field) => field.key === 'tracking_modes',
      )!;
    field.writable = writable;
    render(
      <ProductCatalogField
        company={COMPANY}
        field={field}
        values={{ tracking_modes: ['NONE', 'SERIAL'] }}
        access={access}
        onChange={onChange}
      />,
    );
    if (writable) {
      await userEvent.click(
        screen.getByRole('button', { name: 'Clear unavailable selections' }),
      );
      expect(onChange).toHaveBeenCalledWith(['NONE']);
    } else
      expect(
        screen.queryByRole('button', { name: 'Clear unavailable selections' }),
      ).not.toBeInTheDocument();
  },
);
