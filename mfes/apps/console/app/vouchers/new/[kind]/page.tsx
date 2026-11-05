import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { Providers } from '../../../providers';
import { pageContext } from '../../../lib/page-context';
import { companyPermission } from '../../../lib/company-permissions';
import { ConsoleShell } from '../../../components/ConsoleShell';
import { NoCompany } from '../../../components/NoCompany';
import { SalesEntryConnected } from '../../../components/SalesEntryConnected';
import { VoucherEntry } from '../../../components/VoucherEntry';
import { PurchaseEntryConnected } from '../../../components/PurchaseEntryConnected';
import { trackingId } from '../../../lib/stock-tracking-resources';
import { ErrorState, PageNavigation } from '@janso/ui';
import { voucherSelection } from '../../../lib/operate-navigation';
import { partyCompanyCountry } from '../../../lib/party-company-country';

/**
 * Raising a voucher, by kind.
 *
 * The top bar's "New" menu has pointed at `/vouchers/new/<kind>` since it was built, so the
 * Sales, account Purchase, ordinary Receipt/Payment and physical counts use native entry workflows.
 *
 * An unrecognised kind *is* a 404 — it was never offered.
 */

export async function generateMetadata({ params }: { params: Promise<{ kind: string }> }): Promise<Metadata> {
  const { kind } = await params;
  if (!OFFERED[kind]) notFound();
  return { title: 'New ' + kind.replaceAll('-', ' ') + ' · KiscoBooks', description: 'Prepare a ' + OFFERED[kind].toLowerCase() + ' voucher for the selected company.' };
}

/** The kinds the top bar offers. Mirrors `lib/new-voucher-actions`, which owns the menu. */
const OFFERED: Record<string, string> = {
  sales: 'Sales',
  receipt: 'Receipt',
  purchase: 'Purchase',
  payment: 'Payment',
  'stock-adjustment': 'Stock adjustment',
};

export default async function NewVoucherPage({
  params,
  searchParams,
}: {
  params: Promise<{ kind: string }>;
  searchParams?: Promise<{ voucher_id?: string; type_id?: string | string[]; returnTo?: string | string[] }>;
}) {
  const { kind } = await params;
  const query = await searchParams;
  const resume = query?.voucher_id;
  if (kind === 'purchase' && resume !== undefined && (typeof resume !== 'string' || !trackingId.test(resume))) notFound();
  const offered = OFFERED[kind];
  if (!offered) notFound();
  // Sales and Purchase can be opened for one company voucher type, from an Operate list that Back returns to.
  // An unusable type is a 404 like any other bad selection; an unusable returnTo is simply dropped.
  const native = kind === 'sales' || kind === 'purchase';
  const selection = native ? voucherSelection({ kind: kind.toUpperCase(), type_id: query?.type_id, returnTo: query?.returnTo }) : undefined;
  if (native && !selection) notFound();
  const back = selection?.returnTo;
  const navigation = back ? <PageNavigation back={{ href: back, label: 'voucher list' }}
    breadcrumbs={kind === 'sales' ? [{ label: 'Voucher list', href: back }, { label: 'New sales bill' }] : undefined} /> : undefined;

  const { session, context } = await pageContext();
  const company = session.company.id;
  // Presentation only. Every destination re-resolves the actor's grants and the company scope
  // server-side, and the vouchers service authorizes again on arrival (CLAUDE.md §5.1–5.2).
  const canCreate = !!company && companyPermission(session, 'vouchers.create', company);
  const reviewingPurchase = kind === 'purchase' && resume !== undefined;
  const permissions = company ? session.permissions.filter(permission => companyPermission(session, permission, company)) : [];
  // The default country for a supplier created from the bill; only read for someone who can create one.
  const companyCountry = company && kind === 'purchase' && permissions.includes('accounting.party.manage') && permissions.includes('accounting.account.manage') ? await partyCompanyCountry(company) : undefined;

  return (
    <Providers session={session}>
      <ConsoleShell session={session} context={context} activeHref={back ?? '/vouchers/new/' + kind}>
        {!company ? (
          <NoCompany
            action="raise a voucher for"
            context={context}
            canCreate={companyPermission(session, 'company.create')}
          />
        ) : !permissions.includes('vouchers.read') || (!reviewingPurchase && !canCreate) ? (
          <ErrorState status={403} detail={permissions.includes('vouchers.read') ? 'Voucher creation access is required for this company.' : 'Voucher read access is required for this company.'} />
        ) : kind === 'purchase' ? (
          <PurchaseEntryConnected key={company + (selection?.typeId ?? '')} company={company} currency={session.display.currency ?? ''} actor={session.user.id ?? ''} year={context.fiscalYear?.id ?? 'unselected'} canCreate={canCreate} permissions={permissions} initialVoucherId={resume} initialTypeId={selection?.typeId} navigation={navigation} companyCountry={companyCountry} />
        ) : kind === 'receipt' || kind === 'payment' || kind === 'stock-adjustment' ? (
          <VoucherEntry key={company + ':' + kind} company={company} currency={session.display.currency ?? ''} canCreate={canCreate} permissions={permissions} initialKind={kind === 'receipt' ? 'RECEIPT' : kind === 'payment' ? 'PAYMENT' : kind === 'stock-adjustment' ? 'PHYSICAL_STOCK' : 'PURCHASE'} />
        ) : (
          <SalesEntryConnected key={company + (selection?.typeId ?? '')} company={company} canCreate={canCreate} initialTypeId={selection?.typeId} navigation={navigation} />
        )}
      </ConsoleShell>
    </Providers>
  );
}
