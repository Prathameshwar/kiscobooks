import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { UnitsIdentifiersDirectory } from '../app/components/UnitsIdentifiersDirectory';
import { AttributeMasterDirectory } from '../app/components/AttributeMasterDirectory';
import { PricingMasterDirectory } from '../app/components/PricingMasterDirectory';

import { ProductTypeHistory } from '../app/components/ProductTypeRevision';
import { AttributeSetHistory } from '../app/components/AttributeSetHistory';
import { ProductProfileHistory } from '../app/components/ProductProfileHistory';
import { ConfigurationReference } from '../app/components/ProductConfigurationCommon';
import { AttributeReferenceLabel } from '../app/components/AttributeMasterCommon';
import { ProfileField } from '../app/components/ProductProfileCommon';
import * as profiles from './product-profile-fixtures';
import { masterConfig } from '../app/lib/catalog-masters';
import { serviceCall } from '../app/lib/service-call';
import * as units from './units-identifiers-fixtures';
import * as attributes from './attribute-master-fixtures';
import * as pricing from './pricing-master-fixtures';
import * as products from './product-classification-fixtures';
vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
vi.mock('../app/lib/navigate', () => ({
  goTo: vi.fn(),
  signInUrl: () => '/sign-in',
}));
const api = vi.mocked(serviceCall);
beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(null, '', '/');
  products.resetFixtures();
});
it.each(['pack-types', 'attribute-definitions', 'sales-channels'])(
  'uses real view/edit links in the %s kebab menu',
  async (resource) => {
    const fixture =
      resource === 'pack-types'
        ? units
        : resource === 'attribute-definitions'
          ? attributes
          : pricing;
    api.mockImplementation(
      async (_endpoint, request) => fixture.response(request) as never,
    );
    const props = {
      company: units.COMPANY,
      config: masterConfig(resource)!,
      canManage: true,
      initialQuery: 'q=Basic',
    };
    render(
      resource === 'pack-types' ? (
        <UnitsIdentifiersDirectory {...props} access={units.access} />
      ) : resource === 'attribute-definitions' ? (
        <AttributeMasterDirectory {...props} access={attributes.access} />
      ) : (
        <PricingMasterDirectory {...props} access={pricing.access} />
      ),
    );
    await userEvent.click(
      await screen.findByRole('button', { name: /Actions for/ }),
    );
    const view = screen.getByRole('menuitem', { name: 'View details' });
    expect(view).toHaveAttribute(
      'href',
      expect.stringContaining(
        `/masters/${resource}/${resource === 'attribute-definitions' ? units.SOURCE : units.RECORD}?returnTo=`,
      ),
    );
    expect(
      new URL(
        view.getAttribute('href')!,
        'https://console.invalid',
      ).searchParams.get('returnTo'),
    ).toContain('q=Basic');
    expect(
      screen.getByRole('menuitem', { name: 'Edit details' }),
    ).toHaveAttribute('href', expect.stringContaining('/edit?returnTo='));
  },
);
it.each(['product-types', 'attribute-sets', 'warranty-policies'])(
  'links View and Open draft to the existing nested %s revision page',
  async (resource) => {
    const fixture =
      resource === 'product-types'
        ? products
        : resource === 'attribute-sets'
          ? attributes
          : profiles;
    api.mockImplementation(
      async (_endpoint, request) => fixture.response(request) as never,
    );
    const props = {
      company: units.COMPANY,
      here: '/masters/' + resource + '/' + units.RECORD,
      active: true,
      canManage: true,
      blocked: false,
      onLeave: vi.fn(),
    };
    render(
      resource === 'product-types' ? (
        <ProductTypeHistory {...props} parentId={units.RECORD} />
      ) : resource === 'attribute-sets' ? (
        <AttributeSetHistory
          {...props}
          setId={units.RECORD}
          access={attributes.access}
        />
      ) : (
        <ProductProfileHistory
          {...props}
          resource="warranty-policies"
          parentId={units.RECORD}
        />
      ),
    );
    await userEvent.click(
      await screen.findByRole('button', { name: /Actions for/ }),
    );
    const view = screen.getByRole('menuitem', { name: 'View revision' });
    expect(view).toHaveAttribute(
      'href',
      expect.stringContaining(
        '/masters/' + resource + '/' + units.RECORD + '/revisions/',
      ),
    );
    expect(
      screen.getByRole('menuitem', { name: 'Open draft' }),
    ).toHaveAttribute('href', view.getAttribute('href'));
  },
);
it('uses the verified parent from a native published choice for its nested detail link', async () => {
  api.mockResolvedValue({
    items: [
      { value: units.SOURCE, label: 'General type', parent_id: units.RECORD },
    ],
    page: units.page,
  } as never);
  render(
    <ConfigurationReference
      company={units.COMPANY}
      source="product-type-revisions"
      label="Published product type"
      value={units.SOURCE}
      onChange={vi.fn()}
      disabled
      returnTo={'/masters/product-families/' + units.RECORD}
    />,
  );
  expect(
    await screen.findByRole('link', { name: 'Open published product type' }),
  ).toHaveAttribute(
    'href',
    expect.stringContaining(
      '/masters/product-types/' + units.RECORD + '/revisions/' + units.SOURCE,
    ),
  );
});
it.each(['denied', 'missing-parent'])(
  'does not offer a guessed revision link for %s choices',
  async (reason) => {
    if (reason === 'denied')
      api.mockRejectedValue({
        status: 403,
        message: 'Reference access unavailable',
      });
    else
      api.mockResolvedValue({
        items: [{ value: units.SOURCE, label: 'General type' }],
        page: units.page,
      } as never);
    render(
      <ConfigurationReference
        company={units.COMPANY}
        source="product-type-revisions"
        label="Published product type"
        value={units.SOURCE}
        onChange={vi.fn()}
        disabled
        returnTo={'/masters/product-families/' + units.RECORD}
      />,
    );
    if (reason === 'denied')
      await screen.findByText(/Reference access unavailable/);
    else await screen.findByDisplayValue('General type');
    expect(
      screen.queryByRole('link', { name: 'Open published product type' }),
    ).not.toBeInTheDocument();
  },
);
it.each([true, false])(
  'links resolved attribute units only when available: %s',
  async (available) => {
    api.mockImplementation(async () => {
      if (!available) throw { status: 403, message: 'Protected unit' };
      return { ...units.row('units'), id: units.SOURCE } as never;
    });
    render(
      <AttributeReferenceLabel
        company={units.COMPANY}
        resource="units"
        id={units.SOURCE}
        returnTo={'/masters/attribute-options/' + units.RECORD}
      />,
    );
    if (available) {
      const link = await screen.findByRole('link');
      expect(link).toHaveAttribute(
        'href',
        expect.stringContaining(
          '/masters/units/' + units.SOURCE + '?returnTo=',
        ),
      );
    } else {
      await screen.findByText(/label unavailable/);
      expect(screen.queryByRole('link')).not.toBeInTheDocument();
    }
  },
);
it('links a verified identifier profile on an immutable inventory revision', async () => {
  api.mockImplementation(
    async (_endpoint, request) => profiles.response(request) as never,
  );
  const field = profiles
    .fields('catalog.inventory_profile_template_revision')
    .find((field) => field.key === 'identifier_profile_id')!;
  render(
    <ProfileField
      company={units.COMPANY}
      field={field}
      value={units.SOURCE}
      disabled
      onChange={vi.fn()}
      access={profiles.access}
      returnTo={
        '/masters/inventory-templates/' +
        units.RECORD +
        '/revisions/' +
        units.SOURCE
      }
    />,
  );
  expect(
    await screen.findByRole('link', { name: 'Open identifier profile' }),
  ).toHaveAttribute(
    'href',
    expect.stringContaining(
      '/masters/identifier-profiles/' + units.SOURCE + '?returnTo=',
    ),
  );
});
