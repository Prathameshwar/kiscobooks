import { ErrorState } from '@janso/ui';
import { Providers } from '../../providers';
import { ConsoleShell } from '../../components/ConsoleShell';
import { VoucherEntry } from '../../components/VoucherEntry';
import { NoCompany } from '../../components/NoCompany';
import { pageContext } from '../../lib/page-context';
import { companyPermission } from '../../lib/company-permissions';
import { notFound, redirect } from 'next/navigation';
import { newVoucherHref, voucherSelection, type VoucherSelection } from '../../lib/operate-navigation';

/**
 * Entry by selection (`?kind=…&type_id=…`), for the kinds that use the generic entry.
 *
 * Sales and Purchase each have one complete screen, `/vouchers/new/<kind>`. A link that still names
 * them here (an old bookmark, an older list) is sent to it rather than served a second copy of the
 * same workspace — two routes for one screen is how one of them ended up unstyled.
 */
export default async function VoucherEntryPage({ searchParams }: { searchParams?: Promise<VoucherSelection> }) {
  const selection = voucherSelection(await searchParams);
  if (!selection) notFound();
  if (selection.kind === 'SALES' || selection.kind === 'PURCHASE') redirect(newVoucherHref(selection.kind, selection.typeId, selection.returnTo));
  const { session, context } = await pageContext(), company = session.company.id;
  const permissions = session.permissions.filter(key => companyPermission(session, key, company));
  const entry = company ? <VoucherEntry key={company + (selection.kind ?? '') + (selection.typeId ?? '')} company={company} currency={session.display.currency ?? ''} permissions={permissions} initialKind={selection.kind} initialTypeId={selection.typeId} returnTo={selection.returnTo} canCreate /> : null;
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref={selection.returnTo ?? '/vouchers'}>{!company ? <NoCompany action="record" context={context} canCreate={companyPermission(session, 'company.create')} /> : permissions.includes('vouchers.read') && permissions.includes('vouchers.create') ? entry : <ErrorState status={403} />}</ConsoleShell></Providers>;
}
