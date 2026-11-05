import { notFound } from 'next/navigation';
import { ErrorState } from '@janso/ui';
import { OperateFrame } from '../../components/OperateFrame';
import { VoucherImportLanding } from '../../components/VoucherImportLanding';
import { voucherSelection, type VoucherSelection } from '../../lib/operate-navigation';

export default async function ImportPage({ searchParams }: { searchParams?: Promise<VoucherSelection> }) {
  const selection = voucherSelection(await searchParams);
  if (!selection) notFound();
  return OperateFrame({ href: selection.returnTo ?? '/vouchers', children: (company, permissions) => permissions.includes('vouchers.import.read')
    ? <VoucherImportLanding key={company+(selection.kind??'')+(selection.typeId??'')} company={company} permissions={permissions} kind={selection.kind} typeId={selection.typeId} returnTo={selection.returnTo} />
    : <ErrorState status={403} detail="Voucher import read access is required for this company." /> });
}
