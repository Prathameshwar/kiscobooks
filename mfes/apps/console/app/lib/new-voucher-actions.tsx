import { PaymentsIcon, ReceiptIcon, StockIcon, StoreIcon, WalletIcon, type MenuItem } from '@janso/ui';
import type { Session } from '../session';
import { companyPermission } from './company-permissions';

/** Voucher creation destinations. The shell offers them only with current company read/create grants. */
export const newVoucherActions: readonly MenuItem[] = [
  { id: '/vouchers/new/sales', href: '/vouchers/new/sales', label: 'Sales', icon: <ReceiptIcon size={15} /> },
  { id: '/vouchers/new/receipt', href: '/vouchers/new/receipt', label: 'Receipt', icon: <WalletIcon size={15} /> },
  {
    id: '/vouchers/new/purchase',
    href: '/vouchers/new/purchase',
    label: 'Purchase',
    icon: <StoreIcon size={15} />,
    separatorBefore: true,
  },
  { id: '/vouchers/new/payment', href: '/vouchers/new/payment', label: 'Payment', icon: <PaymentsIcon size={15} /> },
  {
    id: '/vouchers/new/stock-adjustment',
    href: '/vouchers/new/stock-adjustment',
    label: 'Stock adjustment',
    icon: <StockIcon size={15} />,
    separatorBefore: true,
  },
];

/** A new voucher needs an open company and current read/create grants; every destination rechecks them. */
export function showNewVoucher(session: Session): boolean {
  const company = session.company.id;
  return !!company && companyPermission(session, 'vouchers.read', company)
    && companyPermission(session, 'vouchers.create', company);
}
