import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { configBody, configFields, configInitial, useConfigList, useConfigRead, type ConfigSections, type ConfigValues } from '../app/lib/product-configuration';
import { serviceCall } from '../app/lib/service-call';
import { COMPANY, draft, metadata, page } from './product-configuration-fixtures';
vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
const values = () => ({ details: { effective_from: '2028-01-01', change_reason: 'Reviewed defaults' }, options: { barcode_mode: 'INHERIT', barcode_default: null }, profiles: { goods_type_revision_mode: 'INHERIT', goods_type_revision_id: null }, pricing: { sale_price_mode: 'INHERIT', sale_level_count: null }, numeric_defaults: [] } as Record<ConfigSections, ConfigValues | ConfigValues[]>);
beforeEach(() => vi.clearAllMocks());
it.each([
  ['details', 'effective_from', '2028-02-30'], ['details', 'effective_from', null], ['details', 'change_reason', null],
  ['options', 'barcode_mode', 'UNKNOWN'], ['options', 'barcode_default', 'yes'], ['options', 'barcode_default', 1],
  ['profiles', 'goods_type_revision_id', 'unknown-reference'], ['profiles', 'goods_type_revision_mode', null],
  ['pricing', 'sale_level_count', -1], ['pricing', 'sale_level_count', 0], ['pricing', 'sale_level_count', 65], ['pricing', 'sale_level_count', '1.5'],
])('rejects an invalid %s.%s value before a command', (section, key, value) => { const current = values(); (current[section as ConfigSections] as ConfigValues)[key as string] = value; expect(Object.keys(configBody(metadata, current).errors).length).toBeGreaterThan(0); });
it('normalizes an empty optional integer and trims a changed reason', () => { const current = values(); current.pricing = { sale_price_mode: 'INHERIT', sale_level_count: '' }; (current.details as ConfigValues).change_reason = '  Reviewed defaults  '; expect(configBody(metadata, current).body).toMatchObject({ change_reason: 'Reviewed defaults', pricing: { sale_level_count: null } }); });
it('rejects a retained reference after switching its mode to clear', () => { const current = values(); current.profiles = { goods_type_revision_mode: 'CLEAR', goods_type_revision_id: COMPANY }; expect(configBody(metadata, current).errors['profiles.goods_type_revision_mode']).toBeTruthy(); });
it.each([
  { dimension: 'INVALID', quantity_decimal_places: 0, quantity_increment: '1' },
  { dimension: 'COUNT', quantity_decimal_places: -1, quantity_increment: '1' },
  { dimension: 'COUNT', quantity_decimal_places: 5, quantity_increment: '1' },
  { dimension: 'COUNT', quantity_increment: '1' },
  { dimension: 'COUNT', price_increment: '1' },
  { dimension: 'COUNT', price_decimal_places: 2, currency: 'inr' },
  { dimension: 'COUNT', price_decimal_places: 2, currency: 'INR', price_increment: '0.001' },
  { dimension: 'COUNT', price_basis_quantity: '0' },
  { dimension: 'COUNT', price_basis_quantity: '-2' },
])('rejects incompatible numeric defaults %j', row => { const current = values(); current.numeric_defaults = [row]; expect(Object.keys(configBody(metadata, current).errors).length).toBeGreaterThan(0); });
it('rejects an invalid optimistic version and omits protected scalar fields', () => { const current = values(), fields = structuredClone(metadata); fields.details[1]!.visible = false; fields.options[0]!.conditional_access = true; expect(configBody(fields, current, { ...draft, row_version: 0 }).errors.version).toBeTruthy(); expect(configBody(fields, current).body).not.toHaveProperty('change_reason'); });
it('preserves a numeric collection unchanged after stripping its server ownership fields', () => {
  const current = values(); current.options = { barcode_mode: 'OPTIONAL', barcode_default: true }; current.details = { effective_from: draft.effective_from, change_reason: draft.change_reason };
  const row = { dimension: 'COUNT' as const, quantity_decimal_places: 0, quantity_increment: '1.0000', price_decimal_places: null, price_increment: null, price_basis_quantity: null, currency: null };
  current.numeric_defaults = [row]; expect(configBody(metadata, current, { ...draft, numeric_defaults: [{ id: COMPANY, draft_id: draft.id, ...row }] }).body).toEqual({ expected_version: 3 });
});
it('handles older optional choice arrays but rejects duplicate field metadata', () => {
  const field = { ...metadata.options[0]!, control: { ...metadata.options[0]!.control!, choices: undefined } };
  const loaded = configFields({ company_id: COMPANY, entity_type: 'test', source_version: 1, fields: [field] }, COMPANY, 'test'); expect(configInitial(loaded)).toEqual({ barcode_mode: '' });
  expect(() => configFields({ company_id: COMPANY, entity_type: 'test', source_version: 1, fields: [field, field] }, COMPANY, 'test')).toThrow();
});
it('paginates with an opaque cursor, returns to the first page and resets on a filter change', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_, request) => ({ items: [], page: { ...page, has_more: !request.path.includes('cursor='), next_cursor: request.path.includes('cursor=') ? null : 'opaque-next' } }));
  const { result, rerender } = renderHook(({ filter }) => useConfigList('/scopes', filter), { initialProps: { filter: 'scope_kind=COMPANY' } });
  await waitFor(() => expect(result.current.loading).toBe(false)); act(() => result.current.next()); await waitFor(() => expect(result.current.hasPrevious).toBe(true)); await waitFor(() => expect(result.current.loading).toBe(false)); expect(vi.mocked(serviceCall).mock.calls.at(-1)![1].path).toContain('cursor=opaque-next');
  act(() => result.current.previous()); await waitFor(() => expect(result.current.hasPrevious).toBe(false)); act(() => result.current.setLimit(50)); await waitFor(() => expect(result.current.data?.page.limit).toBe(25));
  act(() => result.current.first()); rerender({ filter: 'status=DRAFT' }); await waitFor(() => expect(vi.mocked(serviceCall).mock.calls.at(-1)![1].path).toContain('status=DRAFT')); expect(result.current.hasPrevious).toBe(false);
});
it('surfaces a verified-read failure and supports an explicit fresh read', async () => {
  vi.mocked(serviceCall).mockResolvedValueOnce({ invalid: true }).mockResolvedValueOnce({ valid: true });
  const { result } = renderHook(() => useConfigRead<{ valid: boolean }>('/scope', value => { if (!value.valid) throw { status: 502, message: 'Unverified response' }; }));
  await waitFor(() => expect(result.current.failure?.status).toBe(502)); act(() => result.current.refresh()); await waitFor(() => expect(result.current.data?.valid).toBe(true));
});
