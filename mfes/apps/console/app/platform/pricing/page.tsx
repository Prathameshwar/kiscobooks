import { Notice } from '@janso/ui';
import { ConsoleShell } from '../../components/ConsoleShell';
import { Providers } from '../../providers';
import { pageContext } from '../../lib/page-context';
import { PricingDirectory } from './PricingDirectory';

export default async function PricingPage() {
  const { session, context } = await pageContext();
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/platform/pricing">
    {session.permissions.includes('platform.config.manage') ? <PricingDirectory scope={session.organisation.id ?? ''} />
      : <Notice tone="danger">Platform configuration permission is required.</Notice>}
  </ConsoleShell></Providers>;
}
