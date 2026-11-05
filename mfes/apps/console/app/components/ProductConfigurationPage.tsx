import { DEFAULT_DISPLAY_CONFIG, ErrorState } from '@janso/ui';
import { notFound } from 'next/navigation';
import { Providers } from '../providers';
import { pageContext } from '../lib/page-context';
import { companyPermission } from '../lib/company-permissions';
import { ConsoleShell } from './ConsoleShell';
import { NoCompany } from './NoCompany';
import { ProductConfigurationDirectory, ProductConfigurationScope } from './ProductConfigurationDirectory';
import { ProductConfigurationEditor } from './ProductConfigurationEditor';
import { ProductConfigurationDetail } from './ProductConfigurationDetail';
import { ProductConfigurationAdoption, ProductConfigurationEffective } from './ProductConfigurationInspect';

export async function ProductConfigurationPage({ segments = [], query = {} }: { segments?: string[]; query?: Record<string, string | string[] | undefined> } = {}) {
  const uuid = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
  const directory = !segments.length, creatingScope = segments.length === 1 && segments[0] === 'new', effective = segments.length === 1 && segments[0] === 'effective', adoption = segments.length === 1 && segments[0] === 'adopt';
  const scope = segments[0] === 'scopes' && uuid.test(segments[1] ?? ''), draft = segments[0] === 'drafts' && uuid.test(segments[1] ?? ''), revision = segments[0] === 'revisions' && uuid.test(segments[1] ?? '');
  const newDraft = scope && segments.length === 4 && segments[2] === 'drafts' && segments[3] === 'new', editing = draft && segments.length === 3 && segments[2] === 'edit';
  if (!(directory || creatingScope || effective || adoption || newDraft || editing || segments.length === 2 && (scope || draft || revision))) notFound();
  const { session, context } = await pageContext(), company = session.company.id, canRead = !!company && companyPermission(session, 'product_configuration.read', company), canManage = !!company && companyPermission(session, 'product_configuration.manage', company);
  const canPublish = !!company && companyPermission(session, 'product_configuration.publish', company), canAdopt = !!company && companyPermission(session, 'product_configuration.adopt', company);
  const returnTo = typeof query.returnTo === 'string' ? query.returnTo : undefined, id = segments[1]?.toLowerCase(), timezone = session.display.timezone ?? DEFAULT_DISPLAY_CONFIG.timezone;
  const params = new URLSearchParams(); for (const [key, value] of Object.entries(query)) if (typeof value === 'string') params.set(key, value);
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/products/configuration">
    {!company ? <NoCompany action="configure" context={context} canCreate={companyPermission(session, 'company.create')} /> : !canRead || (creatingScope || newDraft || editing) && !canManage ? <ErrorState status={403} detail="Product configuration read access and the requested action permission are required for this company." />
      : directory ? <ProductConfigurationDirectory key={company} company={company} canManage={canManage} canPublish={canPublish} canAdopt={canAdopt} initialQuery={params.toString()} />
      : creatingScope ? <ProductConfigurationEditor key={company} company={company} timezone={timezone} returnTo={returnTo} />
      : effective ? <ProductConfigurationEffective key={company} company={company} timezone={timezone} returnTo={returnTo} initialItemId={typeof query.item_id === 'string' && uuid.test(query.item_id) ? query.item_id : undefined} initialFamilyId={typeof query.family_id === 'string' && uuid.test(query.family_id) ? query.family_id : undefined} initialKind={query.kind === 'SERVICE' ? 'SERVICE' : 'GOODS'} />
      : adoption ? <ProductConfigurationAdoption key={company} company={company} timezone={timezone} canAdopt={canAdopt} returnTo={returnTo} initialItemId={typeof query.item_id === 'string' && uuid.test(query.item_id) ? query.item_id : undefined} />
      : editing || newDraft ? <ProductConfigurationEditor key={company + ':' + segments.join('/')} company={company} id={editing ? id : undefined} scopeId={newDraft ? id : undefined} timezone={timezone} returnTo={returnTo} />
      : scope ? <ProductConfigurationScope key={company + ':' + id} company={company} id={id!} canManage={canManage} returnTo={returnTo} />
      : <ProductConfigurationDetail key={company + ':' + segments.join('/')} company={company} id={id!} revision={revision} canManage={canManage} canPublish={canPublish} timezone={timezone} returnTo={returnTo} />}
  </ConsoleShell></Providers>;
}
