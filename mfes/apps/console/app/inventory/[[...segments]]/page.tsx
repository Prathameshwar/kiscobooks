import { notFound } from 'next/navigation';
import { ConsoleShell } from '../../components/ConsoleShell';
import { InventoryOverview } from '../../components/InventoryOverview';
import { inventoryGroups } from '../../lib/inventory-navigation';
import { pageContext } from '../../lib/page-context';
import { Providers } from '../../providers';
import { StockTrackingRoute } from '../../components/StockTrackingRoute';
import { trackingRoute } from '../../lib/stock-tracking-route';
import { trackingId } from '../../lib/stock-tracking-resources';

export default async function InventoryPage({
  params, searchParams,
}: {
  params: Promise<{ segments?: string[] }>; searchParams?: Promise<{ item_id?: string | string[] }>;
}) {
  const { segments = [] } = await params;
  let tracking: ReturnType<typeof trackingRoute> = null;
  try { tracking = trackingRoute(segments); } catch { notFound(); }
  const query = await searchParams;
  if (tracking && query?.item_id !== undefined && (typeof query.item_id !== 'string' || !trackingId.test(query.item_id))) notFound();
  if (!tracking && (
    segments.length > 1 ||
    (segments.length === 1 &&
      !inventoryGroups.some((group) => group.key === segments[0]))
  ))
    notFound();
  const { session, context } = await pageContext();
  return (
    <Providers session={session}>
      <ConsoleShell
        session={session}
        context={context}
        activeHref={'/inventory' + (segments.length ? '/' + segments[0] : '')}
      >
        {tracking ? <StockTrackingRoute route={tracking} session={session} context={context} itemId={query?.item_id as string | undefined} /> : <InventoryOverview
          session={session}
          context={context}
          groupKey={segments[0]}
        />}
      </ConsoleShell>
    </Providers>
  );
}
