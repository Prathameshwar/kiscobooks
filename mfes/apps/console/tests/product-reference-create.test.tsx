import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { ProductCatalogReference } from '../app/components/ProductCatalogCommon';
import { serviceCall } from '../app/lib/service-call';
import { COMPANY, FRESH, ROOT, access, resetFixtures } from './product-classification-fixtures';
import { drawerResponse, groupPath, page } from './product-reference-fixtures';

vi.mock('../app/lib/service-call', async original => ({ ...(await original<typeof import('../app/lib/service-call')>()), serviceCall: vi.fn() }));
beforeEach(() => {
  vi.clearAllMocks();
  resetFixtures();
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => drawerResponse(request) as never);
});
const api = vi.mocked(serviceCall);
function reference(source = 'item-groups', overrides: Partial<typeof access> = {}, disabled = false) {
  const changed = vi.fn();
  const view = render(<ProductCatalogReference company={COMPANY} source={source} label={source === 'item-groups' ? 'Primary product group' : 'Product type'} value={null} values={{ kind: 'GOODS' }} access={{ ...access, manageGroups: true, manageTypes: true, ...overrides }} disabled={disabled} onChange={changed} />);
  return { changed, view };
}
async function openGroup() {
  await userEvent.click(screen.getByRole('button', { name: 'New product group' }));
  const panel = await screen.findByRole('dialog', { name: 'New product group' });
  await within(panel).findByRole('textbox', { name: 'Code' }, { timeout: 10_000 });
  return panel;
}
async function fill(panel: HTMLElement) {
  await userEvent.type(within(panel).getByRole('textbox', { name: 'Code' }), 'TEA');
  await userEvent.type(within(panel).getByRole('textbox', { name: 'Name' }), 'Tea');
}
async function createTypeDraft() {
  await userEvent.click(screen.getByRole('button', { name: 'New product type' }));
  const panel = await screen.findByRole('dialog', { name: 'New product type' });
  await within(panel).findByRole('textbox', { name: 'Code' }, { timeout: 10_000 });
  await fill(panel);
  await userEvent.click(within(panel).getByRole('button', { name: 'Create product type' }));
  const save = await within(panel).findByRole('button', { name: 'Save draft requirements' });
  await waitFor(() => expect(save).toBeEnabled());
  await userEvent.click(save);
  await within(panel).findByRole('heading', { name: /Requirements revision/ });
  return panel;
}

it.each([
  ['item-groups', 'Primary product group', 'New product group'],
  ['product-type-revisions', 'Product type', 'New product type'],
])('offers an inline create action for %s with company-scoped management access', (source, label, action) => {
  render(<ProductCatalogReference company={COMPANY} source={source} label={label} value={null} values={{ kind: 'GOODS' }} access={{ ...access, manageGroups: true, manageTypes: true }} onChange={vi.fn()} />);
  const button = screen.getByRole('button', { name: action });
  expect(button).toBeVisible();
  expect(button.textContent).toBe('');
  expect(button).toHaveAttribute('title', action);
});

