'use client';

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import type { components } from '@janso/api-client/catalog';
import { Button, Card, CardBody, CustomFields, FieldGroup, FieldPair, Notice, PageHeader, PageNavigation, SearchSelect, Select, TextField, Toggle, customCondition, customPatch, useFormatters, type SearchSelectLoader, type SearchSelectOption } from '@janso/ui';
import { masterRequest } from '../lib/catalog-master-api';
import { masterCustomFields } from '../lib/catalog-masters';
import { requestFailure, type RequestFailure } from '../lib/service-call';
import { useProductMode } from './ProductModeProvider';
import { catalogBack } from '../lib/product-classification';
import { useUnsavedChanges } from '../lib/use-unsaved-changes';
import { SimpleProductBatches, batchInputs, batchRow, type BatchRow } from './SimpleProductBatches';

import { SimpleProductSerials, serialInputs, type SerialRow } from './SimpleProductSerials';

type Options = components['schemas']['SimpleCreationOptions'];
type Input = components['schemas']['SimpleCreationInput'];
type Status = components['schemas']['SimpleCreationStatus'];
type Field = components['schemas']['FieldMetadata'];
type Choice = { id: string; code?: string; name?: string; description?: string; value?: string; label?: string };
type Choices = { items: Choice[]; page: { has_more: boolean; next_cursor?: string | null } };
type CategoryRow = { key: string; scheme_id: string; category_id: string; is_primary: boolean };
const categoryRow = (scheme_id = ''): CategoryRow => ({ key: crypto.randomUUID(), scheme_id, category_id: '', is_primary: false });

function ProductChoice({ company, field, resource, value, onChange, kind, date, parent, disabled, error, selectedLabel }: {
  company: string; field: Field; resource: string; value: string | null;
  onChange: (value: string | null) => void; kind?: Input['kind']; date?: string; parent?: string | null; disabled: boolean; error?: string; selectedLabel?: string;
}) {
  const [selected, setSelected] = useState<SearchSelectOption | null>(null);
  const tax = resource.startsWith('tax-');
  const path = `/v1/companies/${company}/` + (tax ? resource : `option-sources/catalog.${resource}`);
  const load = useCallback<SearchSelectLoader>(async ({ q, cursor, signal }) => {
    const params = new URLSearchParams({ limit: '50' });
    if (q.trim().length >= 2) params.set('q', q.trim());
    if (cursor) params.set('cursor', cursor);
    if (tax && kind) params.set('item_kind', kind);
    if (resource === 'tax-classifications' && date) params.set('as_of', date);
    if (resource === 'tax-rules') params.set('is_active', 'true');
    if (parent) params.set('parent_id', parent);
    const page = await masterRequest<Choices>({ path: path + '?' + params, signal });
    return { items: page.items.map(row => {
      const label = row.label ?? row.name ?? row.description ?? row.code ?? 'Choice';
      return { id: row.value ?? row.id, label: tax && row.code && label !== row.code ? `${row.code} · ${label}` : label, meta: tax ? undefined : row.code };
    }), nextCursor: page.page.has_more ? page.page.next_cursor ?? null : null };
  }, [path, kind, date, tax, resource, parent]);
  useEffect(() => {
    if (!value || selected?.id === value) return;
    const controller = new AbortController();
    // The only suggested reference is the company's native Default group.
    if (resource === 'item_groups') masterRequest<Choice>({ path: `/v1/companies/${company}/item-groups/${value}`, signal: controller.signal })
      .then(row => { if (!controller.signal.aborted) setSelected({ id: value, label: row.name ?? row.code ?? 'Product group' }); }).catch(() => undefined);
    return () => controller.abort();
  }, [company, resource, value, selected?.id]);
  return <SearchSelect label={field.label} error={error} value={value} selected={selected?.id === value ? selected : value ? { id: value, label: selectedLabel ?? 'Loading choice…' } : null}
    loadOptions={load} scopeKey={path + ':' + kind + ':' + parent} minQueryLength={0} required={field.required} clearable={!field.required}
    disabled={disabled || !field.writable || field.conditional_access} onChange={(id, option) => { setSelected(option); onChange(id); }} />;
}

const decimals = /^(?:0|[1-9]\d{0,14})(?:\.\d{1,4})?$/;
const nonzero = (value: string) => /[1-9]/.test(value);
const detailFields = { brand: ['brand_id'], model: ['model_code'], barcode: ['barcode_value', 'barcode_symbology'], manufacturer: ['manufacturer_id'] } as const;
type Detail = keyof typeof detailFields;

