import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { PurchaseWorkspaceGrid } from '../app/components/PurchaseWorkspaceGrid';
import { PurchaseMobileLines } from '../app/components/PurchaseMobileLines';
import { PurchaseLineEditor } from '../app/components/PurchaseLineEditor';
import { PURCHASE_DEMO_POLICY, blankPurchaseLine, purchaseExample } from '../app/lib/purchase-workspace';
import { serviceCall } from '../app/lib/service-call';

vi.mock('../app/lib/service-call', () => ({ serviceCall: vi.fn() }));
const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const company = id(1), supplier = id(2), product = id(3);
const policy = { ...PURCHASE_DEMO_POLICY, live: true, stockCompany: company, supplierHistoryAccess: true,
  suppliers: [{ id: supplier, label: 'Acme Supplies', meta: '', payables: [] }],
  subjects: [{ id: product, label: 'Paper boxes', meta: '', kind: 'ITEM' as const, unit: 'pcs' }] };
const draft = (mode: 'ITEMS' | 'MIXED' | 'ACCOUNTS' = 'ITEMS') => {
  const value = purchaseExample('2026-11-05');
  value.mode = mode; value.supplier = supplier;
  value.lines = mode === 'ACCOUNTS' ? [{ ...blankPurchaseLine('p1', 'ACCOUNT'), subject: id(4), label: 'Repairs' }]
    : [{ ...value.lines[0]!, kind: 'ITEM', subject: product, label: 'Paper boxes', unit: 'pcs' }];
  return value;
};

describe('purchase product history placement', () => {
  it.each(['ITEMS', 'MIXED'] as const)('shows the history icon beside a selected product in read-only %s grid lines', async mode => {
    vi.clearAllMocks();
    vi.mocked(serviceCall).mockResolvedValue({ items: [], page: { next_cursor: null } } as never);
    const dispatch = vi.fn();
    render(<PurchaseWorkspaceGrid draft={draft(mode)} policy={policy} dispatch={dispatch} problems={[]} disabled keepGrid={false}
      onDetails={vi.fn()} onEdit={vi.fn()} onUnstorable={vi.fn()} />);
    const icon = screen.getByRole('button', { name: 'Purchase history for Paper boxes' });
    expect(icon).toBeEnabled();
    expect(icon.closest('.janso-entry-cell__with-action')).toBeInTheDocument();
    expect(serviceCall).not.toHaveBeenCalled();
    icon.focus(); await userEvent.setup().keyboard('{Enter}');
    expect(await screen.findByRole('dialog', { name: 'Paper boxes · purchase history' })).toBeVisible();
    expect(dispatch).not.toHaveBeenCalled();
  });

  it('shows the icon on compact cards and omits it from account-only lines', () => {
    const { rerender } = render(<PurchaseMobileLines draft={draft('MIXED')} policy={policy} dispatch={vi.fn()} problems={[]} disabled onEdit={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Purchase history for Paper boxes' }).closest('.janso-purchase-mobile-product')).toBeInTheDocument();
    rerender(<PurchaseMobileLines draft={draft('ACCOUNTS')} policy={policy} dispatch={vi.fn()} problems={[]} disabled onEdit={vi.fn()} />);
    expect(screen.queryByRole('button', { name: /Purchase history for/ })).toBeNull();
  });

  it('keeps product history available before the supplier is selected', () => {
    const value = draft('ITEMS'); value.supplier = '';
    render(<PurchaseMobileLines draft={value} policy={policy} dispatch={vi.fn()} problems={[]} disabled onEdit={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Purchase history for Paper boxes' })).toBeEnabled();
  });

  it('opens and closes history inside a read-only compact line editor without closing the editor', async () => {
    vi.mocked(serviceCall).mockResolvedValue({ items: [], page: { next_cursor: null } } as never);
    const value = draft('MIXED'), user = userEvent.setup();
    render(<PurchaseLineEditor draft={value} line={value.lines[0]!} ordinal={1} policy={policy} canEdit={false} onApply={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByRole('dialog', { name: 'Review purchase line 1' })).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Purchase history for Paper boxes' }));
    expect(await screen.findByRole('dialog', { name: 'Paper boxes · purchase history' })).toBeVisible();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog', { name: 'Paper boxes · purchase history' })).toBeNull();
    expect(screen.getByRole('dialog', { name: 'Review purchase line 1' })).toBeVisible();
  });
});
