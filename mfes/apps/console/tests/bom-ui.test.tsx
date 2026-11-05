import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { BomMasterPage } from '../app/components/BomMasterPage';
import { BomAssignment } from '../app/components/BomAssignment';
import { BomDefinition } from '../app/components/BomDefinition';
import { masterConfig, type MasterField } from '../app/lib/catalog-masters';
import { serviceCall } from '../app/lib/service-call';
import { newBomLine } from '../app/lib/boms';
import fields from './bom-fields.json';

vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/sign-in' }));
const api = vi.mocked(serviceCall);
const company = '01990000-0000-7000-8000-000000000001', bom = '01990000-0000-7000-8000-000000000002', draft = '01990000-0000-7000-8000-000000000003';
const publication = '01990000-0000-7000-8000-000000000004';
const access = { manage: true, publish: true, assign: true, goods: true, units: true, routes: true, warehouses: true };
const page = (items: unknown[]) => ({ items, page: { limit: 200, has_more: false, next_cursor: null } });
const header = () => ({ id: bom, company_id: company, code: 'MAKE', name: 'Assembly recipe', is_active: true, row_version: 1 });
let enabled: boolean, published: boolean, incomplete: boolean, failSave: boolean;
let editedFields: Record<string, MasterField[]>;
const recipe = () => ({ id: draft, company_id: company, bom_id: bom, draft_number: 1, row_version: published ? 2 : 1, status: published ? 'PUBLISHED' : 'DRAFT', published_revision_id: published ? publication : null,
  specification: 'Assemble the reviewed goods', change_reason: 'Initial recipe', definition_date: '2090-01-01', route_revision_id: null, batch_minimum: null, batch_maximum: null, batch_multiple: null, component_count: 0, output_count: 1 });
const output = { ...newBomLine('outputs', 1), id: publication, draft_id: draft, revision_id: null, item_id: bom, unit_revision_id: publication, nominal_quantity: '10.0000', yield_fraction: '1.00000000', role: 'PRIMARY' };
beforeEach(() => {
  vi.clearAllMocks(); enabled = true; published = false; incomplete = false; failSave = false;
  editedFields = structuredClone(fields) as Record<string, MasterField[]>;
  api.mockImplementation(async (_endpoint, request) => {
    const url = new URL(request.path, 'https://test.invalid'), path = url.pathname;
    if (path.endsWith('/field-set')) { const entity = path.split('/').at(-2)!.replace('catalog.', ''); return { company_id: company, entity_type: 'catalog.' + entity, fields: editedFields[entity + ':' + (url.searchParams.get('operation') ?? 'read')] } as never; }
    if (path.endsWith('/authoring-context')) return { company_id: company, enabled, operational_ready: false } as never;
    if (path.endsWith('/options/references/goods/' + bom)) return { id: bom, source: 'goods', parent_id: bom, code: 'FG', name: 'Finished goods' } as never;
    if (path.endsWith('/options/references/units/' + publication)) return { id: publication, source: 'units', parent_id: bom, code: 'BASE', name: 'Pieces', revision: 1 } as never;
    if (path.endsWith('/outputs')) return { ...page([output]), ...(incomplete ? { page: { limit: 200, has_more: true, next_cursor: 'more' } } : {}) } as never;
    if (path.endsWith('/components')) return page([]) as never;
    if (path.endsWith('/drafts/' + draft + '/publish')) { published = true; return recipe() as never; }
    if (path.endsWith('/drafts/' + draft)) return recipe() as never;
    if (path.endsWith('/boms') && request.method === 'POST') { if (failSave) { failSave = false; throw { status: 503, message: 'Save result uncertain' }; } return header() as never; }
    if (path.endsWith('/boms/' + bom)) return header() as never;
    if (path.endsWith('/boms')) return page([header()]) as never;
    if (path.endsWith('/drafts') || path.endsWith('/revisions') || path.endsWith('/bom-assignments')) return page([]) as never;
    throw { status: 404, message: 'Unexpected test request: ' + path };
  });
});

