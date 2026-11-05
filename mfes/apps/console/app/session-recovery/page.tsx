import { Notice, PageHeader } from '@janso/ui';
import { recoveryPath } from '../lib/session-recovery';
import { signInUrl } from '../lib/navigate';

// Public recovery UI: no session/tenant/company data is read or rendered here.
export default async function RecoveryPage({ searchParams }: {
  searchParams: Promise<{ reason?: string; returnTo?: string }>;
}) {
  const query = await searchParams;
  const denied = query.reason === 'access';
  return <main className="janso-main"><div className="janso-page">
    <PageHeader title={denied ? 'Workspace access unavailable' : 'Workspace temporarily unavailable'} />
    <Notice tone={denied ? 'danger' : 'warning'}>
      {denied ? 'Your current access does not allow this workspace to open. Sign in to check your access.'
        : 'The workspace service could not be reached or its response could not be verified. Try again shortly.'}
    </Notice>
    <div className="janso-form-actions">
      <a className="janso-btn janso-btn--primary" href={recoveryPath(query.returnTo)}>Try again</a>
      <a className="janso-btn janso-btn--ghost" href={signInUrl()}>Sign in</a>
    </div>
  </div></main>;
}