it.each(['item-groups', 'product-type-revisions'])('hides creation for read-only %s access', source => {
  reference(source, { manageGroups: false, manageTypes: false });
  expect(screen.queryByRole('button', { name: /New product/ })).not.toBeInTheDocument();
});
it('does not turn a disabled product field into an authoring action', () => {
  reference('item-groups', {}, true);
  expect(screen.getByRole('button', { name: 'New product group' })).toBeDisabled();
});
it('creates a group with the reused form and returns its identity without a product write', async () => {
  const { changed } = reference();
  const panel = await openGroup();
  expect(within(panel).queryByRole('navigation')).not.toBeInTheDocument();
  await fill(panel);
  await userEvent.click(within(panel).getByRole('button', { name: 'Create item group' }));
  await waitFor(() => expect(changed).toHaveBeenCalledWith(FRESH));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  const writes = api.mock.calls.map(call => call[1]).filter(call => call.method === 'POST');
  expect(writes).toHaveLength(1);
  expect(writes[0]).toMatchObject({ path: groupPath, body: { code: 'TEA', name: 'Tea', allowed_kind: 'GOODS', parent_group_id: null } });
  expect(writes[0].key).toBeTruthy();
});
it('validates the group form and focuses its error inside the drawer', async () => {
  reference(); const panel = await openGroup();
  await userEvent.click(within(panel).getByRole('button', { name: 'Create item group' }));
  await waitFor(() => expect(within(panel).getByRole('textbox', { name: 'Code' })).toHaveFocus());
  expect(api.mock.calls.some(call => call[1].method === 'POST')).toBe(false);
});
it('confirms discarding only the drawer draft and restores trigger focus', async () => {
  const { changed } = reference(); const panel = await openGroup(); await fill(panel);
  await userEvent.click(within(panel).getByRole('button', { name: 'Close' }));
  const confirm = await screen.findByRole('dialog', { name: 'Discard new master changes?' });
  await userEvent.click(within(confirm).getByRole('button', { name: 'Cancel' }));
  expect(within(panel).getByRole('textbox', { name: 'Code' })).toHaveValue('TEA');
  await userEvent.click(within(panel).getByRole('button', { name: 'Cancel' }));
  await userEvent.click(within(await screen.findByRole('dialog', { name: 'Discard new master changes?' })).getByRole('button', { name: 'Discard changes' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'New product group' })).toHaveFocus());
  expect(changed).not.toHaveBeenCalled();
});
it('freezes an uncertain group save and reuses its exact body and key', async () => {
  let writes = 0;
  api.mockImplementation(async (_endpoint, request) => {
    if (request.path === groupPath && request.method === 'POST' && ++writes === 1) throw { status: 503, message: 'Connection interrupted.' };
    return drawerResponse(request) as never;
  });
  const { changed } = reference(); const panel = await openGroup(); await fill(panel);
  await userEvent.click(within(panel).getByRole('button', { name: 'Create item group' }));
  const retry = await within(panel).findByRole('button', { name: 'Retry same save' });
  expect(within(panel).getByRole('textbox', { name: 'Code' })).toBeDisabled();
  expect(within(panel).getByRole('button', { name: 'Close' })).toBeDisabled();
  await userEvent.click(retry);
  await waitFor(() => expect(changed).toHaveBeenCalledWith(FRESH));
  const saves = api.mock.calls.map(call => call[1]).filter(call => call.method === 'POST');
  expect(saves[1].key).toBe(saves[0].key); expect(saves[1].body).toEqual(saves[0].body);
});
it('creates a type and draft then requires explicit reviewed publication before selecting it', async () => {
  const { changed } = reference('product-type-revisions'); const panel = await createTypeDraft();
  expect(changed).not.toHaveBeenCalled();
  await userEvent.click(await within(panel).findByRole('button', { name: 'Publish requirements' }));
  expect(changed).not.toHaveBeenCalled();
  const confirm = await screen.findByRole('dialog', { name: 'Publish product type requirements?' });
  await userEvent.click(within(confirm).getByRole('button', { name: 'Publish requirements' }));
  await waitFor(() => expect(changed).toHaveBeenCalledWith(FRESH));
  const writes = api.mock.calls.map(call => call[1]).filter(call => call.method === 'POST');
  expect(writes.map(call => call.path)).toEqual([`/v1/companies/${COMPANY}/product-types`, `/v1/companies/${COMPANY}/product-types/${FRESH}/revisions`, `/v1/companies/${COMPANY}/product-types/${FRESH}/revisions/${FRESH}/publish`]);
  expect(writes.every(call => call.key)).toBe(true);
});
it('preserves a saved type draft when the creator cannot publish', async () => {
  const { changed } = reference('product-type-revisions', { publish: false }); const panel = await createTypeDraft();
  expect(within(panel).getByText(/A permitted publisher must publish/)).toBeVisible();
  expect(within(panel).queryByRole('button', { name: 'Publish requirements' })).not.toBeInTheDocument();
  expect(changed).not.toHaveBeenCalled();
});
it('refuses a published choice belonging to another master and retries only the read', async () => {
  let wrong = true;
  api.mockImplementation(async (_endpoint, request) => request.path.includes('/product-configuration/options/product-type-revisions')
    ? { items: [{ value: FRESH, parent_id: wrong ? ROOT : FRESH, label: 'Tea type', code: 'TEA' }], page } as never : drawerResponse(request) as never);
  const { changed } = reference('product-type-revisions'); const panel = await createTypeDraft();
  await userEvent.click(await within(panel).findByRole('button', { name: 'Publish requirements' }));
  await userEvent.click(within(await screen.findByRole('dialog', { name: 'Publish product type requirements?' })).getByRole('button', { name: 'Publish requirements' }));
  await within(panel).findByText(/its availability for this product could not be verified/);
  expect(changed).not.toHaveBeenCalled(); wrong = false;
  await userEvent.click(within(panel).getByRole('button', { name: 'Retry selection' }));
  await waitFor(() => expect(changed).toHaveBeenCalledWith(FRESH));
  expect(api.mock.calls.filter(call => call[1].method === 'POST')).toHaveLength(3);
});

