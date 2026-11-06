'use client';
import { useEffect, useState } from 'react';
import { Notice, TextField } from '@janso/ui';
import type { components } from '@janso/api-client/catalog';
import { masterRequest } from '../lib/catalog-master-api';
import { requestFailure } from '../lib/service-call';
import type { AdvancedOptions, ProductProfileValues } from '../lib/advanced-product-draft';
import { AdvancedProductChoice } from './AdvancedProductChoice';
import { ProductCatalogCustomFields } from './ProductCatalogCustomFields';

type Revision = { id: string; revision?: number; status?: string; is_published?: boolean; product_type_id?: string };
type Page = { items: Revision[]; page: { has_more: boolean; next_cursor?: string | null } };
export function AdvancedProfileStep({ company, value, options, onChange, errors, disabled, definitionLocked = false, setupLocked = false }: { company: string; value: ProductProfileValues; options: AdvancedOptions; onChange: (value: ProductProfileValues) => void; errors: Record<string, string>; disabled: boolean; definitionLocked?: boolean; setupLocked?: boolean }) {
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [revisionFailure, setRevisionFailure] = useState('');
  const field = (key: string) => options.family_fields.fields.find(row => row.key === key);
  const shown = (key: string) => field(key)?.visible === true;
  const blocked = (key: string) => disabled || definitionLocked || !field(key)?.writable || !!field(key)?.conditional_access;
  const change = (key: keyof ProductProfileValues, next: string) => onChange({ ...value, [key]: next });
  useEffect(() => {
    if (!value.product_type_id) { setRevisions([]); return; }
    const controller = new AbortController();
    setRevisionFailure('');
    masterRequest<Page>({ path: `/v1/companies/${company}/product-types/${value.product_type_id}/revisions?limit=200&sort=-revision&published=true`, signal: controller.signal }).then(page => {
      if (controller.signal.aborted) return;
      setRevisions(page.items.filter(row => !row.product_type_id || row.product_type_id === value.product_type_id));
    }).catch(error => { if (!controller.signal.aborted) setRevisionFailure(requestFailure(error).message); });
    return () => controller.abort();
  }, [company, value.product_type_id]);
  return <div className="product-wizard__sections">
    <section className="product-wizard__section" aria-labelledby="profile-core"><h3 id="profile-core">Identity</h3><p>Details shared by every SKU.</p>
      <div className="product-wizard__fields">
        <label className="product-wizard__field">Product kind <span aria-hidden="true">*</span><select aria-label="Product kind" value={value.kind} disabled={disabled || definitionLocked} onChange={event => onChange({ ...value, kind: event.target.value as ProductProfileValues['kind'], product_type_id: '', product_type_revision_id: '', brand_id: '', series_id: '' })}><option value="GOODS">Goods</option><option value="SERVICE">Service</option></select></label>
        {shown('name') && <TextField label={field('name')?.label ?? 'Profile name'} value={value.name} required error={errors.name} disabled={blocked('name')} maxLength={100} onChange={event => change('name', event.target.value)} />}
        {shown('code') && <TextField label={field('code')?.label ?? 'Profile code'} value={value.code} error={errors.code} disabled={blocked('code')} maxLength={30} onChange={event => change('code', event.target.value.toUpperCase())} />}
        <AdvancedProductChoice company={company} resource="product-types" kind={value.kind} label="Change Product Type" value={value.product_type_id} selected={labels.product_type_id} disabled={disabled || definitionLocked} onChange={(id, label) => { setLabels(previous => ({ ...previous, product_type_id: label })); onChange({ ...value, product_type_id: id, product_type_revision_id: '' }); }} />
        <label className="product-wizard__field">Published Type revision <span aria-hidden="true">*</span><select aria-label="Published Type revision" aria-invalid={!!errors.product_type_revision_id} value={value.product_type_revision_id} disabled={disabled || definitionLocked || (!value.product_type_id && !value.product_type_revision_id)} onChange={event => change('product_type_revision_id', event.target.value)}><option value="">Choose a published revision</option>{!value.product_type_id && value.product_type_revision_id && <option value={value.product_type_revision_id}>Company default revision</option>}{revisions.map(row => <option key={row.id} value={row.id}>Revision {row.revision ?? row.id.slice(0, 8)}</option>)}</select>{errors.product_type_revision_id && <span role="alert">{errors.product_type_revision_id}</span>}</label>
        <AdvancedProductChoice company={company} resource="item_groups" label="Product group" value={value.group_id} selected={labels.group_id} required disabled={disabled || definitionLocked} error={errors.group_id} onChange={(id, label) => { setLabels(previous => ({ ...previous, group_id: label })); change('group_id', id); }} />
      </div>{revisionFailure && <Notice tone="warning">Published Type revisions could not be loaded. {revisionFailure}</Notice>}
    </section>
    {(shown('brand_id') || shown('model_code') || shown('description')) && <section className="product-wizard__section" aria-labelledby="profile-detail"><h3 id="profile-detail">Details and classification</h3><div className="product-wizard__fields">
      {shown('brand_id') && <AdvancedProductChoice company={company} resource="brands" label={field('brand_id')?.label ?? 'Brand'} value={value.brand_id} selected={labels.brand_id} required={field('brand_id')?.required || options.selected_type?.require_brand} disabled={blocked('brand_id')} error={errors.brand_id} onChange={(id, label) => { setLabels(previous => ({ ...previous, brand_id: label })); onChange({ ...value, brand_id: id, series_id: '' }); }} />}
      {shown('series_id') && value.brand_id && <AdvancedProductChoice company={company} resource="brand_series" label={field('series_id')?.label ?? 'Series'} parent={value.brand_id} value={value.series_id} selected={labels.series_id} disabled={blocked('series_id')} error={errors.series_id} onChange={(id, label) => { setLabels(previous => ({ ...previous, series_id: label })); change('series_id', id); }} />}
      {shown('model_code') && <TextField label={field('model_code')?.label ?? 'Model code'} value={value.model_code} disabled={blocked('model_code')} error={errors.model_code} onChange={event => change('model_code', event.target.value)} />}
      {shown('description') && <TextField label={field('description')?.label ?? 'Description'} value={value.description} disabled={blocked('description')} error={errors.description} onChange={event => change('description', event.target.value)} />}
    </div></section>}
    {options.defaults.configuration.options.category_mode !== 'DISABLED' && <section className="product-wizard__section" aria-labelledby="profile-categories"><h3 id="profile-categories">Categories</h3><p>Choose the classifications that apply to this Profile.</p>
      {(options.required_category_schemes ?? []).map(scheme => {
        const row = value.categories.find(entry => entry.scheme_id === scheme.id);
        return <AdvancedProductChoice key={scheme.id} company={company} resource="item_categories" parent={scheme.id} label={scheme.name} value={row?.category_id ?? ''} required disabled={disabled || setupLocked} error={errors['categories.' + scheme.id]} onChange={id => { const without = value.categories.filter(entry => entry.scheme_id !== scheme.id); onChange({ ...value, categories: [...without, { key: row?.key ?? crypto.randomUUID(), scheme_id: scheme.id, category_id: id, is_primary: true }] }); }} />;
      })}
      {value.categories.filter(row => !(options.required_category_schemes ?? []).some(scheme => scheme.id === row.scheme_id)).map(row => <div className="product-wizard__category" key={row.key}><AdvancedProductChoice company={company} resource="category_schemes" label="Category scheme" value={row.scheme_id} disabled={disabled || setupLocked} onChange={id => onChange({ ...value, categories: value.categories.map(entry => entry.key === row.key ? { ...entry, scheme_id: id, category_id: '' } : entry) })} /><AdvancedProductChoice company={company} resource="item_categories" parent={row.scheme_id} label="Category" value={row.category_id} disabled={disabled || setupLocked || !row.scheme_id} error={errors['categories.' + row.key]} onChange={id => onChange({ ...value, categories: value.categories.map(entry => entry.key === row.key ? { ...entry, category_id: id } : entry) })} /><button type="button" className="janso-link" disabled={disabled || setupLocked} onClick={() => onChange({ ...value, categories: value.categories.filter(entry => entry.key !== row.key) })}>Remove category</button></div>)}
      <button type="button" className="janso-btn janso-btn--secondary" disabled={disabled || setupLocked || value.categories.length >= 128} onClick={() => onChange({ ...value, categories: [...value.categories, { key: crypto.randomUUID(), scheme_id: '', category_id: '', is_primary: false }] })}>Add category</button>
    </section>}
    {value.kind === 'GOODS' && options.defaults.configuration.options.manufacturer_mode !== 'DISABLED' && <section className="product-wizard__section" aria-labelledby="profile-manufacturer"><h3 id="profile-manufacturer">Manufacturer</h3><p>Identify who makes this product, when applicable.</p><div className="product-wizard__fields"><AdvancedProductChoice company={company} resource="manufacturers" label="Manufacturer" value={value.manufacturer_id} selected={labels.manufacturer_id} required={options.selected_type?.require_manufacturer || options.defaults.configuration.options.manufacturer_mode === 'REQUIRED'} disabled={disabled || setupLocked} error={errors.manufacturer_id} onChange={(id, label) => { setLabels(previous => ({ ...previous, manufacturer_id: label })); onChange({ ...value, manufacturer_id: id, manufacturer_site_id: '' }); }} />{value.manufacturer_id && <AdvancedProductChoice company={company} resource="manufacturer_sites" parent={value.manufacturer_id} label="Manufacturer site" value={value.manufacturer_site_id} selected={labels.manufacturer_site_id} disabled={disabled || setupLocked} error={errors.manufacturer_site_id} onChange={(id, label) => { setLabels(previous => ({ ...previous, manufacturer_site_id: label })); change('manufacturer_site_id', id); }} />}</div></section>}
    <ProductCatalogCustomFields company={company} fields={options.family_fields.fields as components['schemas']['FieldMetadata'][]} values={{ ...value, custom_fields: value.custom_fields }} creating disabled={disabled || definitionLocked} errors={errors} onChange={custom_fields => onChange({ ...value, custom_fields })} />
  </div>;
}
