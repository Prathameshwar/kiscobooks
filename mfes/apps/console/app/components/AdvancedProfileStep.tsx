'use client';
import { useEffect, useId, useState } from 'react';
import { FieldLabel, Notice, Select, TextField } from '@janso/ui';
import type { components } from '@janso/api-client/catalog';
import { masterRequest } from '../lib/catalog-master-api';
import { requestFailure } from '../lib/service-call';
import { advancedFieldLabel } from '../lib/advanced-product-presentation';
import { clearUnavailableProfile, unavailableProfileFields } from '../lib/advanced-product-compatibility';
import type { AdvancedOptions, ProductProfileValues } from '../lib/advanced-product-draft';
import { AdvancedProductChoice } from './AdvancedProductChoice';
import { ProductCatalogCustomFields } from './ProductCatalogCustomFields';

type Revision = { id: string; revision?: number; status?: string; is_published?: boolean; product_type_id?: string };
type Page = { items: Revision[]; page: { has_more: boolean; next_cursor?: string | null } };
export function AdvancedProfileStep({ company, value, options, onChange, errors, disabled, definitionLocked = false, setupLocked = false, refreshing = false }: { company: string; value: ProductProfileValues; options: AdvancedOptions; onChange: (value: ProductProfileValues) => void; errors: Record<string, string>; disabled: boolean; definitionLocked?: boolean; setupLocked?: boolean; refreshing?: boolean }) {
  const descriptionId = useId();
  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [revisionFailure, setRevisionFailure] = useState('');
  const [revisionLoading, setRevisionLoading] = useState(false);
  const field = (key: string) => options.family_fields.fields.find(row => row.key === key);
  const modes = options.defaults.configuration.options;
  const shown = (key: string) => field(key)?.visible === true && (key !== 'brand_id' && key !== 'series_id' || modes.brand_mode !== 'DISABLED' || !!value.brand_id || !!value.series_id) && (key !== 'model_code' || modes.model_mode !== 'DISABLED' || !!value.model_code);
  const blocked = (key: string) => disabled || refreshing || definitionLocked || !field(key)?.writable || !!field(key)?.conditional_access || (['brand_id', 'series_id'].includes(key) && modes.brand_mode === 'DISABLED') || (key === 'model_code' && modes.model_mode === 'DISABLED');
  const change = (key: keyof ProductProfileValues, next: string) => onChange({ ...value, [key]: next });
  useEffect(() => {
    if (!value.product_type_id) { setRevisions([]); setRevisionLoading(false); setRevisionFailure(''); return; }
    const controller = new AbortController();
    setRevisionFailure(''); setRevisions([]); setRevisionLoading(true);
    masterRequest<Page>({ path: `/v1/companies/${company}/product-types/${value.product_type_id}/revisions?limit=200&sort=-revision&published=true`, signal: controller.signal }).then(page => {
      if (controller.signal.aborted) return;
      setRevisionLoading(false); setRevisions(page.items.filter(row => !row.product_type_id || row.product_type_id === value.product_type_id));
    }).catch(error => { if (!controller.signal.aborted) { setRevisionLoading(false); setRevisionFailure(requestFailure(error).message); } });
    return () => controller.abort();
  }, [company, value.product_type_id]);
  return <div className="product-wizard__sections">
    {!definitionLocked && unavailableProfileFields(value, options).length > 0 && <Notice tone="warning" action={<button type="button" className="janso-btn janso-btn--secondary" disabled={disabled || refreshing || setupLocked} onClick={() => onChange(clearUnavailableProfile(value, options))}>Remove unavailable Profile details</button>}>Some saved Profile details are no longer allowed by this product kind or configuration. Review them and remove them to continue.</Notice>}
    <section className="product-wizard__section" aria-labelledby="profile-core"><h3 id="profile-core">Identity</h3><p>Details shared by every SKU.</p>
      <div className="product-wizard__fields">
        <Select label="Product kind" value={value.kind} required disabled={disabled || definitionLocked} options={[{ value: "GOODS", label: "Goods" }, { value: "SERVICE", label: "Service" }]} onChange={kind => onChange({ ...value, kind: kind as ProductProfileValues['kind'], product_type_id: '', product_type_revision_id: '' })} />
        {shown('name') && <TextField label={advancedFieldLabel(field('name'), 'Profile name')} value={value.name} required error={errors.name} disabled={blocked('name')} maxLength={100} onChange={event => change('name', event.target.value)} />}
        {shown('code') && <TextField label={advancedFieldLabel(field('code'), 'Profile code')} value={value.code} required error={errors.code} disabled={blocked('code')} maxLength={30} onChange={event => change('code', event.target.value.toUpperCase())} />}
        <AdvancedProductChoice company={company} resource="product-types" kind={value.kind} label="Product Type" value={value.product_type_id} disabled={disabled || definitionLocked} onChange={id => { onChange({ ...value, product_type_id: id, product_type_revision_id: '' }); }} />
        <Select label="Published Type revision" loading={revisionLoading} loadingLabel="Loading published revisions…" required value={value.product_type_revision_id} disabled={disabled || definitionLocked || (!value.product_type_id && !value.product_type_revision_id)} placeholder="Choose a published revision" error={errors.product_type_revision_id} options={[...(!value.product_type_id && value.product_type_revision_id ? [{ value: value.product_type_revision_id, label: 'Company default revision' }] : []), ...revisions.map(row => ({ value: row.id, label: `Revision ${row.revision ?? 'published'}` }))]} onChange={revision => change('product_type_revision_id', revision)} />
        <AdvancedProductChoice company={company} resource="item_groups" label="Product group" value={value.group_id} required disabled={disabled || definitionLocked} error={errors.group_id} onChange={id => { change('group_id', id); }} />
      </div>{revisionFailure && <Notice tone="warning">Published Type revisions could not be loaded. {revisionFailure}</Notice>}
    </section>
    {(shown('brand_id') || shown('model_code') || shown('description')) && <section className="product-wizard__section" aria-labelledby="profile-detail"><h3 id="profile-detail">Details and classification</h3><div className="product-wizard__fields">
      {shown('brand_id') && <AdvancedProductChoice company={company} resource="brands" label={advancedFieldLabel(field('brand_id'), 'Brand')} value={value.brand_id} required={field('brand_id')?.required || options.selected_type?.require_brand || modes.brand_mode === 'REQUIRED'} disabled={blocked('brand_id')} error={errors.brand_id} onChange={id => { onChange({ ...value, brand_id: id, series_id: '' }); }} />}
      {shown('series_id') && value.brand_id && <AdvancedProductChoice company={company} resource="brand_series" label={advancedFieldLabel(field('series_id'), 'Series')} parent={value.brand_id} value={value.series_id} disabled={blocked('series_id')} error={errors.series_id} onChange={id => { change('series_id', id); }} />}
      {shown('model_code') && <TextField label={advancedFieldLabel(field('model_code'), 'Model code')} value={value.model_code} required={field('model_code')?.required || modes.model_mode === 'REQUIRED'} disabled={blocked('model_code')} error={errors.model_code} onChange={event => change('model_code', event.target.value)} />}
      {shown('description') && <div className="janso-field janso-form-grid__full"><div className="janso-field__row"><FieldLabel htmlFor={descriptionId}>{advancedFieldLabel(field('description'), 'Description')}</FieldLabel></div><textarea id={descriptionId} className="janso-input" rows={3} value={value.description} disabled={blocked('description')} aria-invalid={!!errors.description} aria-describedby={errors.description ? descriptionId + '-error' : undefined} onChange={event => change('description', event.target.value)} />{errors.description && <p id={descriptionId + '-error'} className="janso-error" role="alert">{errors.description}</p>}</div>}
    </div></section>}
    {options.defaults.configuration.options.category_mode !== 'DISABLED' && <section className="product-wizard__section" aria-labelledby="profile-categories"><h3 id="profile-categories">Categories</h3><p>Choose the classifications that apply to this Profile.</p>
      {(options.required_category_schemes ?? []).map(scheme => {
        const row = value.categories.find(entry => entry.scheme_id === scheme.id);
        return <AdvancedProductChoice key={scheme.id} company={company} resource="item_categories" parent={scheme.id} label={scheme.name} value={row?.category_id ?? ''} required disabled={disabled || refreshing || setupLocked} error={errors['categories.' + scheme.id]} onChange={id => { const without = value.categories.filter(entry => entry.scheme_id !== scheme.id); onChange({ ...value, categories: [...without, { key: row?.key ?? crypto.randomUUID(), scheme_id: scheme.id, category_id: id, is_primary: true }] }); }} />;
      })}
      {value.categories.filter(row => !(options.required_category_schemes ?? []).some(scheme => scheme.id === row.scheme_id)).map(row => <div className="product-wizard__category" key={row.key}><AdvancedProductChoice company={company} resource="category_schemes" label="Category scheme" value={row.scheme_id} disabled={disabled || refreshing || setupLocked} onChange={id => onChange({ ...value, categories: value.categories.map(entry => entry.key === row.key ? { ...entry, scheme_id: id, category_id: '' } : entry) })} /><AdvancedProductChoice company={company} resource="item_categories" parent={row.scheme_id} label="Category" value={row.category_id} disabled={disabled || setupLocked || !row.scheme_id} error={errors['categories.' + row.key]} onChange={id => onChange({ ...value, categories: value.categories.map(entry => entry.key === row.key ? { ...entry, category_id: id } : entry) })} /><button type="button" className="janso-link" disabled={disabled || refreshing || setupLocked} onClick={() => onChange({ ...value, categories: value.categories.filter(entry => entry.key !== row.key) })}>Remove category</button></div>)}
      <button type="button" className="janso-btn janso-btn--secondary" disabled={disabled || setupLocked || value.categories.length >= 128} onClick={() => onChange({ ...value, categories: [...value.categories, { key: crypto.randomUUID(), scheme_id: '', category_id: '', is_primary: false }] })}>Add category</button>
    </section>}
    {value.kind === 'GOODS' && options.defaults.configuration.options.manufacturer_mode !== 'DISABLED' && <section className="product-wizard__section" aria-labelledby="profile-manufacturer"><h3 id="profile-manufacturer">Manufacturer</h3><p>Identify who makes this product, when applicable.</p><div className="product-wizard__fields"><AdvancedProductChoice company={company} resource="manufacturers" label="Manufacturer" value={value.manufacturer_id} required={options.selected_type?.require_manufacturer || options.defaults.configuration.options.manufacturer_mode === 'REQUIRED'} disabled={disabled || refreshing || setupLocked} error={errors.manufacturer_id} onChange={id => { onChange({ ...value, manufacturer_id: id, manufacturer_site_id: '' }); }} />{value.manufacturer_id && <AdvancedProductChoice company={company} resource="manufacturer_sites" parent={value.manufacturer_id} label="Manufacturer site" value={value.manufacturer_site_id} disabled={disabled || refreshing || setupLocked} error={errors.manufacturer_site_id} onChange={id => { change('manufacturer_site_id', id); }} />}</div></section>}
    <ProductCatalogCustomFields company={company} fields={options.family_fields.fields as components['schemas']['FieldMetadata'][]} values={{ ...value, custom_fields: value.custom_fields }} creating disabled={disabled || refreshing || definitionLocked} errors={errors} onChange={custom_fields => onChange({ ...value, custom_fields })} />
  </div>;
}
