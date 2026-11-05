import { notFound } from 'next/navigation';
import { ConsoleShell } from '../../components/ConsoleShell';
import { InventoryOverview } from '../../components/InventoryOverview';
import { inventoryGroups } from '../../lib/inventory-navigation';
import { pageContext } from '../../lib/page-context';
import { Providers } from '../../providers';

export default async function InventoryPage({
  params,
}: {
  params: Promise<{ segments?: string[] }>;
}) {
  const { segments = [] } = await params;
  if (
    segments.length > 1 ||
    (segments.length === 1 &&
      !inventoryGroups.some((group) => group.key === segments[0]))
  )
    notFound();
  const { session, context } = await pageContext();
  return (
    <Providers session={session}>
      <ConsoleShell
        session={session}
        context={context}
        activeHref={'/inventory' + (segments.length ? '/' + segments[0] : '')}
      >
        <InventoryOverview
          session={session}
          context={context}
          groupKey={segments[0]}
        />
      </ConsoleShell>
    </Providers>
  );
}
