'use client';
import { useId, type ReactNode } from 'react';
import { Badge, PageHeader, useFormatters } from '@janso/ui';
import type { MasterField } from '../lib/catalog-masters';
import type { ClassificationAccess } from '../lib/product-classification-resources';
import { ProductCatalogField } from './ProductCatalogCommon';
import { ProductCatalogCustomFields } from './ProductCatalogCustomFields';

type Row = Record<string, unknown>;
const internal = new Set(['id', 'company_id', 'custom_fields', 'shared_custom_fields', 'revision']);
const trading = new Set(['sellable', 'purchasable', 'min_sale_quantity', 'sale_unit_id', 'purchase_unit_id']);
const recordInfo = new Set(['status', 'is_active', 'row_version', 'authoring_version', 'policy_generation', 'created_at', 'updated_at']);
const readable = (fields: readonly MasterField[], row: Row) => fields.filter(field => field.visible && field.source === 'native' && field.key in row && !internal.has(field.key) && (!field.key.endsWith('_id') || field.control?.kind === 'reference'));
const words = (value: string) => value.replaceAll('_', ' ').toLowerCase().replace(/^./, letter => letter.toUpperCase());
const label = (field: MasterField) => field.control?.label || words(field.label || field.key);

export function ProductDetailHeader({ title, fields, row, family = false, actions, completed = false }: {
  title: string; fields: readonly MasterField[]; row?: Row | null; family?: boolean; actions?: ReactNode; completed?: boolean; lede?: ReactNode;
}) {
  const visible = new Set(fields.filter(field => field.visible && field.source === 'native').map(field => field.key));
  const code = visible.has('sku') ? row?.sku : visible.has('code') ? row?.code : null;
  const status = visible.has('status') && typeof row?.status === 'string' ? row.status : visible.has('is_active') && typeof row?.is_active === 'boolean' ? row.is_active ? 'ACTIVE' : 'INACTIVE' : null;
  return <div className="janso-product-detail__hero">
    <div className="janso-product-detail__mark" aria-hidden="true"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"><path d="M24 5 41 15v19L24 44 7 34V15L24 5Z" /><path d="m7 15 17 10 17-10M24 25v19M15 10l18 10v10" /></svg></div>
    <PageHeader overline={family ? 'Product profile' : 'Product details'} title={title}
      lede={completed ? 'Your product is saved. Review its details and continue with the next step.' : family ? 'Shared identity and specifications for the products in this profile.' : 'Identity, specifications and trading details in one place.'}
      meta={<>{typeof code === 'string' && code && <span className="janso-product-detail__code">{code}</span>}{status && <Badge tone={status === 'ACTIVE' ? 'success' : status === 'INACTIVE' ? 'warn' : 'neutral'}>{words(status)}</Badge>}{visible.has('kind') && typeof row?.kind === 'string' && <Badge>{words(row.kind)}</Badge>}</>}
      actions={actions} />
  </div>;
}

