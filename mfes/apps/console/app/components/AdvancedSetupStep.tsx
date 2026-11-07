'use client';
import { useEffect, useState } from 'react';
import { Notice, TextField } from '@janso/ui';
import type { AdvancedOptions, AdvancedWork } from '../lib/advanced-product-draft';
import { businessSku, putBusiness, clearUnavailableBusiness, unavailableBusinessKeys, type BusinessSku } from '../lib/advanced-product-business';
import { AdvancedProductChoice } from './AdvancedProductChoice';
import { AdvancedPolicyFacts } from './AdvancedProductReview';
import { AdvancedPriceInput, useAdvancedNumericProblems, type NumericProblemHandler } from './AdvancedPriceInput';
import { masterRequest } from '../lib/catalog-master-api';
import { requestFailure } from '../lib/service-call';

export function AdvancedSetupStep({ company, work, options, errors, onChange, disabled, locked = [], focusPath = '', onNumericProblem, onReadyChange }: { company: string; work: AdvancedWork; options: AdvancedOptions; errors: Record<string, string>; onChange: (work: AdvancedWork) => void; disabled: boolean; locked?: boolean[]; focusPath?: string; onNumericProblem?: NumericProblemHandler; onReadyChange?: (ready: boolean) => void }) {
  const [selected, setSelected] = useState(0);
  const { invalid: invalidNumber, report: reportNumeric } = useAdvancedNumericProblems(onNumericProblem);
  useEffect(() => { const match = /^business\.skus\.(\d+)\./.exec(focusPath); if (match) setSelected(Number(match[1])); }, [focusPath]);
  const sku = work.skus[selected] ?? work.skus[0]!;
  const selectedDisabled = disabled || !!locked[selected];
  const values = businessSku(work, sku);
  const path = `business.skus.${selected}.`;
  const change = (patch: Partial<BusinessSku>) => onChange(putBusiness(work, sku, { ...values, ...patch }));
  const pricing = options.defaults.configuration.pricing;
  const [unitDefaults, setUnitDefaults] = useState<AdvancedOptions['defaults'] | null>(null);
  const [unitFailure, setUnitFailure] = useState('');
  const [reloadUnits, setReloadUnits] = useState(0);
  useEffect(() => { onReadyChange?.(!!locked[selected] || !sku.base_unit_id || (!!unitDefaults && !unitFailure && unitDefaults.quantity?.unit_id === sku.base_unit_id && unitDefaults.configuration.source_version === options.defaults.configuration.source_version && unitDefaults.configuration.policy_generation === options.defaults.configuration.policy_generation)); }, [sku.base_unit_id, unitDefaults, unitFailure, locked[selected], options.defaults.configuration.source_version, options.defaults.configuration.policy_generation, onReadyChange]);
  useEffect(() => () => onReadyChange?.(true), [onReadyChange]);
  useEffect(() => {
    if (!sku.base_unit_id) { setUnitDefaults(null); return; }
    const controller = new AbortController();
    setUnitDefaults(null); setUnitFailure('');
    const params = new URLSearchParams({ as_of: options.today, kind: work.profile.kind, group_id: work.profile.group_id, product_type_revision_id: work.profile.product_type_revision_id, unit_id: sku.base_unit_id, currency: options.currency, include_price: 'true' });
    masterRequest<AdvancedOptions['defaults']>({ path: `/v1/companies/${company}/product-configuration/authoring-defaults?${params}`, signal: controller.signal }).then(value => {
      if (controller.signal.aborted) return;
      if (value.quantity?.unit_id !== sku.base_unit_id || value.configuration.source_version !== options.defaults.configuration.source_version || value.configuration.policy_generation !== options.defaults.configuration.policy_generation) throw { status: 409, message: 'Unit or pricing settings changed. Reload the unit rules before continuing.' };
      setUnitDefaults(value);
    }).catch(error => { if (!controller.signal.aborted) setUnitFailure(requestFailure(error).message); });
    return () => controller.abort();
  }, [company, options.today, options.currency, work.profile.kind, work.profile.group_id, work.profile.product_type_revision_id, sku.base_unit_id, options.defaults.configuration.source_version, options.defaults.configuration.policy_generation, reloadUnits]);
  const basis = unitDefaults?.price?.price_basis_quantity;
  const precision = unitDefaults?.price?.price_decimal_places;
  const separatePricing = ([['unit_prices_mode', 'alternate-unit prices'], ['quantity_tiers_mode', 'quantity tiers'], ['channel_prices_mode', 'channel prices'], ['additional_currencies_mode', 'additional currencies'], ['formula_prices_mode', 'price formulas']] as const).filter(([key]) => pricing[key] === 'ENABLED').map(([, label]) => label);
  return <div className="product-wizard__sections"><section className="product-wizard__section"><h3>Set up each SKU</h3><p>{basis && precision !== undefined ? `Amounts are in ${options.currency} per ${basis} base unit. Current precision: ${precision} decimal places.` : 'Checking this SKU’s unit and price rules…'}</p>{unitFailure && <Notice tone="warning">Unit and price rules could not be loaded. {unitFailure} <button type="button" className="janso-link" disabled={selectedDisabled} onClick={() => setReloadUnits(value => value + 1)}>Reload unit rules</button></Notice>}<div className="product-wizard__sku-list product-wizard__sku-list--row" role="group" aria-label="Business setup SKUs">{work.skus.map((row, index) => <button key={row.key} className="product-wizard__sku-tab" type="button" aria-pressed={selected === index} disabled={invalidNumber} onClick={() => setSelected(index)}><strong>{row.sku || `SKU ${index + 1}`}</strong><span>{row.name || 'Needs details'}</span></button>)}</div></section>
    {unavailableBusinessKeys(work, options, selected).length > 0 && <Notice tone="warning" action={<button type="button" className="janso-btn janso-btn--secondary" disabled={selectedDisabled || invalidNumber} onClick={() => onChange(clearUnavailableBusiness(work, options, selected))}>Remove unavailable SKU details</button>}>Saved prices or tracking details for this SKU are no longer available under its current settings or access. Review and remove those entries to continue.</Notice>}
    <section className="product-wizard__section" aria-labelledby="business-tax"><h3 id="business-tax">Tax and treatment</h3>{options.gst_enabled ? <div className="product-wizard__fields"><AdvancedProductChoice company={company} resource="tax_classifications" label={work.profile.kind === 'GOODS' ? 'HSN' : 'SAC'} value={values.classification_id} required disabled={selectedDisabled} error={errors[path + 'classification_id']} onChange={id => change({ classification_id: id })} /><AdvancedProductChoice company={company} resource="tax_rules" label="GST treatment / rate" value={values.rule_id} required disabled={selectedDisabled} error={errors[path + 'rule_id']} onChange={id => change({ rule_id: id })} /></div> : <p>GST classification is not enabled for this company.</p>}</section>
    <section className="product-wizard__section" aria-labelledby="business-profiles"><h3 id="business-profiles">Published policies</h3><p>These settings come from your company and Product Type. We check them before making the SKU active.</p><AdvancedPolicyFacts company={company} options={options} kind={work.profile.kind} />
      {work.profile.kind === 'GOODS' && options.batch?.available && <label className="product-wizard__check"><input type="checkbox" disabled={selectedDisabled || options.batch?.required} checked={values.batch_enabled ?? !!options.batch?.required} onChange={event => change({ batch_enabled: event.target.checked })} /> Enable batch tracking for this SKU {options.batch?.required && '(required)'}</label>}{errors[path + 'batch_enabled'] && <Notice tone="danger">{errors[path + 'batch_enabled']}</Notice>}
    </section>
    <section className="product-wizard__section" aria-labelledby="business-prices">
      <h3 id="business-prices">Prices</h3>
      {separatePricing.length > 0 && <Notice>Enabled options outside this creation form: {separatePricing.join(', ')}. This form captures base-unit prices, purchase references and MRP. Additional price rules require separate pricing setup; creation does not generate them.</Notice>}
      <p>Enter amounts in {options.currency}. Keep up to four decimal places; configured price precision is {precision ?? 'being checked'}. Prices are checked before publication.</p>
      {sku.sellable && pricing.sale_price_mode !== 'DISABLED' && <section className="product-wizard__price-group" aria-label="Selling prices">
        <h4>Selling prices</h4>
        {(options.sale_price_levels ?? []).length > 0 ? <div className="product-wizard__fields">{options.sale_price_levels!.map(level => <AdvancedPriceInput key={level.plan_id} label={`${level.name} selling price`} path={path + 'sale_prices.' + level.plan_id} onNumericProblem={reportNumeric} unit={options.currency} required={level.required} value={values.sale_prices[level.plan_id] ?? ''} hint={`${level.tax_basis === 'INCLUSIVE' ? 'Includes tax' : 'Excludes tax'}. Per ${basis ?? 'configured'} base unit(s).`} disabled={selectedDisabled || !options.price_levels_accessible} error={errors[path + 'sale_prices.' + level.plan_id]} onChange={amount => change({ sale_prices: { ...values.sale_prices, [level.plan_id]: amount } })} />)}</div> : <Notice tone={pricing.sale_price_mode === 'REQUIRED' ? 'warning' : 'info'}>{!options.price_levels_accessible ? 'Selling prices are unavailable with your current access.' : 'No active selling-price level is available. Review company pricing defaults.'}</Notice>}
      </section>}
      {sku.purchasable && pricing.purchase_reference_mode !== 'DISABLED' && <section className="product-wizard__price-group" aria-label="Purchase reference">
        <h4>Purchase reference</h4><p>An estimated purchase amount. Opening stock uses its own valuation cost.</p>
        <div className="product-wizard__fields">
          <AdvancedPriceInput label="Purchase reference amount" path={path + 'purchase_amount'} onNumericProblem={reportNumeric} unit={options.currency} requirePositive required={pricing.purchase_reference_mode === 'REQUIRED'} value={values.purchase_amount} disabled={selectedDisabled} error={errors[path + 'purchase_amount']} onChange={purchase_amount => change({ purchase_amount })} />
          <TextField label="Purchase source reference" value={values.purchase_source} required={!!values.purchase_amount} hint="Required when an amount is entered; for example, a supplier quotation." disabled={selectedDisabled} error={errors[path + 'purchase_source']} maxLength={500} onChange={event => change({ purchase_source: event.target.value })} />
        </div>
      </section>}
      {work.profile.kind === 'GOODS' && pricing.mrp_mode !== 'DISABLED' && <section className="product-wizard__price-group" aria-label="Maximum retail price">
        <h4>Maximum retail price (MRP)</h4>
        <div className="product-wizard__fields">
          <AdvancedPriceInput label="MRP" path={path + 'mrp_amount'} onNumericProblem={reportNumeric} unit={options.currency} requirePositive required={pricing.mrp_mode === 'REQUIRED'} value={values.mrp_amount} disabled={selectedDisabled} error={errors[path + 'mrp_amount']} onChange={mrp_amount => change({ mrp_amount })} />
          <TextField label="MRP jurisdiction" value={values.mrp_jurisdiction} required={!!values.mrp_amount} hint="Required with MRP; use the jurisdiction code, such as IN." disabled={selectedDisabled} error={errors[path + 'mrp_jurisdiction']} maxLength={20} onChange={event => change({ mrp_jurisdiction: event.target.value.toUpperCase() })} />
          <TextField label="MRP source reference" value={values.mrp_source} required={!!values.mrp_amount} hint="Required with MRP; for example, a manufacturer price list." disabled={selectedDisabled} error={errors[path + 'mrp_source']} maxLength={500} onChange={event => change({ mrp_source: event.target.value })} />
        </div>
      </section>}
      {(!sku.sellable || pricing.sale_price_mode === 'DISABLED') && (!sku.purchasable || pricing.purchase_reference_mode === 'DISABLED') && (work.profile.kind !== 'GOODS' || pricing.mrp_mode === 'DISABLED') && <p>Price entry is disabled for this SKU by its trade directions and company settings.</p>}
      {work.profile.kind === 'GOODS' && options.batch?.available && <p>Batch-specific prices and physical MRP can be entered with opening batches in the next step, or later through batch management.</p>}
    </section>
  </div>;
}
