import { notFound } from 'next/navigation';
import { Notice } from '@janso/ui';
import { pageContext } from '../../../lib/page-context';
import { Providers } from '../../../providers';
import { ConsoleShell } from '../../../components/ConsoleShell';
import { catalogs, type Catalog } from '../reference-config';
import { ReferenceDirectory } from '../ReferenceDirectory';
export default async function CatalogPage({ params }: { params: Promise<{ catalog: string }> }) {
  const { catalog } = await params; if (!catalogs.includes(catalog as Catalog)) notFound();
  const { session, context } = await pageContext();
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref={'/platform/references/' + catalog}>{session.permissions.includes('platform.config.manage') ? <ReferenceDirectory catalog={catalog as Catalog} /> : <Notice tone="danger">Platform configuration permission is required.</Notice>}</ConsoleShell></Providers>;
}
