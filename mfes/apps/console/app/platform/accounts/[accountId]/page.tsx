import { notFound } from 'next/navigation';
import { Notice } from '@janso/ui';
import { ConsoleShell } from '../../../components/ConsoleShell';
import { Providers } from '../../../providers';
import { pageContext } from '../../../lib/page-context';
import { AccountDetail } from '../AccountDetail';

export default async function AccountPage({ params, searchParams }: { params: Promise<{ accountId:string }>; searchParams:Promise<{ returnTo?:string }> }) {
  const [{session,context}, {accountId}, query] = await Promise.all([pageContext(),params,searchParams]);
  if (!/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(accountId)) notFound();
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/platform/accounts">
    {session.permissions.includes('platform.account.read') ? <AccountDetail accountId={accountId} permissions={session.permissions} returnTo={query.returnTo} draftScope={session.user.id} /> : <Notice tone="danger">Platform account-read permission is required.</Notice>}
  </ConsoleShell></Providers>;
}