it('does not select a saved group with an incompatible product kind', async () => {
  api.mockImplementation(async (_endpoint, request) => request.path === groupPath && request.method === 'POST'
    ? { ...drawerResponse(request) as object, allowed_kind: 'SERVICE' } as never : drawerResponse(request) as never);
  const { changed } = reference(); const panel = await openGroup(); await fill(panel);
  await userEvent.click(within(panel).getByRole('button', { name: 'Create item group' }));
  await within(panel).findByText(/its allowed kind or active status could not be verified/);
  expect(changed).not.toHaveBeenCalled();
});
it('respects native protected create fields inside the drawer', async () => {
  api.mockImplementation(async (_endpoint, request) => {
    const result = drawerResponse(request);
    if (request.path.includes('/entities/catalog.item_group/field-set')) {
      const metadata = result as { fields: Array<{ writable: boolean }> };
      return { ...metadata, fields: metadata.fields.map(field => ({ ...field, writable: false })) } as never;
    }
    return result as never;
  });
  reference(); const panel = await openGroup();
  expect(within(panel).getByRole('textbox', { name: 'Code' })).toBeDisabled();
  expect(within(panel).getByRole('button', { name: 'Create item group' })).toBeDisabled();
  expect(api.mock.calls.some(call => call[1].method === 'POST')).toBe(false);
});
it('retries an uncertain type publication with the same version body and key', async () => {
  let attempts = 0;
  api.mockImplementation(async (_endpoint, request) => {
    if (request.path.endsWith('/publish') && ++attempts === 1) throw { status: 503, message: 'Publication connection interrupted.' };
    return drawerResponse(request) as never;
  });
  const { changed } = reference('product-type-revisions'); const panel = await createTypeDraft();
  await userEvent.click(await within(panel).findByRole('button', { name: 'Publish requirements' }));
  const confirm = await screen.findByRole('dialog', { name: 'Publish product type requirements?' });
  await userEvent.click(within(confirm).getByRole('button', { name: 'Publish requirements' }));
  await userEvent.click(await within(confirm).findByRole('button', { name: 'Retry same publication' }));
  await waitFor(() => expect(changed).toHaveBeenCalledWith(FRESH));
  const attemptsMade = api.mock.calls.map(call => call[1]).filter(call => call.path.endsWith('/publish'));
  expect(attemptsMade).toHaveLength(2); expect(attemptsMade[1].body).toEqual(attemptsMade[0].body); expect(attemptsMade[1].key).toBe(attemptsMade[0].key);
});
