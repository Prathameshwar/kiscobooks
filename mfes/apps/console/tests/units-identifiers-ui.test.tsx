import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DisplayConfigProvider, PermissionProvider } from '@janso/ui';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UnitsIdentifiersDirectory } from '../app/components/UnitsIdentifiersDirectory';
import { UnitsIdentifiersEditor } from '../app/components/UnitsIdentifiersEditor';
import { UnitsIdentifiersDetail } from '../app/components/UnitsIdentifiersDetail';
import { IdentifierProfileRequirements } from '../app/components/IdentifierProfileRequirements';
import { UnitConversionCheck } from '../app/components/UnitConversionCheck';
import { IdentifierUnitReference } from '../app/components/UnitsIdentifiersCommon';
import { CatalogMasterDetail } from '../app/components/CatalogMasterDetail';
import { masterConfig } from '../app/lib/catalog-masters';
import { identifierResources } from '../app/lib/units-identifiers';
import { serviceCall } from '../app/lib/service-call';
import { BEFORE_COMPANY_CHANGE } from '../app/lib/use-unsaved-changes';
import {
  COMPANY,
  RECORD,
  SOURCE,
  ROOT,
  FRESH,
  access,
  fields,
  response,
  row,
  page,
} from './units-identifiers-fixtures';

vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
vi.mock('../app/lib/navigate', () => ({
  goTo: vi.fn(),
  signInUrl: () => '/sign-in',
}));
const configs = identifierResources.map((resource) => masterConfig(resource)!);
it('retains the exact converted quantity when company display precision rounds it to zero', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) =>
    request.path.endsWith('/units/convert')
      ? ({ ...(response(request) as object), quantity: '0.0001' } as never)
      : (response(request) as never),
  );
  render(
    <DisplayConfigProvider config={{ quantityPrecision: 0 }}>
      <UnitConversionCheck company={COMPANY} fromUnit={SOURCE} />
    </DisplayConfigProvider>,
  );
  await choose('Convert to unit', 'Each');
  await userEvent.click(
    screen.getByRole('button', { name: 'Check conversion' }),
  );
  expect(await screen.findByText('Exact quantity: 0.0001')).toBeVisible();
});
const writable = configs.filter(
  (config) => config.resource !== 'unit-conversions',
);
const wrap = (node: React.ReactNode) =>
  render(
    <PermissionProvider permissions={[]}>
      <DisplayConfigProvider
        config={{ timezone: 'Asia/Kolkata', currency: 'INR' }}
      >
        {node}
      </DisplayConfigProvider>
    </PermissionProvider>,
  );
const writes = () =>
  vi
    .mocked(serviceCall)
    .mock.calls.filter(([, request]) =>
      ['POST', 'PATCH'].includes(request.method ?? 'GET'),
    );
async function fill() {
  await userEvent.type(
    await screen.findByRole('textbox', { name: 'Code' }),
    'NEW',
  );

  await userEvent.type(
    screen.getByRole('textbox', { name: 'Name' }),
    'New definition',
  );
}
async function choose(label: string, name: string) {
  await userEvent.click(await screen.findByRole('combobox', { name: label }));
  await userEvent.click(
    await screen.findByRole('option', { name: new RegExp(name) }),
  );
}
beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(null, '', '/');
  vi.mocked(serviceCall).mockImplementation(
    async (_endpoint, request) => response(request) as never,
  );
});

it('blocks conversion creation without unit read authority', async () => {
  wrap(
    <UnitsIdentifiersEditor
      company={COMPANY}
      config={masterConfig('unit-conversions')!}
      access={{ ...access, units: false }}
    />,
  );
  expect(
    await screen.findByRole('button', { name: 'Create unit conversion' }),
  ).toBeDisabled();
  expect(
    vi
      .mocked(serviceCall)
      .mock.calls.some(([, request]) => request.path.includes('/units/')),
  ).toBe(false);
});

