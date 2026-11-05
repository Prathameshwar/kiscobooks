import { Notice } from '@janso/ui';
import { ConsoleShell } from '../../../components/ConsoleShell';
import { Providers } from '../../../providers';
import { pageContext } from '../../../lib/page-context';
import { TenantForm } from '../TenantForm';

export default async function NewTenantPage({ searchParams }: { searchParams: Promise<{ returnTo?: string }> }) {
  const [{ session, context }, query] = await Promise.all([pageContext(), searchParams]);
  // WizardLayout owns the masthead, step rail and viewport scroll container.
  // Keep the regular shell for access errors, as in the company creation route.
  return <Providers session={session}>
    {['platform.tenant.read', 'platform.tenant.create'].every(permission => session.permissions.includes(permission))
      ? <TenantForm scope={session.organisation.id ?? ''} returnTo={query.returnTo} />
      : <ConsoleShell session={session} context={context} activeHref="/platform/tenants"><Notice tone="danger">Tenant creation permission is required.</Notice></ConsoleShell>}
  </Providers>;
}
