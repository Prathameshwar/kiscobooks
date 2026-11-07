import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { ProductWarehousePolicies } from '../app/components/ProductWarehousePolicies';
import { WarehousePolicyReleases } from '../app/components/WarehousePolicyReleases';
import { serviceCall } from '../app/lib/service-call';
import { operationLabels } from '../app/lib/warehouse-ui';
vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
const company = '01990000-0000-7000-8000-000000000001', item = '01990000-0000-7000-8000-000000000002';
const keys = ['effective_date', 'change_reason', 'selection_mode', 'default_sale_warehouse_id', 'default_purchase_warehouse_id', 'default_customer_return_warehouse_id', 'default_opening_warehouse_id', 'warehouse_id', 'purchase_binding_id', 'safety_quantity', 'reorder_quantity', 'target_quantity', 'min_order_quantity', 'max_order_quantity', 'order_multiple', 'lead_time_days', ...Object.keys(operationLabels)];
let writes: Record<string, unknown>[];
beforeEach(() => {
  writes = [];
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
    if (request.method) { writes.push(request); return {}; }
    if (request.path.includes('/entities/')) return { company_id: company, entity_type: request.path.split('/entities/')[1]!.split('/')[0], fields: keys.map(key => ({ key, visible: true, writable: true })) } as never;
    if (request.path.endsWith('/warehouse-configuration')) return { company_id: company, location_mode: 'MULTI_LOCATION' } as never;
    if (request.path.includes('/unit-bindings')) return { items: [{ id: item, item_id: item, usage_role: 'BASE', code: 'PCS' }], page: { has_more: false } } as never;
    if (request.path.endsWith('/policy-releases')) return { policy_generation: 1, source_version: 1, history: [], current: null } as never;
    return { item_id: item, policy_generation: 1, source_version: 1, selection_mode: 'ALLOW_ALL_ACTIVE', locations: [], scopes: [] } as never;
  });
});
it('keeps unsaved replenishment when saving the location policy', async () => {
  render(<ProductWarehousePolicies company={company} item={item} canManage />);
  fireEvent.click(await screen.findByRole('button', { name: 'Add replenishment band' }));
  fireEvent.change(screen.getByLabelText('Target quantity'), { target: { value: '17.1250' } });
  fireEvent.click(screen.getByRole('button', { name: 'Review location policy' }));
  fireEvent.click(screen.getByRole('button', { name: 'Save policy' }));
  await waitFor(() => expect(writes).toHaveLength(1));
  await waitFor(() => expect(screen.getByLabelText('Target quantity')).toHaveValue('17.1250'));
  expect(writes[0]?.method).toBe('PUT');
});
it('shows release history while withholding publication without authority', async () => {
  render(<WarehousePolicyReleases company={company} canPublish={false} />);
  await screen.findByText('Release history');
  expect(screen.queryByRole('button', { name: 'Review release' })).toBeNull();
  expect(writes).toHaveLength(0);
});