export function ProductDetailView({ company, fields, row, access, returnTo, family = false, onLeave }: {
  company: string; fields: readonly MasterField[]; row: Row; access: ClassificationAccess; returnTo: string; family?: boolean;
  onLeave?: React.MouseEventHandler<HTMLAnchorElement>;
}) {
  const id = useId(), format = useFormatters(), available = readable(fields, row);
  const facts = available.filter(field => !trading.has(field.key) && !recordInfo.has(field.key));
  const trade = available.filter(field => trading.has(field.key));
  const information = available.filter(field => recordInfo.has(field.key));
  const references = facts.filter(field => field.control?.kind === 'reference');
  const identity = facts.filter(field => field.control?.kind !== 'reference' && field.key !== 'description');
  const description = facts.find(field => field.key === 'description');
  const customs = fields.filter(field => field.visible && field.source === 'custom');
  const groups = [
    { key: 'details', title: 'Product overview', show: identity.length > 0 || !!description },
    { key: 'references', title: 'Classification & units', show: references.length > 0 },
    { key: 'specifications', title: 'Additional specifications', show: customs.length > 0 },
    { key: 'trading', title: 'Trading', show: trade.length > 0 },
    { key: 'record', title: 'Record information', show: information.length > 0 },
  ].filter(group => group.show);
  const value = (field: MasterField): ReactNode => {
    const raw = row[field.key];
    if (raw == null || raw === '') return <span className="janso-product-detail__empty">Not set</span>;
    if (typeof raw === 'boolean') return <span className="janso-product-detail__boolean" data-enabled={raw}>{raw ? 'Enabled' : 'Disabled'}</span>;
    if (field.key.endsWith('_at') && typeof raw === 'string') return format.dateTime(raw);
    if (field.key.endsWith('_date') && typeof raw === 'string') return format.date(raw);
    if (field.key === 'min_sale_quantity') return format.quantity(String(raw));
    if (Array.isArray(raw)) return raw.map(entry => typeof entry === 'string' ? field.control?.choices?.find(choice => choice.value === entry)?.label ?? words(entry) : String(entry)).join(', ') || 'None';
    if (typeof raw === 'object') return 'Additional details';
    if (typeof raw === 'string') return field.control?.choices?.find(choice => choice.value === raw)?.label ?? (recordInfo.has(field.key) || field.key === 'kind' ? words(raw) : raw);
    return String(raw);
  };
  const list = (entries: MasterField[]) => <dl className="janso-product-detail__facts">{entries.map(field => <div key={field.key}><dt>{label(field)}</dt><dd>{value(field)}</dd></div>)}</dl>;
  const section = (key: string, title: string, children: ReactNode, description?: string) => <section id={`${id}-${key}`} tabIndex={-1} aria-labelledby={`${id}-${key}-heading`} className="janso-product-detail__section">
    <div className="janso-product-detail__section-heading"><h2 id={`${id}-${key}-heading`}>{title}</h2>{description && <p>{description}</p>}</div>{children}
  </section>;
  return <div className="janso-product-detail" role="region" aria-label="Record details">
    {groups.length > 1 && <nav className="janso-product-detail__navigation" aria-label="Product detail sections">{groups.map(group => <a key={group.key} href={`#${id}-${group.key}`}>{group.title}</a>)}</nav>}
    <div className="janso-product-detail__layout">
      <div className="janso-product-detail__main">
        {(identity.length > 0 || description) && section('details', 'Product overview', <>{list(identity)}{description && <div className="janso-product-detail__description"><h3>{label(description)}</h3><p>{value(description)}</p></div>}</>, family ? 'The shared details that describe this product profile.' : 'The details that identify this product in your catalogue.')}
        {references.length > 0 && section('references', 'Classification & units', <div className="janso-product-detail__references">{references.map(field => <ProductCatalogField key={field.key} company={company} field={field} values={row} readView access={access} returnTo={returnTo} onLeave={onLeave} disabled onChange={() => undefined} />)}</div>, 'Connected master records and the units used by this product.')}
        {customs.length > 0 && section('specifications', 'Additional specifications', <div className="janso-product-detail__custom">{['shared_custom_fields', 'custom_fields'].map(group => {
          const entries = customs.filter(field => group === 'shared_custom_fields' ? field.key.startsWith('shared_custom_fields.') : !field.key.startsWith('shared_custom_fields.')).map(field => ({ ...field, key: field.key.replace(/^shared_custom_fields\./, '') }));
          return entries.length > 0 ? <ProductCatalogCustomFields key={group} company={company} fields={entries} values={{ ...row, custom_fields: row[group] }} disabled onChange={() => undefined} /> : null;
        })}</div>)}
        {!facts.length && !customs.length && <p className="janso-product-detail__empty">No product specifications are available with your current field access.</p>}
      </div>
      {(trade.length > 0 || information.length > 0) && <aside className="janso-product-detail__aside" aria-label="Product trading and record information">
        {trade.length > 0 && section('trading', 'Trading', list(trade), 'How this product can be bought and sold.')}
        {information.length > 0 && section('record', 'Record information', list(information))}
      </aside>}
    </div>
  </div>;
}
