import { Notice } from '@janso/ui';
import { ConsoleShell } from '../../components/ConsoleShell';
import { Providers } from '../../providers';
import { pageContext } from '../../lib/page-context';
import { AccountDirectory } from './AccountDirectory';

export default async function AccountsPage() {
  const { session, context } = await pageContext();
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/platform/accounts">
    {session.permissions.includes('platform.account.read') ? <AccountDirectory permissions={session.permissions} /> : <Notice tone="danger">Platform account-read permission is required.</Notice>}
  </ConsoleShell></Providers>;
}
