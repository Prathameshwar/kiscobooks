import { notFound } from 'next/navigation';
import { Notice } from '@janso/ui';
import { Providers } from '../../providers';
import { ConsoleShell } from '../../components/ConsoleShell';
import { AssignmentDirectory } from '../../components/AssignmentDirectory';
import { AssignmentEditor } from '../../components/AssignmentEditor';
import { accessContext } from '../../lib/access-context';
import { pageContext } from '../../lib/page-context';

export default async function AssignmentsPage({ params, searchParams }: {
  params: Promise<{ segments?: string[] }>; searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { session, context } = await pageContext(), access = accessContext(session);
  const { segments = [] } = await params, search = await searchParams;
  if (segments.length > 1 || segments[0] && segments[0] !== 'new') notFound();
  const creating = segments[0] === 'new', returnTo = typeof search.returnTo === 'string' ? search.returnTo : undefined;
  const subjectId = typeof search.subject_id === 'string' && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(search.subject_id) ? search.subject_id : undefined;
  const query = new URLSearchParams(Object.entries(search).flatMap(([key, value]) => typeof value === 'string' ? [[key, value]] : [])).toString();
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/assignments">
    {!access.permissions.includes('role.read') || creating && !access.permissions.includes('role.assign') ? <Notice tone="danger">Role read and assignment permissions are required for this action.</Notice>
      : creating ? <AssignmentEditor key={access.tenantId + ':' + access.companyId} context={access} returnTo={returnTo} initialSubject={subjectId} /> : <AssignmentDirectory key={access.tenantId + ':' + access.companyId} context={access} initialQuery={query} returnTo={returnTo} />}
  </ConsoleShell></Providers>;
}
