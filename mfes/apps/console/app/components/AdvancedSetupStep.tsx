'use client';
import { useEffect, useState } from 'react';
import { Notice, TextField } from '@janso/ui';
import type { AdvancedOptions, AdvancedWork } from '../lib/advanced-product-draft';
import { businessSku, putBusiness, type BusinessSku } from '../lib/advanced-product-business';
import { AdvancedProductChoice } from './AdvancedProductChoice';
import { masterRequest } from '../lib/catalog-master-api';
import { requestFailure } from '../lib/service-call';

export function AdvancedSetupStep({ company, work, options, errors, onChange, disabled, locked = [], focusPath = '' }: { company: string; work: AdvancedWork; options: AdvancedOptions; errors: Record<string, string>; onChange: (work: AdvancedWork) => void; disabled: boolean; locked?: boolean[]; focusPath?: string }) {
  const [selected, setSelected] = useState(0);
  useEffect(() => { const match = /^business\.skus\.(\d+)\./.exec(focusPath); if (match) setSelected(Number(match[1])); }, [focusPath]);
  const sku = work.skus[selected] ?? work.skus[0]!;
  const selectedDisabled = disabled || !!locked[selected];
  const values = businessSku(work, sku);
  const path = `business.skus.${selected}.`;
  const change = (patch: Partial<BusinessSku>) => onChange(putBusiness(work, sku, { ...values, ...patch }));
  const pricing = options.defaults.configuration.pricing;
  const [unitDefaults, setUnitDefaults] = useState<AdvancedOptions['defaults'] | null>(null);
  const [unitFailure, setUnitFailure] = useState('');
  useEffect(() => {
    if (!sku.base_unit_id) { setUnitDefaults(null); return; }
    const controller = new AbortController();
    setUnitDefaults(null); setUnitFailure('');
    const params = new URLSearchParams({ as_of: options.today, kind: work.profile.kind, group_id: work.profile.group_id, product_type_revision_id: work.profile.product_type_revision_id, unit_id: sku.base_unit_id, currency: options.currency, include_price: 'true' });
    masterRequest<AdvancedOptions['defaults']>({ path: `/v1/companies/${company}/product-configuration/authoring-defaults?${params}`, signal: controller.signal }).then(value => {
      if (!controller.signal.aborted) setUnitDefaults(value);
    }).catch(error => { if (!controller.signal.aborted) setUnitFailure(requestFailure(error).message); });
    return () => controller.abort();
  }, [company, options.today, options.currency, work.profile.kind, work.profile.group_id, work.profile.product_type_revision_id, sku.base_unit_id]);
  const basis = unitDefaults?.price?.price_basis_quantity;
  const precision = unitDefaults?.price?.price_decimal_places;
  return <div className="product-wizard__sections"><section className="product-wizard__section"><h3>Set up each SKU</h3><p>{basis && precision !== undefined ? `Amounts are in ${options.currency} per ${basis} base unit. Current precision: ${precision} decimal places.` : 'Checking this SKU’s unit and price rules…'}</p>{unitFailure && <Notice tone="warning">Unit and price rules could not be loaded. {unitFailure}</Notice>}<div className="product-wizard__sku-list product-wizard__sku-list--row" role="group" aria-label="Business setup SKUs">{work.skus.map((row, index) => <button key={row.key} className="product-wizard__sku-tab" type="button" aria-pressed={selected === index} onClick={() => setSelected(index)}><strong>{row.sku || `SKU ${index + 1}`}</strong><span>{row.name || 'Needs details'}</span></button>)}</div></section>
    <section className="product-wizard__section" aria-labelledby="business-tax"><h3 id="business-tax">Tax and treatment</h3>{options.gst_enabled ? <div className="product-wizard__fields"><AdvancedProductChoice company={company} resource="tax_classifications" label={work.profile.kind === 'GOODS' ? 'HSN' : 'SAC'} value={values.classification_id} required disabled={selectedDisabled} error={errors[path + 'classification_id']} onChange={id => change({ classification_id: id })} /><AdvancedProductChoice company={company} resource="tax_rules" label="GST treatment / rate" value={values.rule_id} required disabled={selectedDisabled} error={errors[path + 'rule_id']} onChange={id => change({ rule_id: id })} /></div> : <p>GST classification is not enabled for this company.</p>}</section>
    <section className="product-wizard__section" aria-labelledby="business-profiles"><h3 id="business-profiles">Published policies</h3><p>These are resolved from the current company and Product Type configuration. Native readiness checks them before activation.</p><dl className="product-wizard__facts"><div><dt>Inventory profile</dt><dd>{work.profile.kind === 'SERVICE' ? 'Not applicable' : options.defaults.configuration.profiles.inventory_template_revision_id ?? 'No published default'}</dd></div><div><dt>Identifier profile</dt><dd>{work.profile.kind === 'SERVICE' ? 'Not applicable' : options.defaults.configuration.profiles.identifier_profile_id ?? 'Not configured'}</dd></div><div><dt>Warranty policy</dt><dd>{options.defaults.configuration.profiles.warranty_revision_id ?? 'Not configured'}</dd></div><div><dt>Return policy</dt><dd>{options.defaults.configuration.profiles.return_policy_revision_id ?? 'Not configured'}</dd></div><div><dt>Handling profile</dt><dd>{options.defaults.configuration.profiles.handling_revision_id ?? 'Not configured'}</dd></div></dl>
      {work.profile.kind === 'GOODS' && options.batch?.available && <label className="product-wizard__check"><input type="checkbox" disabled={selectedDisabled || options.batch?.required} checked={values.batch_enabled ?? !!options.batch?.required} onChange={event => change({ batch_enabled: event.target.checked })} /> Enable batch tracking for this SKU {options.batch?.required && '(required)'}</label>}{errors[path + 'batch_enabled'] && <Notice tone="danger">{errors[path + 'batch_enabled']}</Notice>}
    </section>
    <section className="product-wizard__section" aria-labelledby="business-prices"><h3 id="business-prices">Purchase and sale prices</h3><p>Prices remain drafts until their native publication is confirmed. Tax basis follows each named price level.</p>
      {sku.sellable && pricing.sale_price_mode !== 'DISABLED' && <div className="product-wizard__fields">{(options.sale_price_levels ?? []).map(level => <div key={level.plan_id}><TextField label={`${level.name} · ${options.currency} · ${level.tax_basis.toLowerCase()} tax${level.required ? ' · required' : ''}`} inputMode="decimal" value={values.sale_prices[level.plan_id] ?? ''} disabled={selectedDisabled || !options.price_levels_accessible} error={errors[path + 'sale_prices.' + level.plan_id]} onChange={event => change({ sale_prices: { ...values.sale_prices, [level.plan_id]: event.target.value } })} /></div>)}</div>}
      {sku.sellable && pricing.sale_price_mode === 'REQUIRED' && !(options.sale_price_levels ?? []).length && <Notice tone="warning">No accessible sale price level is available. Review the company price configuration.</Notice>}
      {sku.purchasable && pricing.purchase_reference_mode !== 'DISABLED' && <div className="product-wizard__fields"><TextField label={`Purchase reference · ${options.currency}`} inputMode="decimal" value={values.purchase_amount} disabled={selectedDisabled} error={errors[path + 'purchase_amount']} onChange={event => change({ purchase_amount: event.target.value })} /><TextField label="Purchase source reference" value={values.purchase_source} disabled={selectedDisabled} maxLength={500} onChange={event => change({ purchase_source: event.target.value })} /></div>}
      {work.profile.kind === 'GOODS' && pricing.mrp_mode !== 'DISABLED' && <div className="product-wizard__fields"><TextField label={`MRP · ${options.currency}`} inputMode="decimal" value={values.mrp_amount} disabled={selectedDisabled} error={errors[path + 'mrp_amount']} onChange={event => change({ mrp_amount: event.target.value })} /><TextField label="MRP jurisdiction" value={values.mrp_jurisdiction} disabled={selectedDisabled} maxLength={20} onChange={event => change({ mrp_jurisdiction: event.target.value.toUpperCase() })} /><TextField label="MRP source reference" value={values.mrp_source} disabled={selectedDisabled} maxLength={500} onChange={event => change({ mrp_source: event.target.value })} /></div>}
    </section>
  </div>;
}
