'use client';
import { useCallback, useRef, useState } from 'react';
import { Button, Card, CardBody, FormActions, FormLayout, Notice, PageHeader, PageNavigation, SectionHeader, CustomFields, CustomFieldEditor, customPatch, Select, SearchSelect, type CustomField, type CustomDefinition, type DefinitionDraft } from '@janso/ui';
import { productFieldRequest as request, ProductFieldError } from '../lib/product-fields';
import { inventoryBreadcrumbs } from '../lib/inventory-navigation';
import { masterReturn } from '../lib/master-navigation';
import { useUnsavedChanges } from '../lib/use-unsaved-changes';
type Page<T> = { items: T[]; page: { next_cursor: string | null; has_more: boolean } };
type DefinitionItem = DefinitionDraft & { id: string; digest: string; company_id: string | null; entity_type: string; display_order?: number; display_group?: string | null; placeholder?: string | null; requires_feature?: string | null };
type Preview = { source_definition_digests: Record<string,string>; eligible: boolean; owner_count: number; preview_token: string; definitions: CustomDefinition[]; issues: {owner_id:string;field_key:string;reason:string}[] };
type Product = { id:string; name?:string; row_version:number; custom_fields?:Record<string,unknown>; [key:string]:unknown };
export function ProductFields({ company, currencies, canManage, returnTo }: {company:string;currencies:string[];canManage:boolean;returnTo?:string}) {
  const [entity,setEntity] = useState('catalog.item');
  const [fields,setFields] = useState<CustomField[]>([]), [definitions,setDefinitions] = useState<DefinitionItem[]>([]);
  const [sources,setSources] = useState<string[]>([]), [owner,setOwner] = useState<Product | null>(null);
  const [values,setValues] = useState<Record<string,unknown>>({}), [editor,setEditor] = useState<DefinitionItem | 'new' | null>(null);
  const [preview,setPreview] = useState<Preview | null>(null), [busy,setBusy] = useState(false), [message,setMessage] = useState('');
  const [errors,setErrors] = useState<Record<string,string>>({}), [loaded,setLoaded] = useState(false);
  const [scope,setScope] = useState('company');
  const dirty = !!editor || !!owner && Object.keys(customPatch(fields, values, owner.custom_fields ?? {})).length > 0;
  useUnsavedChanges(() => busy || dirty);
  const retry = useRef<{payload:string;key:string}|null>(null);
  const base = '/v1/companies/'+company, entityRoot = base+'/entities/'+entity;
  const products = base+(entity === 'catalog.item' ? '/items':'/product-families');
  async function action(run: () => Promise<void>) { setBusy(true);setMessage('');setErrors({});try { await run(); } catch(error) {
    setMessage(error instanceof Error ? error.message : 'Unable to complete this action'); if(error instanceof ProductFieldError) setErrors(error.fields);
  } finally {setBusy(false);} }
  function receipt(payload: unknown) { const encoded=JSON.stringify(payload); if(retry.current?.payload !== encoded) retry.current={payload:encoded,key:crypto.randomUUID()}; return retry.current!.key; }
  async function refresh() {
    const data = await request<{fields:CustomField[]}>('catalog','GET',entityRoot+'/field-set?operation=update'+(owner ? '&object_id='+owner.id:'')); setFields(data.fields);
    if(canManage) {
      const contract = await request<{option_sources:Record<string,unknown>}>('identity','GET','/v1/entities/'+entity+'/custom-field-contract?company_id='+company); setSources(Object.keys(contract.option_sources));
      setDefinitions(await loadDefinitions());
    }
    setLoaded(true);
  }
  async function loadDefinitions(): Promise<DefinitionItem[]> {
      const rows: DefinitionItem[] = []; let cursor: string | null=null;
      do {
        const page: Page<DefinitionItem> = await request('identity','GET','/v1/custom-field-definitions?entity_type='+entity+'&company_id='+company+'&limit=200'+(cursor ? '&cursor='+encodeURIComponent(cursor):''));
        rows.push(...page.items); cursor=page.page.next_cursor;
        if(rows.length > 256) throw new Error('Too many product definitions');
      } while(cursor);
      return rows;
  }
  async function review() {
    setPreview(null);
    const rows=await loadDefinitions();setDefinitions(rows);
    const result=await request<Preview>('catalog','POST',entityRoot+'/custom-field-adoption/preview');
    if(rows.length !== Object.keys(result.source_definition_digests).length || rows.some(row => result.source_definition_digests[row.id] !== row.digest)) throw new Error('Definitions are still synchronizing. Reload and review again.');
    setPreview(result);
  }
  const lookup = useCallback(async ({q,cursor,signal}:{q:string;cursor:string|null;signal:AbortSignal}) => {
    const page = await request<Page<{id:string;name?:string;sku?:string;code?:string}>>('catalog','GET',products+'?q='+encodeURIComponent(q)+(cursor ? '&cursor='+encodeURIComponent(cursor):''),undefined,undefined,signal);
    return {items:page.items.map(row => ({id:row.id,label:row.name ?? row.sku ?? row.code ?? row.id})),nextCursor:page.page.next_cursor};
  },[products]);
  async function selectOwner(id:string|null) { setOwner(null);setValues({});setPreview(null); if(!id) return;
    await action(async () => { const [product,metadata]=await Promise.all([request<Product>('catalog','GET',products+'/'+id),request<{fields:CustomField[]}>('catalog','GET',entityRoot+'/field-set?operation=update&object_id='+id)]);
      setOwner(product);setValues(product.custom_fields ?? {});setFields(metadata.fields); }); }
  return <section className="janso-page" aria-label="Product custom fields"><PageNavigation back={{ href: masterReturn(returnTo, '/inventory/products'), label: 'previous page' }} breadcrumbs={inventoryBreadcrumbs('products', 'Product fields')} onNavigate={event => { if (busy) event.preventDefault(); }} /><PageHeader title="Product fields" lede="Family values describe the product family. SKU values belong to each individual item." />
    <FormLayout aside={<><SectionHeader title="Fields and saved values" /><p className="janso-fine">Select a field owner, load its available fields, then choose the product whose values you want to edit.</p><p className="janso-fine">Definition changes are candidates until reviewed and adopted. Changing a definition does not silently rewrite existing product values.</p></>}><div className="janso-flow">
    <Card><CardBody><div className="janso-flow"><SectionHeader title="Choose a product" />
    <Select label="Field owner" value={entity} disabled={busy} options={[{value:'catalog.item',label:'SKU / item'},{value:'catalog.product_family',label:'Product family'}]}
      onChange={v => {setEntity(v);setLoaded(false);setOwner(null);setValues({});setFields([]);setDefinitions([]);setPreview(null);setEditor(null);setMessage('');}} />
    </div></CardBody><FormActions><Button loading={busy} onClick={() => void action(refresh)}>Load fields</Button></FormActions></Card>
    {message && <Notice>{message}</Notice>}
    {loaded && <><Card><CardBody><SearchSelect label="Find a product" value={owner?.id ?? null} selected={owner ? {id:owner.id,label:String(owner.name ?? owner.id)}:null} loadOptions={lookup}
      disabled={busy} onChange={id => void selectOwner(id)} /></CardBody></Card>
      {owner && <form aria-label="Product custom values" onSubmit={event => {event.preventDefault();void action(async () => {
        const body={expected_version:owner.row_version,custom_fields:customPatch(fields,values,owner.custom_fields ?? {})};
        if(!Object.keys(body.custom_fields).length) {setMessage('No values changed.');return;}
        const result=await request<Product>('catalog','PATCH',products+'/'+owner.id,body,receipt({route:products+'/'+owner.id,body}));
        setOwner(result);setValues(result.custom_fields ?? {});retry.current=null;setPreview(null);setMessage('Product custom values saved.');
      });}}><Card><CardBody><div className="janso-flow"><SectionHeader title="Product values" description={owner.name ?? 'Selected product'} /><CustomFields fields={fields} values={values} nativeValues={owner} currencies={currencies} disabled={busy} errors={errors} onChange={setValues}
        loadOptions={(source,parent) => async ({q,cursor,signal}) => {
          const page=await request<Page<{value:string;label:string}>>('catalog','GET',base+'/option-sources/'+source+'?q='+encodeURIComponent(q)+(parent ? '&parent_id='+encodeURIComponent(parent):'')+(cursor ? '&cursor='+encodeURIComponent(cursor):''),undefined,undefined,signal);
          return {items:page.items.map(row => ({id:row.value,label:row.label})),nextCursor:page.page.next_cursor};
        }} /></div></CardBody><FormActions><Button type="submit" loading={busy}>Save product values</Button></FormActions></Card></form>}
      {canManage && <section className="janso-flow" aria-label="Manage definitions"><SectionHeader title="Manage definitions" description="Create or edit a candidate, then review its impact before adoption." /><Card><CardBody><div className="janso-flow">
        <Select label="New definition scope" value={scope} options={[{value:'company',label:'This company'},{value:'tenant',label:'All companies'}]} disabled={busy || !!editor} onChange={setScope} />
        <ul className="janso-flow">{definitions.map(row => <li key={row.id}>{row.label} <Button variant="ghost" disabled={busy} onClick={() => void action(async () => setEditor(await request<DefinitionItem>('identity','GET','/v1/custom-field-definitions/'+row.id)))}>Edit</Button></li>)}</ul>
        </div></CardBody><FormActions><Button disabled={busy} onClick={() => setEditor('new')}>Add field</Button><Button variant="ghost" disabled={busy} onClick={() => void action(review)}>Review pending changes</Button></FormActions></Card>
        {editor && <CustomFieldEditor key={editor === 'new' ? 'new':editor.id} initial={editor === 'new' ? undefined:editor} sources={sources} fields={fields.map(f => ({key:f.key,label:f.label}))} currencies={currencies} busy={busy}
          onCancel={() => setEditor(null)} onSave={async draft => {setBusy(true);try {
            const prior=editor === 'new' ? null:editor;
            await request('identity',prior ? 'PUT':'POST','/v1/custom-field-definitions'+(prior ? '/'+prior.id:''),{
              ...draft,entity_type:entity,company_id:prior ? prior.company_id : scope === 'company' ? company:null,
              expected_digest:prior?.digest,display_order:prior?.display_order ?? 0,display_group:prior?.display_group ?? null,
              placeholder:prior?.placeholder ?? null,requires_feature:prior?.requires_feature ?? null,
            });
            setEditor(null);setPreview(null);setMessage('Candidate saved. Reload fields after synchronization, then review adoption.');await refresh();
          } finally {setBusy(false);} }} />}
        {preview && <section aria-label="Adoption review"><Card><CardBody><div className="janso-flow"><SectionHeader title="Adoption review" /><p>{preview.owner_count} existing products checked.</p>
          <ul>{preview.definitions.map(d => <li key={d.key}>{d.key}: {d.data_type}{d.validation.required ? ', required':''}{d.is_searchable ? ', searchable':''}</li>)}</ul>
          {preview.issues.length > 0 && <ul>{preview.issues.map((issue,index) => <li key={index}>{issue.owner_id}: {issue.field_key}: {issue.reason}</li>)}</ul>}
          </div></CardBody><FormActions><Button disabled={busy || !preview.eligible} onClick={() => void action(async () => {
            const body={preview_token:preview.preview_token};await request('catalog','POST',entityRoot+'/custom-field-adoption',body,receipt({entity,body}));
            retry.current=null;setPreview(null);setOwner(null);setValues({});await refresh();setMessage('Reviewed definitions adopted.');
          })}>Adopt reviewed definitions</Button></FormActions></Card>
        </section>}
      </section>}
    </>}
  </div></FormLayout></section>;
}
