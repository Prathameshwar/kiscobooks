'use client';

import { lazy, Suspense, useCallback, useRef, useState, type ReactNode } from 'react';
import { Button, ConfirmDialog, Drawer, IconButton, Notice, PlusIcon } from '@janso/ui';
import type { components as CatalogComponents } from '@janso/api-client/catalog';
import { masterConfig, type MasterRow } from '../lib/catalog-masters';
import { masterRequest } from '../lib/catalog-master-api';
import { catalogBase, catalogId } from '../lib/product-classification';
import type { ClassificationAccess } from '../lib/product-classification-resources';
import type { ServicePage } from '../lib/service-resource';
import { requestFailure } from '../lib/service-call';

const GroupEditor = lazy(() => import('./CatalogMasterEditor').then(module => ({ default: module.CatalogMasterEditor })));
const TypeEditor = lazy(() => import('./ProductCatalogEditor').then(module => ({ default: module.ProductCatalogEditor })));
const RequirementsEditor = lazy(() => import('./ProductTypeRevision').then(module => ({ default: module.ProductTypeRevision })));
type Resource = 'item-groups' | 'product-type-revisions';

/** The owning forms retain their field policies, commands and publication confirmation. */
function ReferenceCreateDrawer({ company, resource, kind, access, onCreated, onClose }: {
  company: string; resource: Resource; kind: string; access: ClassificationAccess;
  onCreated: (id: string) => void; onClose: () => void;
}) {
  const [master, setMaster] = useState<MasterRow | null>(null);
  const [revision, setRevision] = useState<MasterRow | null>(null);
  const [state, setState] = useState({ dirty: false, busy: false });
  const [discard, setDiscard] = useState(false), [problem, setProblem] = useState('');
  const verifying = useRef(false);
  const group = resource === 'item-groups';
  const close = useCallback(() => {
    if (state.busy || verifying.current) return;
    if (state.dirty) setDiscard(true); else onClose();
  }, [state.busy, state.dirty, onClose]);
  function savedMaster(row: MasterRow) {
    setState({ dirty: false, busy: false });
    setMaster(row);
    if (!group) return;
    if (!catalogId.test(row.id) || row.company_id !== company || row.is_active !== true || ![kind, 'BOTH'].includes(String(row.allowed_kind))) {
      setProblem('The group was created, but its allowed kind or active status could not be verified for this product. Your product selection is unchanged.');
      return;
    }
    onCreated(row.id);
  }
  async function selectPublished(row: MasterRow) {
    if (verifying.current || !master) return;
    verifying.current = true;
    setState({ dirty: false, busy: true });
    setProblem('');
    try {
      const query = new URLSearchParams({ value: row.id, kind, limit: '1' });
      const page = await masterRequest<ServicePage<CatalogComponents['schemas']['ConfigurationOptionItem']>>({
        path: catalogBase(company, 'product-configuration/options/product-type-revisions') + '?' + query,
        signal: AbortSignal.timeout(30_000),
      });
      if (!catalogId.test(row.id) || !row.published_at || row.product_type_id !== master.id || !Array.isArray(page.items) || page.items.length !== 1 || page.items[0].value !== row.id || page.items[0].parent_id !== master.id || !page.items[0].label) {
        throw { status: 502, message: 'The type was published, but its availability for this product could not be verified. Retry selection; the created records are preserved.' };
      }
      onCreated(row.id);
    } catch (error) {
      setProblem(requestFailure(error, 'product type selection').message);
    } finally {
      verifying.current = false;
      setState({ dirty: false, busy: false });
    }
  }
  function savedRevision(row: MasterRow) {
    setState({ dirty: false, busy: false });
    setRevision(row);
    if (row.published_at) void selectPublished(row);
  }
  return <>
    <Drawer open title={group ? 'New product group' : 'New product type'} size="lg" busy={state.busy} onClose={close}>
      <div className="console-reference-create-drawer janso-flow" onSubmit={event => event.stopPropagation()} onKeyDown={event => { if (event.key === 'Enter') event.stopPropagation(); }}>
        <p className="janso-fine">Your product draft stays on this page. {group ? 'Save this group to select it for the product.' : 'Create the type, save its requirements and review publication before selecting it.'}</p>
        {problem && <Notice tone="danger">{problem}</Notice>}
        <Suspense fallback={<p role="status">Loading create form…</p>}>
          {!master ? group
            ? <GroupEditor company={company} config={masterConfig('item-groups')!} embedded={{ initialValues: { allowed_kind: ['GOODS', 'SERVICE'].includes(kind) ? kind : 'BOTH' }, onSaved: savedMaster, onCancel: close, onStateChange: setState }} />
            : <TypeEditor company={company} config={masterConfig('product-types')!} access={access} embedded={{ initialValues: { kind: ['GOODS', 'SERVICE'].includes(kind) ? kind : 'BOTH' }, onSaved: savedMaster, onCancel: close, onStateChange: setState }} />
            : group ? <Button onClick={close}>Close</Button>
              : revision?.published_at ? <>
                <Notice tone="success">Product type requirements published. The created type and revision have been preserved.</Notice>
                <Button loading={state.busy} onClick={() => void selectPublished(revision)}>Retry selection</Button>
                <Button variant="ghost" disabled={state.busy} onClick={close}>Close</Button>
              </> : <>
                {revision && !access.publish && <Notice>The requirements are saved as a draft. A permitted publisher must publish them before this type can be selected. Your product selection is unchanged.</Notice>}
                <RequirementsEditor key={revision?.id ?? 'new'} company={company} parentId={master.id} id={revision?.id} canManage={!!access.manageTypes} access={access} embedded={{ onSaved: savedRevision, onCancel: close, onStateChange: setState }} />
              </>}
        </Suspense>
      </div>
    </Drawer>
    <ConfirmDialog open={discard} title="Discard new master changes?" confirmLabel="Discard changes" onCancel={() => setDiscard(false)} onConfirm={onClose}>
      Unsaved changes in this panel will be discarded. Your product draft and any masters already saved are preserved.
    </ConfirmDialog>
  </>;
}

/** Remount only the lookup after creation; product fields and draft stay mounted. */
export function ProductReferenceCreate({ company, source, kind, access, disabled, onCreated, children }: {
  company: string; source: string; kind?: string; access: ClassificationAccess; disabled: boolean;
  onCreated: (id: string) => void; children: ReactNode;
}) {
  const [open, setOpen] = useState(false), [refresh, setRefresh] = useState(0);
  const permitted = source === 'item-groups' ? access.groups && access.manageGroups
    : source === 'product-type-revisions' && access['product-types'] && access.configuration && access.manageTypes;
  const close = useCallback(() => setOpen(false), []);
  if (!permitted || !['item-groups', 'product-type-revisions'].includes(source)) return <>{children}</>;
  return <>
    <div className="console-reference-create">
      <div className="console-reference-create__field" key={refresh}>{children}</div>
      <IconButton className="console-reference-create__action" variant="outline" label={source === 'item-groups' ? 'New product group' : 'New product type'} icon={<PlusIcon size={16} />} aria-haspopup="dialog" disabled={disabled} onClick={() => setOpen(true)} />
    </div>
    {open && <ReferenceCreateDrawer key={company + ':' + source} company={company} resource={source as Resource} kind={kind ?? 'GOODS'} access={access} onClose={close} onCreated={id => {
      onCreated(id); setRefresh(value => value + 1); setOpen(false);
    }} />}
  </>;
}