it('removes read-denied query settings while retaining the caller', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) =>
    request.path.includes('/field-set')
      ? ({
          company_id: COMPANY,
          entity_type: 'catalog.identifier_type',
          fields: fields('catalog.identifier_type').filter(
            (field) => field.key !== 'code',
          ),
        } as never)
      : (response(request) as never),
  );
  wrap(
    <UnitsIdentifiersDirectory
      company={COMPANY}
      config={masterConfig('identifier-types')!}
      canManage={false}
      access={access}
      initialQuery="q=MPN&sort=code&returnTo=%2Fsettings"
    />,
  );
  expect(
    await screen.findByText(
      /Unavailable search, filter or sort settings were removed/,
    ),
  ).toBeVisible();
  expect(
    screen.getByRole('link', { name: 'Back to previous page' }),
  ).toHaveAttribute('href', '/settings');
  expect(window.location.search).not.toContain('q=');
  expect(window.location.search).not.toContain('sort=code');
});

it('rejects a quantity receipt for a different input', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) =>
    request.path.endsWith('/units/convert')
      ? ({
          ...(response(request) as object),
          input_quantity: '2.0000',
        } as never)
      : (response(request) as never),
  );
  wrap(<UnitConversionCheck company={COMPANY} fromUnit={SOURCE} />);
  await choose('Convert to unit', 'Each');
  await userEvent.click(
    screen.getByRole('button', { name: 'Check conversion' }),
  );
  expect(
    await screen.findByText('The conversion result could not be verified.'),
  ).toBeVisible();
  expect(screen.queryByText(/Converted quantity:/)).not.toBeInTheDocument();
});

describe('units and identifiers directories', () => {
  it.each(configs)(
    'renders $title with permitted links and native columns',
    async (config) => {
      wrap(
        <UnitsIdentifiersDirectory
          company={COMPANY}
          config={config}
          canManage
          access={access}
        />,
      );
      expect(
        await screen.findByRole('table', { name: config.title + ' directory' }),
      ).toBeVisible();
      await waitFor(() =>
        expect(screen.queryByRole('progressbar')).not.toBeInTheDocument(),
      );
      expect(
        screen.getByRole('link', { name: 'New ' + config.singular }),
      ).toHaveAttribute(
        'href',
        expect.stringContaining('/masters/' + config.resource + '/new'),
      );
      expect(
        screen.getByRole('navigation', { name: 'Units and identifiers' }),
      ).toBeVisible();
      if (config.resource === 'unit-conversions')
        expect(screen.getByText('9007199254740993')).toBeVisible();
    },
  );
  it('searches types by indexed code and retains filters in create navigation', async () => {
    const config = masterConfig('identifier-types')!;
    wrap(
      <UnitsIdentifiersDirectory
        company={COMPANY}
        config={config}
        canManage
        access={access}
        initialQuery="q=MPN&is_barcode=false&limit=50"
      />,
    );
    expect(
      await screen.findByRole('link', { name: 'New identifier type' }),
    ).toHaveAttribute('href', expect.stringContaining('is_barcode'));
    expect(
      screen.getByText('At least two characters; search by code.'),
    ).toBeVisible();
    await waitFor(() =>
      expect(
        vi
          .mocked(serviceCall)
          .mock.calls.some(
            ([, request]) =>
              request.path.includes('/identifier-types?') &&
              request.path.includes('q=MPN') &&
              request.path.includes('is_barcode=false'),
          ),
      ).toBe(true),
    );
    expect(
      screen.queryByRole('option', { name: 'Name A to Z' }),
    ).not.toBeInTheDocument();
  });
  it('keeps conversion browsing immutable and references navigable', async () => {
    wrap(
      <UnitsIdentifiersDirectory
        company={COMPANY}
        config={configs[0]!}
        canManage
        access={access}
        initialQuery={'from_unit_id=' + SOURCE}
      />,
    );
    expect(await screen.findByRole('link', { name: 'Box' })).toHaveAttribute(
      'href',
      expect.stringContaining('/masters/units/' + SOURCE),
    );
    await userEvent.click(screen.getByRole('button', { name: /Actions for/ }));
    expect(
      screen.getByRole('menuitem', { name: 'View details' }),
    ).toBeVisible();
    expect(
      screen.queryByRole('menuitem', { name: 'Edit details' }),
    ).not.toBeInTheDocument();
  });
  it('hides write actions, inaccessible related links and read-denied search', async () => {
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) =>
      request.path.includes('/field-set')
        ? ({
            company_id: COMPANY,
            entity_type: 'catalog.identifier_type',
            fields: fields('catalog.identifier_type').filter(
              (field) => field.key !== 'code',
            ),
          } as never)
        : (response(request) as never),
    );
    wrap(
      <UnitsIdentifiersDirectory
        company={COMPANY}
        config={masterConfig('identifier-types')!}
        canManage={false}
        access={{ ...access, units: false, 'unit-conversions': false }}
        initialQuery="q=MPN"
      />,
    );
    expect(await screen.findByText('Read-only access.')).toBeVisible();
    expect(
      screen.queryByRole('link', { name: 'New identifier type' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: 'Conversions' }),
    ).not.toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByRole('progressbar')).not.toBeInTheDocument(),
    );
    expect(
      vi
        .mocked(serviceCall)
        .mock.calls.some(
          ([, request]) =>
            request.path.includes('/identifier-types?') &&
            request.path.includes('q='),
        ),
    ).toBe(false);
  });
  it('advances and resets bounded cursor pages', async () => {
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) =>
      request.path.includes('/pack-types?')
        ? ({
            items: [row('pack-types')],
            page: {
              ...page,
              has_more: !request.path.includes('cursor='),
              next_cursor: 'signed-page',
            },
          } as never)
        : (response(request) as never),
    );
    wrap(
      <UnitsIdentifiersDirectory
        company={COMPANY}
        config={masterConfig('pack-types')!}
        canManage
        access={access}
      />,
    );
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: /Next page of/ }),
      ).toBeEnabled(),
    );
    await userEvent.click(screen.getByRole('button', { name: /Next page of/ }));
    await waitFor(() =>
      expect(
        vi
          .mocked(serviceCall)
          .mock.calls.some(([, request]) =>
            request.path.includes('cursor=signed-page'),
          ),
      ).toBe(true),
    );
    await userEvent.click(
      screen.getByRole('button', { name: /Previous page of/ }),
    );
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: /Previous page of/ }),
      ).toBeDisabled(),
    );
  });
});