it('creates a BOM in shared form cards and retains an exact retry after an uncertain result', async () => {
  failSave = true;
  render(<BomMasterPage company={company} config={masterConfig('boms')!} record={['new']} access={access} />);
  fireEvent.change(await screen.findByRole('textbox', { name: 'Code' }), { target: { value: 'MAKE' } });
  fireEvent.change(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'Assembly recipe' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save BOM' }));
  expect(await screen.findByRole('button', { name: 'Retry save' })).toBeEnabled();
  expect(screen.getByRole('textbox', { name: 'Code' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Retry save' }));
  expect(await screen.findByRole('link', { name: 'Open BOM' })).toHaveAttribute('href', '/masters/boms/' + bom);
  const writes = api.mock.calls.map(call => call[1]).filter(request => request.method === 'POST');
  expect(writes).toHaveLength(2); expect(writes[0]!.key).toBe(writes[1]!.key); expect(writes[0]!.body).toEqual(writes[1]!.body);
  expect(screen.getByRole('link', { name: 'Add recipe' })).toHaveAttribute('href', '/masters/boms/' + bom + '/drafts/new');
});
it('keeps BOM authoring unavailable when the company capability is off', async () => {
  enabled = false;
  render(<BomMasterPage company={company} config={masterConfig('boms')!} record={['new']} access={access} />);
  expect(await screen.findByText(/Enable BOM definitions/)).toBeVisible();
  expect(screen.getByRole('button', { name: 'Save BOM' })).toBeDisabled();
  expect(api.mock.calls.some(call => call[1].method === 'POST')).toBe(false);
});
it('does not replace or publish an incomplete paged recipe', async () => {
  incomplete = true;
  render(<BomDefinition company={company} bom={bom} id={draft} published={false} access={access} />);
  expect(await screen.findByText(/complete BOM line set is unavailable/)).toBeVisible();
  expect(screen.getByRole('button', { name: 'Save draft' })).toBeDisabled();
  expect(screen.queryByRole('button', { name: 'Review and publish' })).not.toBeInTheDocument();
});
it('publishes only after reviewing a complete recipe and keeps the resulting publication link', async () => {
  render(<BomDefinition company={company} bom={bom} id={draft} published={false} access={access} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Review and publish' }));
  expect(api.mock.calls.some(call => call[1].path.endsWith('/publish'))).toBe(false);
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Publish recipe' }));
  await waitFor(() => expect(screen.getByRole('textbox', { name: 'Specification' })).toBeDisabled());
  expect(await screen.findByText(/Published recipe.*immutable/)).toBeVisible();
  expect(screen.getByRole('link', { name: 'Open published recipe' })).toHaveAttribute('href', `/masters/boms/${bom}/revisions/${publication}`);
});
it('requires readable complete child fields before allowing aggregate replacement', async () => {
  for (const operation of ['read', 'update', 'publish']) editedFields['bom_output:' + operation] = editedFields['bom_output:' + operation]!.filter(field => field.key !== 'nominal_quantity');
  render(<BomDefinition company={company} bom={bom} id={draft} published={false} access={access} />);
  expect(await screen.findByText(/complete recipe and its native fields cannot be reviewed/)).toBeVisible();
  expect(screen.getByRole('button', { name: 'Save draft' })).toBeDisabled();
  expect(api.mock.calls.some(call => call[1].path.includes('/outputs?'))).toBe(false);
});

it('does not send an invalid run count to quantity preview', async () => {
  render(<BomDefinition company={company} bom={bom} id={draft} published={false} access={access} />);
  fireEvent.change(await screen.findByRole('textbox', { name: 'Requested good output' }), { target: { value: '10' } });
  fireEvent.change(screen.getByRole('textbox', { name: 'Run count' }), { target: { value: '1.5' } });
  fireEvent.click(screen.getByRole('button', { name: 'Calculate quantities' }));
  expect(await screen.findByText('Enter a whole run count from 1 to 1000.')).toBeVisible();
  expect(api.mock.calls.some(call => call[1].path.endsWith('/preview'))).toBe(false);
});
it('respects denied publication snapshot fields', async () => {
  editedFields['bom_revision:publish'] = editedFields['bom_revision:publish']!.map(field => field.key === 'content_sha256' ? { ...field, writable: false } : field);
  render(<BomDefinition company={company} bom={bom} id={draft} published={false} access={access} />);
  await screen.findByText(/Draft recipe.*save changes/);
  expect(screen.queryByRole('button', { name: 'Review and publish' })).not.toBeInTheDocument();
});

it('allows withdrawal while authoring is off, confirms it and preserves an uncertain retry', async () => {
  enabled = false;
  const implementation = api.getMockImplementation()!;
  let first = true;
  api.mockImplementation(async (endpoint, request, subject) => {
    if (request.path.endsWith('/bom-assignments/' + publication + '/deactivate')) {
      if (first) { first = false; throw { status: 503, message: 'Withdrawal result uncertain' }; }
      return { id: publication, company_id: company, row_version: 2, is_active: false } as never;
    }
    if (request.path.endsWith('/bom-assignments/' + publication)) return { id: publication, company_id: company, row_version: 1, is_active: true, bom_revision_id: draft, warehouse_id: null, valid_from: '2090-01-01', valid_to: null, change_reason: 'Initial applicability' } as never;
    if (request.path.endsWith('/revisions/' + draft)) return { ...recipe(), id: draft, revision: 1, status: 'PUBLISHED' } as never;
    return implementation(endpoint, request, subject);
  });
  render(<BomAssignment company={company} bom={bom} id={publication} access={access} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Withdraw applicability' }));
  expect(api.mock.calls.some(call => call[1].method === 'POST')).toBe(false);
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Withdraw applicability' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Retry withdrawal' }));
  expect(await screen.findByText('Recipe applicability withdrawn.')).toBeVisible();
  const writes = api.mock.calls.map(call => call[1]).filter(request => request.path.endsWith('/deactivate'));
  expect(writes).toHaveLength(2); expect(writes[0]!.key).toBe(writes[1]!.key); expect(writes[0]!.body).toEqual(writes[1]!.body);
});

it('retains the original BOM lifecycle request after an uncertain result', async () => {
  const implementation = api.getMockImplementation()!; let first = true;
  api.mockImplementation(async (endpoint, request, subject) => {
    if (request.path.endsWith('/boms/' + bom + '/deactivate')) {
      if (first) { first = false; throw { status: 503, message: 'Deactivation result uncertain' }; }
      return { ...header(), is_active: false, row_version: 2 } as never;
    }
    return implementation(endpoint, request, subject);
  });
  render(<BomMasterPage company={company} config={masterConfig('boms')!} record={[bom]} access={access} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Deactivate' }));
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Deactivate' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Retry deactivate' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  const writes = api.mock.calls.map(call => call[1]).filter(request => request.path.endsWith('/deactivate'));
  expect(writes).toHaveLength(2); expect(writes[0]!.key).toBe(writes[1]!.key); expect(writes[0]!.body).toEqual(writes[1]!.body);
});