export function SimpleProductCreate({ company, returnTo }: { company: string; returnTo?: string }) {
  const mode = useProductMode();
  const format = useFormatters();
  const root = `/v1/companies/${company}/simple-product-creations`;
  const storageKey = 'simple-product-save:' + company;
  const back = catalogBack(returnTo, '/masters/items');
  const [kind, setKind] = useState<'GOODS' | 'SERVICE'>('GOODS');
  const [step, setStep] = useState(0);
  const [batchOn, setBatchOn] = useState<boolean | null>(null);
  const [batches, setBatches] = useState<BatchRow[]>([]);
  const [serials, setSerials] = useState<SerialRow[]>([]);
  const [values, setValues] = useState<Record<string, string>>({ name: '', code: '', base_unit_id: '', group_id: '', opening_quantity: '0', barcode_symbology: 'CODE128' });
  const [details, setDetails] = useState<Partial<Record<Detail, boolean>>>({});
  const [categories, setCategories] = useState<CategoryRow[]>([]);
  const [categoryOn, setCategoryOn] = useState<boolean | null>(null);
  const [custom, setCustom] = useState<Record<string, unknown>>({});
  const [shared, setShared] = useState<Record<string, unknown>>({});
  const [options, setOptions] = useState<Options | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<RequestFailure | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState<Status | null>(null);
  const [intent, setIntent] = useState<{ key: string; body: Input; revision?: number } | null>(null);
  const [editing, setEditing] = useState(false);
  const [recoverKey, setRecoverKey] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const [dirty, setDirty] = useState(false);
  const alive = useRef(true);
  const active = useRef(false);
  const form = useRef<HTMLFormElement>(null);
  const feedback = useRef<HTMLDivElement>(null);
  const completed = useRef<HTMLDivElement>(null);
  const locked = loading || busy || !!recoverKey || (!!job && !editing) || !!intent;
  useUnsavedChanges(() => job?.status !== 'COMPLETE' && (dirty || !!intent || !!job || !!recoverKey || busy));
  const change = (key: string, value: string | null, authored = true) => {
    if (authored) setDirty(true);
    setValues(before => ({ ...before, [key]: value ?? '' }));
  };

  useEffect(() => {
    if (busy || (!failure && !Object.keys(errors).length)) return;
    const invalid = form.current?.querySelector<HTMLElement>('[aria-invalid="true"]');
    const section = invalid?.closest<HTMLElement>('[data-product-step]');
    const focus = () => {
      const editable = Array.from(form.current?.querySelectorAll<HTMLElement>('[aria-invalid="true"]:not(:disabled)') ?? [])
        .find(control => !control.closest('[hidden]'));
      (editable ?? feedback.current)?.focus();
    };
    if (!section?.hidden) { focus(); return; }
    setStep(Number(section.dataset.productStep));
    const frame = requestAnimationFrame(focus);
    return () => cancelAnimationFrame(frame);
  }, [errors, failure, busy, locked]);
  useEffect(() => { if (job?.status === 'COMPLETE') completed.current?.focus(); }, [job?.status]);

  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true);
    const query = new URLSearchParams({ kind });
    if (values.group_id) query.set('group_id', values.group_id);
    masterRequest<Options>({ path: root + '/options?' + query, signal: controller.signal }).then(result => {
      if (controller.signal.aborted) return;
      if (result.company_id !== company || result.kind !== kind || !Array.isArray(result.fields)) throw new Error('Product settings could not be verified.');
      setOptions(result); setLoading(false);
      if (!values.group_id && result.default_group_id) change('group_id', result.default_group_id, false);
    }).catch(error => { if (!controller.signal.aborted) { setOptions(null); setFailure(requestFailure(error)); setLoading(false); } });
    return () => controller.abort();
  }, [root, company, kind, values.group_id, reload]);

  useEffect(() => {
    if (!options || options.configuration.options.category_mode === 'DISABLED') return;
    const required = options.required_category_schemes ?? [];
    setCategories(before => {
      const missing = required.filter(scheme => !before.some(row => row.scheme_id === scheme.id));
      if (missing.length) return [...before.filter(row => row.scheme_id || row.category_id), ...missing.map(scheme => categoryRow(scheme.id))];
      if (!before.length && (options.configuration.options.category_mode === 'REQUIRED' || options.configuration.options.category_default)) return [categoryRow()];
      return before;
    });
  }, [options]);

  const continueSave = useCallback(async (initial: Status) => {
    let current = initial;
    const started = Date.now();
    let budget = 60000;
    while (alive.current && current.status !== 'COMPLETE') {
      if (current.step.startsWith('BATCH') || current.step === 'SERIAL' || ['OPENING', 'VOUCHER', 'SUBMIT', 'ISSUE', 'POST', 'FINALIZE'].includes(current.step)) budget = 300000;
      if (Date.now() - started > budget) throw { status: 503, message: 'Product setup is saved and still processing. Retry Save to check its progress.' } satisfies RequestFailure;
      try {
        current = await masterRequest<Status>({ path: root + '/' + current.id + '/advance', method: 'POST' });
      } catch (error) {
        const problem = requestFailure(error);
        const sourceLag = current.step === 'VOUCHER' && problem.status === 409 && problem.message === 'voucher master evidence is unavailable or stale';
        if (!sourceLag && (problem.status !== 429 || (!current.step.startsWith('BATCH') && current.step !== 'SERIAL'))) throw error;
        await new Promise(resolve => setTimeout(resolve, 2000));
        continue;
      }
      if (current.company_id !== company || current.id !== initial.id) throw new Error('Product progress could not be verified.');
      if (!alive.current) return;
      setJob(current);
      if (current.status !== 'COMPLETE') await new Promise(resolve => setTimeout(resolve, current.step === 'FINALIZE' ? 1500 : current.step === 'SERIAL' ? 600 : 100));
    }
    if (current.status === 'COMPLETE') { sessionStorage.removeItem(storageKey); setIntent(null); }
  }, [root, company, storageKey]);

  useEffect(() => {
    const key = sessionStorage.getItem(storageKey);
    if (!key || active.current) return;
    active.current = true; setBusy(true);
    masterRequest<Status>({ path: root + '/by-key/' + key }).then(async saved => {
      if (!alive.current) return;
      setJob(saved); await continueSave(saved);
    }).catch(error => {
      if (!alive.current) return;
      const problem = requestFailure(error);
      if (problem.status === 404) sessionStorage.removeItem(storageKey);
      else { setRecoverKey(key); setFailure(problem); }
    }).finally(() => { active.current = false; if (alive.current) setBusy(false); });
  }, [root, storageKey, continueSave]);

  async function save(event?: React.FormEvent) {
    event?.preventDefault();
    if (stockStep && step === 0 && !job && !intent && !recoverKey) {
      setFailure(null);
      const problems: Record<string, string> = {};
      for (const key of requiredKeys.filter(key => !key.includes('price') && key !== 'mrp')) if (!values[key]?.trim()) problems[key] = `${field(key)?.label ?? key} is required.`;
      setErrors(problems); if (!Object.keys(problems).length) setStep(1); return;
    }
    if (active.current || !options || ((!job || editing) && (blocked || openingBlocked))) return;
    setFailure(null); setErrors({});
    if (recoverKey) {
      active.current = true; setBusy(true);
      try {
        const saved = await masterRequest<Status>({ path: root + '/by-key/' + recoverKey });
        setRecoverKey(null); setJob(saved); await continueSave(saved);
      } catch (error) {
        const problem = requestFailure(error); setFailure(problem);
        if (problem.status === 404) { sessionStorage.removeItem(storageKey); setRecoverKey(null); }
      } finally { active.current = false; if (alive.current) setBusy(false); }
      return;
    }
    let command = intent;
    if ((!job || editing) && !command) {
      const problems: Record<string, string> = {};
      for (const key of requiredKeys) if (!values[key]?.trim()) problems[key] = `${field(key)?.label ?? key} is required.`;
      if (!values.name?.trim()) problems.name = 'Enter the product name.';
      if (!values.base_unit_id) problems.base_unit_id = 'Choose the base unit.';
      const input: Input = { kind, name: values.name!.trim(), code: values.code?.trim() || null, base_unit_id: values.base_unit_id!, group_id: values.group_id || null };
      for (const [key, entered] of [['custom_fields', custom], ['shared_custom_fields', shared]] as const) {
        const definitions = customs(key + '.');
        const resolved = { ...Object.fromEntries(definitions.filter(field => field.custom?.is_active).map(field => [field.key, field.custom?.default_value])), ...entered };
        const numeric = new Set(definitions.filter(field => ['decimal', 'integer'].includes(field.custom?.data_type ?? '')).map(field => field.key));
        const visible = definitions.filter(field => field.visible && field.writable && field.custom?.is_active && field.custom.data_type !== 'auto_number' && customCondition(field.custom.visibility, { ...values, kind, ...resolved }, numeric));
        for (const field of visible) if (field.required && (resolved[field.key] == null || resolved[field.key] === '')) problems[key + '.' + field.key] = `${field.label} is required.`;
        try { input[key] = customPatch(visible, resolved, {}); } catch (error) { problems[key] = error instanceof Error ? error.message : 'Check additional information.'; }
      }
      if (options.gst_enabled) {
        if (values.classification_id && values.rule_id) input.tax = { classification_id: values.classification_id, rule_id: values.rule_id, directions: ['SALE', 'PURCHASE'] };
      }
      for (const key of (batchEnabled ? [] : ['purchase_price', 'sale_price', 'mrp']) as Array<'purchase_price' | 'sale_price' | 'mrp'>) {
        if (writable(key) && values[key]) {
          if (!decimals.test(values[key]!) || (key === 'mrp' && !nonzero(values[key]!))) problems[key] = key === 'mrp' ? 'Enter a positive MRP with up to four decimal places.' : 'Enter an amount of zero or more with up to four decimal places.';
          input[key] = values[key];
        }
      }
      const selling = batchEnabled ? [] : saleLevels.filter(level => writable(saleKey(level.price_level_id)) && values[saleKey(level.price_level_id)]);
      if (selling.length) input.sale_prices = selling.map(level => {
        const key = saleKey(level.price_level_id); const amount = values[key]!;
        if (!decimals.test(amount)) problems[key] = 'Enter an amount of zero or more with up to four decimal places.';
        return { price_level_id: level.price_level_id, amount };
      });
      for (const key of ['brand_id', 'series_id', 'model_code', 'manufacturer_id', 'manufacturer_site_id'] as const) if (writable(key) && values[key]) input[key] = values[key];
      if (categoryEnabled) {
        if (!categories.length) problems.categories = 'Add a category.';
        categories.forEach((row, index) => {
          if (!row.scheme_id) problems[`categories.${index}.scheme_id`] = 'Choose the category scheme.';
          if (!row.category_id) problems[`categories.${index}.category_id`] = 'Choose the category.';
          if (row.category_id && categories.some((other, otherIndex) => otherIndex < index && other.category_id === row.category_id)) problems[`categories.${index}.category_id`] = 'This category is already selected.';
        });
        input.categories = categories.map(({ scheme_id, category_id, is_primary }) => ({ scheme_id, category_id, is_primary }));
      }
      if (detailEnabled('barcode') && detailWritable('barcode')) input.barcode = {
        value: values.barcode_value ?? '', symbology: values.barcode_symbology as NonNullable<Input['barcode']>['symbology'],
      };
      if (batchAvailable) input.batch_enabled = batchEnabled;
      if (batchEnabled) {
        const prepared = batchInputs(batches, options);
        input.batches = prepared.batches; Object.assign(problems, prepared.errors);
        if (prepared.batches.some(row => nonzero(String(row.opening_quantity ?? '0')))) input.opening_date = options.opening_date;
      }
      if (!batchEnabled && kind === 'GOODS' && options.inventory_enabled && writable('opening_quantity')) {
        const quantity = serialEnabled ? String(serials.length) : values.opening_quantity || '0';
        if (serialEnabled) { const prepared = serialInputs(serials, options); input.serials = prepared.serials; Object.assign(problems, prepared.errors); }
        if (!decimals.test(quantity)) problems.opening_quantity = 'Enter a quantity of zero or more with up to four decimal places.';
        if (nonzero(quantity) && !input.purchase_price) problems.purchase_price = 'Enter Purchase price to value opening stock.';
        input.opening_quantity = quantity;
        if (nonzero(quantity)) input.opening_date = options.opening_date;
      }
      if (Object.keys(problems).length) { setErrors(problems); if (stockStep && Object.keys(problems).some(key => !key.startsWith('batches') && !key.startsWith('serials') && !key.includes('price') && !['mrp', 'opening_quantity'].includes(key))) setStep(0); return; }
      command = { key: crypto.randomUUID(), body: input, ...(editing && job ? { revision: job.row_version } : {}) };
      setIntent(command); if (!job) sessionStorage.setItem(storageKey, command.key);
    }
    active.current = true; setBusy(true);
    try {
      const saved = command?.revision && job
        ? await masterRequest<Status>({ path: root + '/' + job.id, method: 'PATCH', key: command.key, body: { expected_version: command.revision, product: command.body } })
        : job ?? await masterRequest<Status>({ path: root, method: 'POST', key: command!.key, body: command!.body });
      if (!alive.current) return;
      setEditing(false); setJob(saved); await continueSave(saved);
    } catch (error) {
      if (!alive.current) return;
      const problem = requestFailure(error); setFailure(problem);
      if (problem.status >= 400 && problem.status < 500 && problem.status !== 408 && problem.status !== 429) {
        const key = sessionStorage.getItem(storageKey);
        try {
          const saved = await masterRequest<Status>({ path: root + '/by-key/' + key });
          setJob(saved); setEditing(false);
          if (saved.can_edit) setIntent(null);
        } catch (lookupError) {
          if (requestFailure(lookupError).status === 404) { setIntent(null); sessionStorage.removeItem(storageKey); }
          else setRecoverKey(key);
        }
      }
    } finally { active.current = false; if (alive.current) setBusy(false); }
  }
  const field = (key: string) => options?.fields?.find(value => value.key === key);
  const batchAvailable = kind === 'GOODS' && !!options?.batch?.available;
  const serialEnabled = kind === 'GOODS' && !!options?.serial?.enabled;
  const stockStep = batchAvailable || serialEnabled;
  const batchEnabled = batchAvailable && (!!options?.batch?.required || !!batchOn);
  const saleLevels = options?.sale_price_levels ?? [];
  const saleKey = (id: string) => 'sale_prices.' + id;
  const accessible = (key: string) => !!field(key)?.visible && !!field(key)?.writable && !field(key)?.conditional_access;
  const categoryMode = options?.configuration.options.category_mode;
  const requiredSchemes = options?.required_category_schemes ?? [];
  const categoryRequired = categoryMode === 'REQUIRED' || requiredSchemes.length > 0;
  const categoryEntered = categories.some(row => row.scheme_id || row.category_id);
  const categoryWritable = ['category_scheme_id', 'category_id'].every(accessible) && !!field('category_is_primary')?.writable && !field('category_is_primary')?.conditional_access;
  const categoryEnabled = !!categoryMode && categoryMode !== 'DISABLED' && (categoryRequired || (categoryOn ?? (categoryEntered || (categoryWritable && !!options?.configuration.options.category_default))));
  const detailMode = (key: Detail) => options?.configuration.options[`${key}_mode`];
  const detailWritable = (key: Detail) => detailFields[key].every(accessible);
  const detailEnabled = (key: Detail) => detailMode(key) === 'REQUIRED' ||
    (!!detailMode(key) && detailMode(key) !== 'DISABLED' &&
      (details[key] ?? (!!values[detailFields[key][0]] || (detailWritable(key) && !!options?.configuration.options[`${key}_default`]))));
  const shown = (key: string) => {
    if (!field(key)?.visible) return false;
    if (key === 'brand_id' || key === 'series_id') return detailEnabled('brand');
    if (key === 'model_code') return detailEnabled('model');
    if (key.startsWith('barcode_')) return detailEnabled('barcode');
    if (key === 'manufacturer_id' || key === 'manufacturer_site_id') return kind === 'GOODS' && detailEnabled('manufacturer');
    return true;
  };
  const writable = (key: string) => shown(key) && field(key)?.writable && !field(key)?.conditional_access;
  const hasOpening = kind === 'GOODS' && (batchEnabled ? batches.some(row => nonzero(row.values.opening_quantity ?? '0')) : serialEnabled ? serials.length > 0 : nonzero(values.opening_quantity ?? '0'));
  const requiredKeys = ['name', 'base_unit_id', 'group_id', ...(options?.gst_enabled ? ['classification_id', 'rule_id'] : []),
    ...(Object.keys(detailFields) as Detail[]).filter(detailEnabled).flatMap(key => [...detailFields[key]]),
    ...(batchEnabled ? [] : saleLevels.filter(level => level.required).map(level => saleKey(level.price_level_id))),
    ...(batchEnabled ? [] : Object.entries({ purchase_price: options?.configuration.pricing.purchase_reference_mode, sale_price: saleLevels.length ? 'DISABLED' : options?.configuration.pricing.sale_price_mode,
      mrp: kind === 'GOODS' ? options?.configuration.pricing.mrp_mode : 'DISABLED' }).filter(([, mode]) => mode === 'REQUIRED').map(([key]) => key))];
  const selectedDetails = (Object.keys(detailFields) as Detail[]).filter(key => details[key] !== false && !!values[detailFields[key][0]]);
  const unavailableEntries = ['purchase_price', 'sale_price', 'mrp', ...Object.keys(values).filter(key => key.startsWith('sale_prices.')), ...selectedDetails.flatMap(key => [...detailFields[key]]),
    ...(selectedDetails.includes('brand') ? ['series_id'] : [])]
    .filter(key => !!values[key] && !writable(key) && !requiredKeys.includes(key));
  if (selectedDetails.includes('manufacturer') && values.manufacturer_site_id && !writable('manufacturer_site_id')) unavailableEntries.push('manufacturer_site_id');
  if (categoryOn !== false && categoryEntered && (categoryMode === 'DISABLED' || !categoryWritable)) unavailableEntries.push('categories');
  if (categories.some(row => row.is_primary) && !accessible('category_is_primary') && categoryOn !== false) unavailableEntries.push('category_is_primary');
  function clearUnavailable() {
    setDirty(true); setErrors({}); setFailure(null);
    const disabledDetails = selectedDetails.filter(key => detailFields[key].some(field => unavailableEntries.includes(field)));
    if (unavailableEntries.includes('serials')) setSerials([]);
    if (unavailableEntries.includes('batches')) { setBatches([]); setBatchOn(null); setStep(0); }
    if (unavailableEntries.includes('categories')) { setCategories([]); setCategoryOn(false); }
    if (unavailableEntries.includes('category_is_primary')) setCategories(before => before.map(row => ({ ...row, is_primary: false })));
    setDetails(before => ({ ...before, ...Object.fromEntries(disabledDetails.map(key => [key, false])) }));
    setValues(before => {
      const next = { ...before };
      for (const key of unavailableEntries) next[key] = '';
      if (disabledDetails.includes('brand')) next.series_id = '';
      if (disabledDetails.includes('manufacturer')) next.manufacturer_site_id = '';
      if (disabledDetails.includes('barcode')) { next.barcode_value = ''; next.barcode_symbology = 'CODE128'; }
      return next;
    });
  }
  const validation = { ...failure?.fields, ...errors };
  const fieldError = (key: string) => {
    const submitted = intent?.body.sale_prices ?? saleLevels.filter(level => values[saleKey(level.price_level_id)]);
    const index = submitted.findIndex(level => key === saleKey(level.price_level_id));
    return validation[key] ?? validation['initial_setup.' + key] ?? validation['tax.' + key] ?? (key === 'manufacturer_id' ? validation['initial_setup.manufacturer.manufacturer_id'] ?? validation['initial_setup.manufacturer'] : key === 'manufacturer_site_id' ? validation['initial_setup.manufacturer.site_id'] : undefined) ?? (index >= 0 ? validation[`sale_prices.${index}.amount`] : undefined) ?? (key.startsWith('barcode_')
      ? validation['barcode.' + key.slice(8)] ?? validation['initial_setup.barcodes.0.' + key.slice(8)] ?? validation['initial_setup.barcodes.0'] : undefined);
  };
  const customErrors = (prefix: string) => Object.fromEntries(Object.entries(validation).filter(([key]) => key.startsWith(prefix)).map(([key, message]) => [key.slice(prefix.length), message]));
  const textField = (key: string, label: string, required = false, hint?: string) => shown(key) && <TextField key={key} label={field(key)?.label || label} value={values[key] ?? ''} required={required}
    disabled={locked || !writable(key)} error={fieldError(key)} hint={hint}
    inputMode={key.includes('price') || key === 'mrp' || key === 'opening_quantity' ? 'decimal' : undefined} maxLength={key === 'code' ? 30 : key === 'name' || key === 'model_code' ? 100 : key === 'barcode_value' ? 128 : undefined}
    onChange={event => change(key, event.target.value)} />;
  const choice = (key: string, resource: string, label: string, required = false, parent?: string) => shown(key) && <ProductChoice company={company} field={{ ...field(key)!, label, required }} resource={resource} value={values[key] || null}
    onChange={value => { change(key, value); if (key === 'brand_id') change('series_id', null); if (key === 'manufacturer_id') change('manufacturer_site_id', null); }} kind={kind} date={options?.today} parent={parent} disabled={locked} error={fieldError(key)} />;
  const detailSection = (key: Detail, label: string, children: ReactNode) => detailMode(key) && detailMode(key) !== 'DISABLED' && detailFields[key].some(value => field(value)?.visible) &&
    <FieldGroup title={label} hint={detailMode(key) === 'REQUIRED' ? 'Required by Product Configuration.' : !detailWritable(key) ? 'Your field access does not allow these details.' : undefined}
      headerEnd={<label className="janso-check"><Toggle label={'Use ' + label} checked={detailEnabled(key)}
        disabled={locked || detailMode(key) === 'REQUIRED' || (!detailWritable(key) && !detailEnabled(key))} onChange={enabled => {
          setDirty(true); setDetails(before => ({ ...before, [key]: enabled })); setErrors({}); setFailure(null);
        }} /><span>Use {label}</span></label>}>
      {detailEnabled(key) && children}
    </FieldGroup>;
  const customs = (prefix: string) => masterCustomFields((options?.fields ?? []).filter(value => value.source === 'custom' && value.key.startsWith(prefix)).map(value => ({ ...value, key: value.key.slice(prefix.length) })));
  const customOptions = (source: string, parent?: string | null): SearchSelectLoader => async ({ q, cursor, signal }) => {
    const params = new URLSearchParams({ limit: '50', as_of: options!.today });
    if (q.trim().length >= 2) params.set('q', q.trim());
    if (cursor) params.set('cursor', cursor);
    if (parent) params.set('parent_id', parent);
    const page = await masterRequest<Choices>({ path: `/v1/companies/${company}/option-sources/${encodeURIComponent(source)}?${params}`, signal });
    return { items: page.items.map(row => ({ id: row.value ?? row.id, label: row.label ?? row.name ?? row.code ?? 'Choice' })), nextCursor: page.page.has_more ? page.page.next_cursor ?? null : null };
  };
  const blockedByAccess = options && (requiredKeys.some(key => !writable(key)) || (categoryEnabled && !categoryWritable) || (hasOpening && (!options.inventory_enabled || !writable('opening_quantity'))));
  if (!batchAvailable && (batchOn || batches.length)) unavailableEntries.push('batches');
  if ((!serialEnabled || batchEnabled) && serials.length) unavailableEntries.push('serials');
  if (serialEnabled && nonzero(values.opening_quantity ?? '0')) unavailableEntries.push('opening_quantity');
  const blocked = (hasOpening && serialEnabled && !accessible('serial_identifiers')) || blockedByAccess || unavailableEntries.length > 0 || (batchAvailable && !accessible('batch_enabled'));
  const openingBlocked = hasOpening && !writable('purchase_price');
  const another = '/masters/items/new' + (back === '/masters/items' ? '' : '?returnTo=' + encodeURIComponent(back));

  if (mode?.data?.product_family_sku_enabled) return <Notice>This company uses Product profiles and SKUs. Simple product creation is available when that mode is disabled in Product Configuration.</Notice>;
  return <section className={'janso-page janso-simple-product' + (batchAvailable && step === 1 && batchEnabled ? ' janso-simple-product--batches' : '')}>
    <PageNavigation back={{ href: back, label: 'products' }} breadcrumbs={[{ label: 'Products', href: back }, { label: 'New product' }]} />
    <PageHeader title="New product" lede="Add a product or service and make it ready to use." />
    {(failure || Object.keys(errors).length > 0) && <div ref={feedback} tabIndex={-1}><Notice tone="danger">{failure?.message ?? 'Check the highlighted fields and save again.'}</Notice></div>}
    {blockedByAccess && <Notice tone="warning">Your field access does not allow all required product details. Ask your administrator to review product access.</Notice>}
    {unavailableEntries.length > 0 && <Notice tone="warning" action={<Button type="button" variant="ghost" disabled={locked} onClick={clearUnavailable}>Clear unavailable details</Button>}>Some entered details are no longer available under current settings or field access. Clear these entries to continue, or restore the settings.</Notice>}
    {job?.status === 'COMPLETE' ? <div ref={completed} role="region" aria-label="Product saved" tabIndex={-1}><Card><CardBody><Notice tone="success">Product {job.code} is active and ready.{job.opening_posted ? ' Opening stock has been posted.' : ''}</Notice><div className="janso-form-actions"><a className="janso-btn janso-btn--primary" href={another}>Create another product</a><a className="janso-btn janso-btn--ghost" href={back}>Back to products</a></div></CardBody></Card></div> : loading && !options ? <p role="status">Loading product settings…</p> : !options ? <Button onClick={() => { setFailure(null); setReload(value => value + 1); }}>Retry loading settings</Button> :
      <form ref={form} onSubmit={save} noValidate className="janso-flow" aria-busy={busy}>
        {stockStep && <nav className="janso-form-actions" aria-label="Product creation steps"><Button type="button" variant="ghost" aria-current={step === 0 ? 'step' : undefined} disabled={locked} onClick={() => setStep(0)}>1. Product details</Button><Button type="button" variant="ghost" aria-current={step === 1 ? 'step' : undefined} disabled={locked} onClick={() => setStep(1)}>2. Stock and prices</Button></nav>}
        <Card><CardBody><div className="janso-flow">
          <div data-product-step={0} hidden={stockStep && step !== 0}><div className="janso-flow">
          <FieldGroup title="Product">
            {shown('kind') && <FieldPair><Select label="Type" value={kind} options={[{ value: 'GOODS', label: 'Goods' }, { value: 'SERVICE', label: 'Services' }]} disabled={locked || !writable('kind')} onChange={value => {
              setDirty(true); setKind(value as 'GOODS' | 'SERVICE'); setBatchOn(null); setBatches([]); setSerials([]); setStep(0); setValues(before => ({ ...before, base_unit_id: '', classification_id: '', rule_id: '', opening_quantity: '0', mrp: '' })); setOptions(null); setErrors({}); setFailure(null);
            }} /></FieldPair>}
            <FieldPair>{textField('name', 'Product name', true)}{textField('code', 'Product code', false, 'Optional. Leave blank to generate a unique 10-character code.')}</FieldPair>
            <FieldPair>{choice('group_id', 'item_groups', 'Product group', true)}{choice('base_unit_id', 'units', 'Base unit', true)}</FieldPair>
          </FieldGroup>
          {detailSection('brand', 'Brand', <FieldPair>{choice('brand_id', 'brands', 'Brand', true)}{values.brand_id && choice('series_id', 'brand_series', 'Brand series', false, values.brand_id)}</FieldPair>)}
          {detailSection('model', 'Model', <FieldPair>{textField('model_code', 'Model', true)}</FieldPair>)}
          {kind === 'GOODS' && detailSection('manufacturer', 'Manufacturer', <FieldPair>{choice('manufacturer_id', 'manufacturers', 'Manufacturer', true)}{values.manufacturer_id && choice('manufacturer_site_id', 'manufacturer_sites', 'Manufacturer site', false, values.manufacturer_id)}</FieldPair>)}
          {categoryMode && categoryMode !== 'DISABLED' && (categoryRequired || ['category_scheme_id', 'category_id'].some(key => field(key)?.visible)) && <FieldGroup title="Categories" hint={categoryRequired ? 'Complete the required category schemes.' : !categoryWritable ? 'Your field access does not allow these details.' : 'Choose categories within their schemes.'}
            headerEnd={<label className="janso-check"><Toggle label="Use Categories" checked={categoryEnabled} disabled={locked || categoryRequired || (!categoryWritable && !categoryEnabled)} onChange={enabled => {
              setDirty(true); setCategoryOn(enabled); setErrors({}); setFailure(null); if (enabled && !categories.length) setCategories([categoryRow()]);
            }} /><span>Use Categories</span></label>}>
            {categoryEnabled && <div className="janso-flow">{categories.map((row, index) => {
              const required = requiredSchemes.find(scheme => scheme.id === row.scheme_id);
              const update = (patch: Partial<CategoryRow>) => { setDirty(true); setErrors({}); setCategories(before => before.map(entry => entry.key === row.key ? { ...entry, ...patch } : entry)); };
              return <FieldGroup key={row.key} title={'Category ' + (index + 1)} headerEnd={<Button type="button" variant="ghost" disabled={locked || (!!required && categories.filter(entry => entry.scheme_id === row.scheme_id).length === 1)} onClick={() => { setDirty(true); setCategories(before => before.filter(entry => entry.key !== row.key)); }}>Remove category {index + 1}</Button>}>
                <FieldPair>
                  {field('category_scheme_id')?.visible && <ProductChoice company={company} field={{ ...field('category_scheme_id')!, label: 'Category scheme ' + (index + 1), required: true }} resource="category_schemes" value={row.scheme_id || null} selectedLabel={required?.name}
                    onChange={value => update({ scheme_id: value ?? '', category_id: '', is_primary: false })} disabled={locked || !!required} error={fieldError(`categories.${index}.scheme_id`)} />}
                  {field('category_id')?.visible && <ProductChoice company={company} field={{ ...field('category_id')!, label: 'Category ' + (index + 1), required: true }} resource="item_categories" value={row.category_id || null} parent={row.scheme_id}
                    onChange={value => update({ category_id: value ?? '' })} disabled={locked || !row.scheme_id} error={fieldError(`categories.${index}.category_id`)} />}
                </FieldPair>
                {field('category_is_primary')?.visible && <label className="janso-check"><Toggle label={'Primary category ' + (index + 1)} checked={row.is_primary} disabled={locked || !accessible('category_is_primary')} onChange={value => {
                  setDirty(true); setCategories(before => before.map(entry => entry.key === row.key ? { ...entry, is_primary: value } : value && entry.scheme_id === row.scheme_id ? { ...entry, is_primary: false } : entry));
                }} /><span>Primary in this scheme</span></label>}
              </FieldGroup>;
            })}<Button type="button" variant="ghost" disabled={locked || !categoryWritable || categories.length >= 128} onClick={() => { setDirty(true); setCategories(before => [...before, categoryRow()]); }}>Add category</Button></div>}
            {fieldError('categories') && <Notice tone="danger">{fieldError('categories')}</Notice>}
          </FieldGroup>}
          {detailSection('barcode', 'Barcode', <FieldPair>{textField('barcode_value', 'Barcode value', true, 'Enter or scan the barcode. Leading zeroes are preserved.')}
            {shown('barcode_symbology') && <Select label={field('barcode_symbology')?.label ?? 'Barcode format'} required value={values.barcode_symbology ?? 'CODE128'}
              options={field('barcode_symbology')?.control?.choices ?? []} disabled={locked || !writable('barcode_symbology')} error={fieldError('barcode_symbology')}
              onChange={value => change('barcode_symbology', value)} />}</FieldPair>)}
          {options.gst_enabled && <FieldGroup title="Tax"><FieldPair>{choice('classification_id', 'tax-classifications', kind === 'GOODS' ? 'HSN' : 'SAC', true)}{choice('rule_id', 'tax-rules', 'GST treatment / rate', true)}</FieldPair>{errors.tax && <Notice tone="danger">{errors.tax}</Notice>}</FieldGroup>}
          </div></div>
          <div data-product-step={1} hidden={stockStep && step !== 1}><div className="janso-flow">
          {batchAvailable && <SimpleProductBatches options={options} enabled={batchEnabled} rows={batches} locked={locked} errors={validation} onToggle={enabled => { setDirty(true); setBatchOn(enabled); setErrors({}); if (enabled && !batches.length) setBatches([batchRow()]); }} onRows={rows => { setDirty(true); setBatches(rows); setErrors({}); }} />}
          {!batchEnabled && (['purchase_price', 'sale_price', 'mrp'].some(shown) || saleLevels.some(level => shown(saleKey(level.price_level_id)))) && <FieldGroup title="Prices" hint={`Prices are per base unit in ${options.currency}.`}>
            {['purchase_price', 'sale_price', ...(saleLevels.length ? ['mrp'] : [])].some(shown) && <FieldPair>
              {textField('purchase_price', 'Purchase price', !!hasOpening || options.configuration.pricing.purchase_reference_mode === 'REQUIRED', hasOpening ? 'Required to value the opening stock entered below.' : undefined)}
              {saleLevels.length ? textField('mrp', 'MRP', options.configuration.pricing.mrp_mode === 'REQUIRED') : textField('sale_price', 'Selling price', options.configuration.pricing.sale_price_mode === 'REQUIRED')}
            </FieldPair>}
            {!saleLevels.length && shown('mrp') && <FieldPair>{textField('mrp', 'MRP', options.configuration.pricing.mrp_mode === 'REQUIRED')}</FieldPair>}
            {saleLevels.length > 0 && <FieldGroup title="Selling prices"><FieldPair>{saleLevels.map(level => textField(saleKey(level.price_level_id), level.name, level.required, level.tax_basis === 'INCLUSIVE' ? 'Including tax.' : 'Excluding tax.'))}</FieldPair></FieldGroup>}
            {validation.sale_prices && <Notice tone="danger">{validation.sale_prices}</Notice>}
          </FieldGroup>}
          {!batchEnabled && kind === 'GOODS' && options.inventory_enabled && shown('opening_quantity') && <FieldGroup title="Opening stock" hint={serialEnabled ? "Opening value is Purchase price times serial unit count." : "Opening value is Purchase price × Opening quantity. Leave quantity at zero if there is no opening stock."}><FieldPair>{serialEnabled ? <TextField label="Opening quantity" value={String(serials.length)} readOnly error={fieldError('opening_quantity')} hint="One unit per serial row." /> : textField('opening_quantity', 'Opening quantity')}<TextField label="Opening date" value={format.date(options.opening_date)} readOnly hint="Company books begin date." /></FieldPair></FieldGroup>}
          {openingBlocked && <Notice tone="warning">Opening stock needs an editable Purchase price. Set opening quantity to zero, or enable Purchase price in Product Configuration and check your field access.</Notice>}
          {!batchEnabled && serialEnabled && <SimpleProductSerials options={options} rows={serials} onRows={rows => { setDirty(true); setSerials(rows); setErrors({}); }} locked={locked} errors={validation} />}
          </div></div>
          <div data-product-step={0} hidden={stockStep && step !== 0}>
          {(customs('custom_fields.').length > 0 || customs('shared_custom_fields.').length > 0) && <FieldGroup title="Additional information"><CustomFields fields={customs('custom_fields.')} values={custom} onChange={value => { setDirty(true); setCustom(value); }} nativeValues={{ ...values, kind }} creating disabled={locked} errors={customErrors('custom_fields.')} loadOptions={customOptions} currencies={[options.currency]} /><CustomFields fields={customs('shared_custom_fields.')} values={shared} onChange={value => { setDirty(true); setShared(value); }} nativeValues={{ ...values, kind }} creating disabled={locked} errors={customErrors('shared_custom_fields.')} loadOptions={customOptions} currencies={[options.currency]} />{validation.custom_fields && <Notice tone="danger">{validation.custom_fields}</Notice>}{validation.shared_custom_fields && <Notice tone="danger">{validation.shared_custom_fields}</Notice>}</FieldGroup>}
          </div>
        </div></CardBody></Card>
        {busy && <p role="status">{job?.step === 'FINALIZE' ? 'Posting opening stock…' : 'Saving product and preparing it for use…'}</p>}
        <div className="janso-form-actions">{stockStep && step === 1 && <Button type="button" variant="ghost" disabled={locked} onClick={() => setStep(0)}>Back to product details</Button>}<Button type="submit" disabled={busy || loading || ((!job || editing) && (!!blocked || !!openingBlocked))}>{stockStep && step === 0 && !job && !intent && !recoverKey ? 'Next: Stock and prices' : busy ? 'Saving…' : editing ? 'Save corrected product' : job || intent || recoverKey ? 'Retry Save' : 'Save product'}</Button>{job?.can_edit && !busy && !editing && !recoverKey && <Button type="button" variant="ghost" onClick={() => { setEditing(true); setIntent(null); setFailure(null); }}>Correct details</Button>}{!locked && <a className="janso-btn janso-btn--ghost" href={back}>Cancel</a>}</div>
      </form>}
  </section>;
}