describe('native create, edit, errors and safe retries', () => {
  it.each(writable)(
    'creates a $singular with native metadata and success navigation',
    async (config) => {
      wrap(
        <UnitsIdentifiersEditor
          company={COMPANY}
          config={config}
          access={access}
          returnTo={'/masters/' + config.resource + '?q=TE'}
        />,
      );
      await fill();
      if (config.resource === 'identifier-types')
        await userEvent.click(
          screen.getByRole('checkbox', { name: 'Barcode identifier' }),
        );
      await userEvent.click(
        screen.getByRole('button', { name: 'Create ' + config.singular }),
      );
      expect(
        await screen.findByText(config.singular + ' created successfully.'),
      ).toBeVisible();
      expect(writes()[0]?.[1].body).toMatchObject({
        code: 'NEW',
        name: 'New definition',
      });
      expect(writes()[0]?.[1].body).not.toHaveProperty('is_active');
      if (config.resource === 'identifier-types')
        expect(writes()[0]?.[1].body).toHaveProperty('is_barcode', true);
      if (config.resource === 'identifier-profiles')
        expect(writes()[0]?.[1].body).toHaveProperty('requirements', [
          {
            identifier_type: 'SERIAL',
            namespace_rule: 'COMPANY',
            min_count: 1,
            max_count: 1,
            requires_slot: false,
          },
        ]);
      expect(
        screen.getByRole('link', { name: 'View ' + config.singular }),
      ).toHaveAttribute('href', expect.stringContaining(FRESH));
    },
  );
  it('creates exact conversion ratios using searchable current-company units', async () => {
    wrap(
      <UnitsIdentifiersEditor
        company={COMPANY}
        config={configs[0]!}
        access={access}
      />,
    );
    await choose('Source unit', 'Box');
    await choose('Canonical unit', 'Each');
    await userEvent.clear(screen.getByRole('textbox', { name: 'Numerator' }));
    await userEvent.type(
      screen.getByRole('textbox', { name: 'Numerator' }),
      '9007199254740993',
    );
    await userEvent.click(
      screen.getByRole('button', { name: 'Create unit conversion' }),
    );
    expect(
      await screen.findByText('unit conversion created successfully.'),
    ).toBeVisible();
    expect(writes()[0]?.[1].body).toEqual({
      from_unit_id: SOURCE,
      canonical_unit_id: ROOT,
      numerator: '9007199254740993',
      denominator: '1',
    });
  });
  it.each(writable)(
    'edits the $singular name with the current version',
    async (config) => {
      wrap(
        <UnitsIdentifiersEditor
          company={COMPANY}
          config={config}
          id={RECORD}
          access={access}
        />,
      );
      const name = await screen.findByRole('textbox', { name: 'Name' });
      await userEvent.clear(name);
      await userEvent.type(name, 'Renamed');
      await userEvent.click(
        screen.getByRole('button', { name: 'Save changes' }),
      );
      expect(
        await screen.findByText(config.singular + ' updated successfully.'),
      ).toBeVisible();
      expect(writes()[0]?.[1].body).toEqual({
        name: 'Renamed',
        expected_version: 4,
      });
    },
  );
  it('locks stable identifier code and classification and omits unchanged saves', async () => {
    wrap(
      <UnitsIdentifiersEditor
        company={COMPANY}
        config={masterConfig('identifier-types')!}
        id={RECORD}
        access={access}
      />,
    );
    expect(await screen.findByRole('textbox', { name: 'Code' })).toBeDisabled();
    expect(
      screen.getByRole('checkbox', { name: 'Barcode identifier' }),
    ).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    expect(await screen.findByText('No changes to save.')).toBeVisible();
    expect(writes()).toHaveLength(0);
  });
  it('focuses invalid labels and never submits incomplete inputs', async () => {
    wrap(
      <UnitsIdentifiersEditor
        company={COMPANY}
        config={masterConfig('pack-types')!}
        access={access}
      />,
    );
    await userEvent.click(
      await screen.findByRole('button', { name: 'Create pack type' }),
    );
    await waitFor(() =>
      expect(screen.getByRole('textbox', { name: 'Code' })).toHaveFocus(),
    );
    expect(writes()).toHaveLength(0);
  });
  it('validates two distinct profile rules and explicit slots', async () => {
    wrap(
      <UnitsIdentifiersEditor
        company={COMPANY}
        config={masterConfig('identifier-profiles')!}
        access={access}
      />,
    );
    await fill();
    await userEvent.click(
      screen.getByRole('button', { name: 'Add identifier requirement' }),
    );
    expect(
      screen.getByRole('button', { name: 'Add identifier requirement' }),
    ).toBeDisabled();
    expect(
      screen.getByRole('combobox', { name: 'Requirement 2: Identifier type' }),
    ).toHaveValue('IMEI');
    const count = screen.getByRole('textbox', {
      name: 'Requirement 2: Maximum count',
    });
    await userEvent.clear(count);
    await userEvent.type(count, '2');
    await userEvent.click(
      screen.getByRole('button', { name: 'Create identifier profile' }),
    );
    expect(
      await screen.findByText('Multiple identifiers require explicit slots.'),
    ).toBeVisible();
    expect(writes()).toHaveLength(0);
    await userEvent.click(
      screen.getByRole('checkbox', {
        name: 'Requirement 2: Require identifier slots',
      }),
    );
    await userEvent.click(
      screen.getByRole('button', { name: 'Create identifier profile' }),
    );
    expect(
      await screen.findByText('identifier profile created successfully.'),
    ).toBeVisible();
  });
  it('blocks create when required fields, child rules or unit read access are unavailable', async () => {
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) =>
      request.path.includes('identifier_profile_requirement/field-set')
        ? ({
            company_id: COMPANY,
            entity_type: 'catalog.identifier_profile_requirement',
            fields: fields('catalog.identifier_profile_requirement').filter(
              (field) => field.key !== 'max_count',
            ),
          } as never)
        : (response(request) as never),
    );
    wrap(
      <UnitsIdentifiersEditor
        company={COMPANY}
        config={masterConfig('identifier-profiles')!}
        access={access}
      />,
    );
    expect(
      await screen.findByRole('button', { name: 'Create identifier profile' }),
    ).toBeDisabled();
    expect(writes()).toHaveLength(0);
  });
  it('retains 422 field errors and permits a corrected save', async () => {
    let count = 0;
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
      if (request.method === 'POST' && ++count === 1)
        throw {
          status: 422,
          message: 'Invalid code',
          fields: { code: 'Code is reserved.' },
        };
      return response(request) as never;
    });
    wrap(
      <UnitsIdentifiersEditor
        company={COMPANY}
        config={masterConfig('pack-types')!}
        access={access}
      />,
    );
    await fill();
    await userEvent.click(
      screen.getByRole('button', { name: 'Create pack type' }),
    );
    expect(await screen.findByText('Code is reserved.')).toBeVisible();
    const code = screen.getByRole('textbox', { name: 'Code' });
    await userEvent.clear(code);
    await userEvent.type(code, 'VALID');
    await userEvent.click(
      screen.getByRole('button', { name: 'Create pack type' }),
    );
    expect(
      await screen.findByText('pack type created successfully.'),
    ).toBeVisible();
  });
  it.each(['outage', 'foreign receipt'])(
    'locks an uncertain %s save and retries the same key and body',
    async (mode) => {
      let count = 0;
      vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
        if (request.method === 'POST' && ++count === 1) {
          if (mode === 'outage')
            throw { status: 503, message: 'Temporary outage' };
          return {
            ...(response(request) as object),
            company_id: ROOT,
          } as never;
        }
        return response(request) as never;
      });
      wrap(
        <UnitsIdentifiersEditor
          company={COMPANY}
          config={masterConfig('pack-types')!}
          access={access}
        />,
      );
      await fill();
      await userEvent.click(
        screen.getByRole('button', { name: 'Create pack type' }),
      );
      await screen.findByRole('button', { name: 'Retry same save' });
      expect(screen.getByRole('textbox', { name: 'Name' })).toBeDisabled();
      await userEvent.click(
        screen.getByRole('button', { name: 'Retry same save' }),
      );
      expect(
        await screen.findByText('pack type created successfully.'),
      ).toBeVisible();
      expect(writes()).toHaveLength(2);
      expect(writes()[0]?.[1].key).toBe(writes()[1]?.[1].key);
      expect(writes()[0]?.[1].body).toEqual(writes()[1]?.[1].body);
    },
  );
  it('requires reload and review after conflict, preserving drafts until confirmation', async () => {
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
      if (request.method === 'POST')
        throw { status: 409, message: 'Definition changed' };
      return response(request) as never;
    });
    wrap(
      <UnitsIdentifiersEditor
        company={COMPANY}
        config={masterConfig('pack-types')!}
        access={access}
      />,
    );
    await fill();
    await userEvent.click(
      screen.getByRole('button', { name: 'Create pack type' }),
    );
    expect(
      await screen.findByRole('button', { name: 'Create pack type' }),
    ).toBeDisabled();
    await userEvent.click(
      screen.getByRole('button', { name: 'Reload and review' }),
    );
    const dialog = screen.getByRole('dialog', {
      name: 'Reload current definition?',
    });
    expect(screen.getByRole('textbox', { name: 'Name' })).toHaveValue(
      'New definition',
    );
    await userEvent.click(
      within(dialog).getByRole('button', { name: 'Reload and review' }),
    );
    await waitFor(() =>
      expect(screen.getByRole('textbox', { name: 'Name' })).toHaveValue(''),
    );
  });
  it('guards dirty back navigation and company changes', async () => {
    wrap(
      <UnitsIdentifiersEditor
        company={COMPANY}
        config={masterConfig('pack-types')!}
        access={access}
      />,
    );
    await fill();
    const event = new Event(BEFORE_COMPANY_CHANGE, { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    await userEvent.click(screen.getByRole('link', { name: /Back to/ }));
    expect(
      screen.getByRole('dialog', { name: 'Discard unsaved changes?' }),
    ).toBeVisible();
  });
  it.each([401, 403, 404, 503])(
    'shows a useful %s failure instead of an empty editable form',
    async (status) => {
      vi.mocked(serviceCall).mockRejectedValue({
        status,
        message: 'Definition could not be loaded',
      });
      wrap(
        <UnitsIdentifiersEditor
          company={COMPANY}
          config={masterConfig('pack-types')!}
          access={access}
        />,
      );
      expect(
        await screen.findByText('Definition could not be loaded'),
      ).toBeVisible();
      expect(
        screen.queryByRole('button', { name: 'Create pack type' }),
      ).not.toBeInTheDocument();
    },
  );
});

