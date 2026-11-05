import { Notice } from '@janso/ui';
import { ConsoleShell } from '../../components/ConsoleShell';
import { Providers } from '../../providers';
import { pageContext } from '../../lib/page-context';
import { PlatformDetailsForm } from './PlatformDetailsForm';

export default async function PlatformDetailsPage() {
  const { session, context } = await pageContext();
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/platform/details">
    {session.permissions.includes('platform.config.manage') ? <PlatformDetailsForm scope={session.organisation.id ?? ''} />
      : <Notice tone="danger">Platform configuration permission is required.</Notice>}
  </ConsoleShell></Providers>;
}
