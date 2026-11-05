import { notFound } from 'next/navigation';
import { Notice } from '@janso/ui';
import { pageContext } from '../../lib/page-context';
import { Providers } from '../../providers';
import { ConsoleShell } from '../../components/ConsoleShell';
import { catalogs, type Catalog } from './reference-config';
import { ReferenceRecord } from './ReferenceRecord';
export async function ReferenceRecordPage({ params, searchParams, mode }: { params: Promise<{ catalog: string; code?: string }>; searchParams: Promise<{ returnTo?: string; action?: string }>; mode: 'new' | 'view' | 'edit' }) {
  const { catalog, code } = await params, search = await searchParams;
  if (!catalogs.includes(catalog as Catalog) || (mode !== 'new' && (!code || !/^[A-Za-z0-9-]{2,6}$/.test(code)))) notFound();
  const { session, context } = await pageContext();
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref={'/platform/references/' + catalog}>{session.permissions.includes('platform.config.manage') ? <ReferenceRecord catalog={catalog as Catalog} code={code} mode={mode} returnTo={search.returnTo} action={search.action} /> : <Notice tone="danger">Platform configuration permission is required.</Notice>}</ConsoleShell></Providers>;
}