describe('details, profile rules, lifecycle and quantity checks', () => {
  it('recovers a committed lifecycle retry when another administrator changed availability', async () => {
    let count = 0;
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
      if (request.method === 'POST') {
        if (++count === 1)
          throw { status: 503, message: 'Interrupted response' };
        return {
          ...row('pack-types'),
          row_version: 6,
          is_active: true,
        } as never;
      }
      return response(request) as never;
    });
    wrap(
      <UnitsIdentifiersDetail
        company={COMPANY}
        config={masterConfig('pack-types')!}
        id={RECORD}
        canManage
        access={access}
      />,
    );
    await userEvent.click(
      await screen.findByRole('button', { name: 'pack type actions' }),
    );
    await userEvent.click(screen.getByRole('menuitem', { name: 'Deactivate' }));
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: 'Deactivate',
      }),
    );
    await userEvent.click(
      await screen.findByRole('button', { name: 'Retry same deactivate' }),
    );
    expect(
      await screen.findByText(
        'The action completed. Availability has since changed; review the current definition before another action.',
      ),
    ).toBeVisible();
    expect(
      screen.queryByRole('button', { name: 'Retry same deactivate' }),
    ).not.toBeInTheDocument();
    expect(writes()[0]?.[1].key).toBe(writes()[1]?.[1].key);
    expect(writes()[0]?.[1].body).toEqual(writes()[1]?.[1].body);
  });
  it.each(configs)(
    'renders the $singular detail with native read access',
    async (config) => {
      wrap(
        <UnitsIdentifiersDetail
          company={COMPANY}
          config={config}
          id={RECORD}
          canManage={false}
          access={access}
        />,
      );
      await screen.findByText('Definition');
      await waitFor(() =>
        expect(screen.queryByText(/Loading .*\.\.\./)).not.toBeInTheDocument(),
      );
      expect(
        screen.queryByRole('button', { name: config.singular + ' actions' }),
      ).not.toBeInTheDocument();
      if (config.resource === 'identifier-profiles')
        expect(
          await screen.findByRole('table', {
            name: 'Saved identifier requirements',
          }),
        ).toBeVisible();
    },
  );
  it.each(writable)(
    'uses the shared kebab and expected version for $singular lifecycle',
    async (config) => {
      wrap(
        <UnitsIdentifiersDetail
          company={COMPANY}
          config={config}
          id={RECORD}
          canManage
          access={access}
        />,
      );
      await userEvent.click(
        await screen.findByRole('button', {
          name: config.singular + ' actions',
        }),
      );
      await userEvent.click(
        screen.getByRole('menuitem', { name: 'Deactivate' }),
      );
      await userEvent.click(
        within(screen.getByRole('dialog')).getByRole('button', {
          name: 'Deactivate',
        }),
      );
      expect(
        await screen.findByText(config.singular + ' deactivated successfully.'),
      ).toBeVisible();
      expect(writes()[0]?.[1].body).toEqual({ expected_version: 4 });
    },
  );
  it('retries an uncertain lifecycle without changing its version or key', async () => {
    let count = 0;
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
      if (request.method === 'POST' && ++count === 1)
        throw { status: 503, message: 'Offline' };
      return response(request) as never;
    });
    wrap(
      <UnitsIdentifiersDetail
        company={COMPANY}
        config={masterConfig('pack-types')!}
        id={RECORD}
        canManage
        access={access}
      />,
    );
    await userEvent.click(
      await screen.findByRole('button', { name: 'pack type actions' }),
    );
    await userEvent.click(screen.getByRole('menuitem', { name: 'Deactivate' }));
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: 'Deactivate',
      }),
    );
    await userEvent.click(
      await screen.findByRole('button', { name: 'Retry same deactivate' }),
    );
    expect(
      await screen.findByText('pack type deactivated successfully.'),
    ).toBeVisible();
    expect(writes()[0]?.[1].key).toBe(writes()[1]?.[1].key);
    expect(writes()[0]?.[1].body).toEqual(writes()[1]?.[1].body);
  });
  it('keeps requirements read-only and filters with native enum values', async () => {
    wrap(<IdentifierProfileRequirements company={COMPANY} id={RECORD} />);
    const table = await screen.findByRole('table', {
      name: 'Saved identifier requirements',
    });
    expect(await within(table).findByText('Serial number')).toBeVisible();
    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: 'Filter by identifier type' }),
      'IMEI',
    );
    await waitFor(() =>
      expect(
        vi
          .mocked(serviceCall)
          .mock.calls.some(
            ([, request]) =>
              request.path.includes('/requirements?') &&
              request.path.includes('identifier_type=IMEI'),
          ),
      ).toBe(true),
    );
    expect(
      screen.queryByRole('button', { name: /Save/ }),
    ).not.toBeInTheDocument();
  });
  it('hydrates references and aborts old-company reads on unmount', async () => {
    const view = wrap(
      <IdentifierUnitReference
        company={COMPANY}
        label="Source unit"
        value={SOURCE}
        onChange={() => {}}
      />,
    );
    await waitFor(() =>
      expect(screen.getByRole('combobox', { name: 'Source unit' })).toHaveValue(
        'Box',
      ),
    );
    const request = vi
      .mocked(serviceCall)
      .mock.calls.find(([, value]) =>
        value.path.endsWith('/units/' + SOURCE),
      )![1];
    view.unmount();
    expect(request.signal?.aborted).toBe(true);
  });
  it('validates and submits read-only exact quantity checks', async () => {
    wrap(<UnitConversionCheck company={COMPANY} fromUnit={SOURCE} />);
    await userEvent.click(
      screen.getByRole('button', { name: 'Check conversion' }),
    );
    expect(await screen.findByText('Choose a target unit.')).toBeVisible();
    expect(writes()).toHaveLength(0);
    await choose('Convert to unit', 'Each');
    await userEvent.clear(
      screen.getByRole('textbox', { name: 'Quantity to convert' }),
    );
    await userEvent.type(
      screen.getByRole('textbox', { name: 'Quantity to convert' }),
      '1.0000',
    );
    await userEvent.click(
      screen.getByRole('button', { name: 'Check conversion' }),
    );
    expect(
      await screen.findByText('Converted quantity: 12.0000'),
    ).toBeVisible();
    expect(writes()[0]?.[1].body).toEqual({
      from_unit_id: SOURCE,
      to_unit_id: ROOT,
      quantity: '1.0000',
    });
  });
  it('keeps a conversion caller and company permissions on the existing unit detail', async () => {
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) =>
      request.path.includes('unit_of_measure/field-set')
        ? ({
            company_id: COMPANY,
            entity_type: 'catalog.unit_of_measure',
            fields: fields('catalog.pack_type'),
          } as never)
        : (response(request) as never),
    );
    const caller =
      '/masters/unit-conversions/' +
      RECORD +
      '?returnTo=%2Fmasters%2Funit-conversions';
    wrap(
      <CatalogMasterDetail
        company={COMPANY}
        config={masterConfig('units')!}
        id={SOURCE}
        canManage={false}
        identifierAccess={access}
        returnTo={caller}
      />,
    );
    expect(
      screen.getByRole('link', { name: /Back to previous page/ }),
    ).toHaveAttribute('href', caller);
    expect(
      screen.getByRole('link', { name: 'Conversions from this unit' }),
    ).toHaveAttribute(
      'href',
      expect.stringContaining('from_unit_id=' + SOURCE),
    );
  });
});

it.each([
  ['indian', '1,23,456.00'],
  ['western', '123,456.00'],
] as const)(
  'uses the configured %s quantity display without changing native inputs',
  async (digitGrouping, shown) => {
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) =>
      request.path.endsWith('/units/convert')
        ? ({
            ...(response(request) as object),
            quantity: '123456.0000',
          } as never)
        : (response(request) as never),
    );
    render(
      <PermissionProvider permissions={[]}>
        <DisplayConfigProvider config={{ digitGrouping, quantityPrecision: 2 }}>
          <UnitConversionCheck company={COMPANY} fromUnit={SOURCE} />
        </DisplayConfigProvider>
      </PermissionProvider>,
    );
    await choose('Convert to unit', 'Each');
    await userEvent.click(
      screen.getByRole('button', { name: 'Check conversion' }),
    );
    expect(
      await screen.findByText('Converted quantity: ' + shown),
    ).toBeVisible();
    expect(writes()[0]?.[1].body).toEqual({
      from_unit_id: SOURCE,
      to_unit_id: ROOT,
      quantity: '1',
    });
  },
);
