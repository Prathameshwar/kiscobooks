'use client';
import { useEffect, useRef, useState } from 'react';
import { Button, Card, CardBody, ConfirmDialog, FieldGroup, FormActions, FormLayout, Notice, PageHeader, SectionHeader } from '@janso/ui';
import { masterRequest } from '../lib/catalog-master-api';
import { companyToday, configBack, configBody, configEntities, configFields, configInitial, configLink, configRecord, configRoot, useConfigCommand, useConfigDestination, type ConfigDraft, type ConfigFieldSet, type ConfigMetadata, type ConfigPage, type ConfigRevision, type ConfigScope, type ConfigSections, type ConfigValues } from '../lib/product-configuration';
import { requestFailure, type RequestFailure } from '../lib/service-call';
import { AccessFocusErrors, useAccessDraft } from './AccessCommon';
import { ConfigurationFailure, ConfigurationFields, ConfigurationLoading, ConfigurationNavigation, ConfigurationSectionNavigation } from './ProductConfigurationCommon';

const childValues = (value: ConfigDraft | ConfigRevision | null, section: ConfigSections, metadata: ConfigMetadata) => {
  if (!value) return section === 'numeric_defaults' ? [] : configInitial(metadata[section]);
  if (section === 'numeric_defaults') return value.numeric_defaults.map(row => Object.fromEntries(metadata.numeric_defaults.filter(field => field.control).map(field => [field.key, (row as ConfigValues)[field.key] ?? null])));
  return Object.fromEntries(metadata[section].filter(field => field.control).map(field => [field.key, (value[section as 'options' | 'profiles' | 'pricing'] as ConfigValues)[field.key]]));
};
const sectionDescriptions = {
  details: 'Choose when these defaults start and explain the change.',
  options: 'Disabled hides an option for new product entry. Optional lets each product choose, with a default you set below. Required must be completed before activation. Use system default inherits the native setting.',
  profiles: 'Default product types support goods and services. Add inventory, warranty, return or other profiles only when needed.',
  pricing: 'New companies start with one fixed selling price and an optional purchase reference, in the base unit and company currency. MRP and additional pricing options start disabled. The sale level count controls required price coverage; enable multiple selling-price levels to use extra levels.',
};
type Values = Record<ConfigSections, ConfigValues | ConfigValues[]>;
export function ProductConfigurationEditor({ company, scopeId, id, returnTo, timezone }: { company: string; scopeId?: string; id?: string; returnTo?: string; timezone: string }) {
  const api = `/v1/companies/${company}`, [revision, setRevision] = useState(0);
  const [metadata, setMetadata] = useState<ConfigMetadata | null>(null), [before, setBefore] = useState<ConfigDraft | null>(null), [scope, setScope] = useState<ConfigScope | null>(null), [source, setSource] = useState<ConfigRevision | null>(null);
  const [values, setValues] = useState<Values | null>(null), [loading, setLoading] = useState(true), [loadError, setLoadError] = useState<RequestFailure | null>(null), [errors, setErrors] = useState<Record<string, string>>({});
  const [discard, setDiscard] = useState(false);
  const initial = useRef(''), command = useConfigCommand(), navigation = useConfigDestination(command.pending), dirty = !navigation.destination && !!values && JSON.stringify(values) !== initial.current, guard = useAccessDraft(dirty || command.uncertain, command.pending);
  const back = configBack(returnTo, configRoot), title = id ? 'Edit company configuration draft' : 'New company configuration';
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setLoadError(null); setMetadata(null); setValues(null); setErrors({}); setBefore(null); setSource(null); setScope(null);
    async function load() {
      const keys = Object.keys(configEntities) as ConfigSections[];
      const [fields, draft] = await Promise.all([
        Promise.all(keys.map(key => masterRequest<ConfigFieldSet>({ path: api + '/entities/' + configEntities[key] + '/field-set?operation=' + (id ? 'update' : 'create'), signal: controller.signal }))),
        id ? masterRequest<ConfigDraft>({ path: api + '/product-configurations/' + id, signal: controller.signal }) : Promise.resolve(null),
      ]);
      if (draft) configRecord(draft, company, id);
      let ownerId = draft?.scope_id ?? scopeId;
      if (draft && !ownerId) throw { status: 502, message: 'The draft company is unavailable. Return to company configuration.' };
      if (!ownerId) {
        const companies = await masterRequest<ConfigPage<ConfigScope>>({ path: api + '/product-configuration-scopes?scope_kind=COMPANY&limit=2', signal: controller.signal });
        if (!Array.isArray(companies.items) || companies.items.length > 1 || companies.page?.has_more) throw { status: 502, message: 'The company configuration could not be verified.' };
        ownerId = companies.items[0]?.id;
      }
      if (new Set(fields.map(field => field.source_version)).size !== 1) throw { status: 409, message: 'Field settings changed while loading. Reload the editor.' };
      if (fields.some(field => field.configuration_complete !== true)) throw { status: 403, message: 'Some configuration fields are protected. Complete read access is required to edit or copy this aggregate.' };
      const resolved = Object.fromEntries(keys.map((key, index) => [key, configFields(fields[index]!, company, configEntities[key])])) as ConfigMetadata;
      const owner = ownerId ? configRecord(await masterRequest<ConfigScope>({ path: api + '/product-configuration-scopes/' + ownerId, signal: controller.signal }), company, ownerId) : null;
      if (owner && (owner.scope_kind !== 'COMPANY' || owner.owner_id !== company)) throw { status: 403, message: 'Only company configuration can be edited. Retired configurations remain read-only history.' };
      let template: ConfigRevision | null = null;
      if (!draft && ownerId) {
        const revisions = await masterRequest<ConfigPage<ConfigRevision>>({ path: api + '/product-configuration-scopes/' + ownerId + '/revisions?limit=1&sort=-id', signal: controller.signal });
        if (revisions.items[0]) template = configRecord(await masterRequest<ConfigRevision>({ path: api + '/product-configuration-revisions/' + revisions.items[0].id, signal: controller.signal }), company, revisions.items[0].id);
        if (template && template.scope_id !== ownerId) throw { status: 502, message: 'The source revision does not belong to this scope.' };
      }
      const original = draft ?? template;
      if (template) {
        const cannotCopy = (['options', 'profiles', 'pricing'] as const).some(section => {
          const defaults = configInitial(resolved[section]);
          return resolved[section].some(field => field.control && (!field.visible || !field.writable || field.conditional_access) && JSON.stringify((template![section] as ConfigValues)[field.key]) !== JSON.stringify(defaults[field.key]));
        }) || template.numeric_defaults.length > 0 && resolved.numeric_defaults.some(field => field.control && (!field.visible || !field.writable || field.conditional_access));
        if (cannotCopy) throw { status: 403, message: 'Published settings cannot be copied completely with the current field access. Ask an administrator to create this draft.' };
      }
      let date = companyToday(timezone);
      if (template?.effective_from && template.effective_from >= date) {
        const next = new Date(template.effective_from + 'T00:00:00Z'); next.setUTCDate(next.getUTCDate() + 1); date = next.getUTCFullYear() > 9999 ? '' : next.toISOString().slice(0, 10);
      }
      const current: Values = { details: { effective_from: draft?.effective_from ?? date, change_reason: draft?.change_reason ?? '' }, options: childValues(original, 'options', resolved), profiles: childValues(original, 'profiles', resolved), pricing: childValues(original, 'pricing', resolved), numeric_defaults: childValues(original, 'numeric_defaults', resolved) };
      if (original && keys.some(key => key !== 'details' && resolved[key].some(field => field.control && (key === 'numeric_defaults' ? original.numeric_defaults.some(row => !(field.key in row)) : !(field.key in original[key]))))) throw { status: 403, message: 'Some source settings are protected. Ask an administrator to edit or copy this complete configuration.' };
      if (controller.signal.aborted) return;
      setMetadata(resolved); setBefore(draft); setScope(owner); setSource(template); setValues(current); initial.current = JSON.stringify(current); setLoading(false);
    }
    void load().catch(error => { if (!controller.signal.aborted) { setLoadError(requestFailure(error, 'configuration editor')); setLoading(false); } });
    return () => controller.abort();
  }, [api, company, id, scopeId, revision, timezone]);
  const immutable = before?.status === 'PUBLISHED', disabled = command.blocked || !!immutable;
  const numericWritable = !!metadata?.numeric_defaults.filter(field => field.control).every(field => field.visible && field.writable && !field.conditional_access);
  function update(section: ConfigSections, next: ConfigValues | ConfigValues[]) { if (disabled || !values) return; setValues({ ...values, [section]: next }); setErrors({}); }
  function reload() { command.clear(); setRevision(value => value + 1); }
  async function save(event: React.FormEvent) {
    event.preventDefault(); if (!metadata || !values || immutable || command.pending) return;
    const result = configBody(metadata, values, before ?? undefined); setErrors(result.errors);
    if (Object.keys(result.errors).length) return;
    if (command.blocked && !command.uncertain) return;
    const saved = await command.execute<ConfigDraft>({ path: api + '/product-configurations/' + (id ?? 'company'), method: id ? 'PATCH' : 'POST', body: result.body }, value => { configRecord(value, company, id); if (!value.scope_id || !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value.scope_id) || scope && value.scope_id !== scope.id || value.status !== 'DRAFT' || !Number.isSafeInteger(value.row_version)) throw { status: 502, message: 'The saved draft response could not be verified.' }; });
    if (saved) { initial.current = JSON.stringify(values); navigation.setDestination(configLink(configRoot + '/drafts/' + saved.id, back)); }
    else if (command.failure?.fields) setErrors(command.failure.fields);
  }
  return <div className="janso-page"><ConfigurationNavigation title={title} back={back} onLeave={guard.leave} /><PageHeader title={title} lede="Save a draft first. Preview the complete effect before publishing future product defaults." />
    <ConfigurationFailure failure={loadError} retry={reload} onLeave={guard.leave} />{loading ? <ConfigurationLoading /> : metadata && values && <>
      <Notice>Applies to this company. Review and publish the saved draft to update future product defaults.</Notice>
      {immutable && <Notice>Published drafts are immutable. Return to the scope and create a new draft for a later date.</Notice>}
      {source && <Notice>Starts from revision {source.revision}. Existing settings are copied into this draft; enter a new change reason. Nothing is published by saving.</Notice>}
      <FormLayout aside={<><SectionHeader title="Before you save" /><p className="janso-fine">Save a draft to review changes before publication. Saving does not change the product settings currently in use.</p><p className="janso-fine">Published history remains fixed. Create a new draft for a later effective date.</p></>}><form aria-label="Product configuration draft" onSubmit={event => void save(event)} noValidate><Card><CardBody><div className="janso-flow"><AccessFocusErrors fields={{ ...command.failure?.fields, ...errors }} /><ConfigurationFailure failure={command.failure} write onLeave={guard.leave} />
        {command.uncertain && <Notice tone="warning">Your exact request is retained. Retry the same save to recover its result. Editing is disabled until it is resolved.</Notice>}
        <ConfigurationSectionNavigation conversion={metadata.options.some(field => field.visible && field.display_group === 'unit_conversion')} />
        {(['details', 'options', 'profiles', 'pricing'] as const).map(section => <section key={section} id={'configuration-' + section} tabIndex={-1} className="janso-flow janso-config-section" aria-label={{ details: 'Draft details', options: 'Entry options', profiles: 'Profile defaults', pricing: 'Pricing requirements' }[section]}>
          <SectionHeader title={{ details: 'Draft details', options: 'Entry options', profiles: 'Profile defaults', pricing: 'Pricing requirements' }[section]} description={sectionDescriptions[section]} />
          <ConfigurationFields company={company} fields={metadata[section].filter(field => section === 'pricing' ? field.display_group !== 'pricing_options' : section !== 'options' || field.display_group !== 'unit_conversion')} values={values[section] as ConfigValues} setValues={next => update(section, next)} disabled={disabled} errors={{ ...command.failure?.fields, ...errors }} prefix={section === 'details' ? '' : section + '.'} />
          {section === 'options' && metadata.options.some(field => field.visible && field.display_group === 'unit_conversion') && <section id="configuration-unit-conversion" tabIndex={-1} className="janso-config-section" aria-label="Unit conversion"><FieldGroup title="Unit conversion" hint="Keep all three disabled for simple base-unit quantities. Enable only the conversion or quantity entry your business uses. Separate prices for units are controlled under pricing.">
            <ConfigurationFields company={company} fields={metadata.options.filter(field => field.display_group === 'unit_conversion')} values={values.options as ConfigValues} setValues={next => update('options', next)} disabled={disabled} errors={{ ...command.failure?.fields, ...errors }} prefix="options." />
          </FieldGroup></section>}
          {section === 'pricing' && metadata.pricing.some(field => field.visible && field.display_group === 'pricing_options') && <FieldGroup title="Additional pricing options" hint="Enabled permits an option; it does not require a price. Use system default preserves the existing platform behavior. Multiple levels and additional currencies also require the corresponding company capability.">
            <ConfigurationFields company={company} fields={metadata.pricing.filter(field => field.display_group === 'pricing_options')} values={values.pricing as ConfigValues} setValues={next => update('pricing', next)} disabled={disabled} errors={{ ...command.failure?.fields, ...errors }} prefix="pricing." />
          </FieldGroup>}
        </section>)}
        <section id="configuration-numeric" tabIndex={-1} className="janso-flow janso-config-section" aria-label="Numeric defaults"><SectionHeader title="Numeric defaults" description="Quantity rules follow the selected unit dimension. Price entry precision is separate from company display precision." />
          {!numericWritable && <Notice>Numeric defaults are read-only because a field in this collection is hidden or protected. Complete field access is required to replace dimension defaults.</Notice>}
          {(values.numeric_defaults as ConfigValues[]).map((row, index) => <FieldGroup key={index} title={'Dimension defaults ' + (index + 1)}><ConfigurationFields company={company} fields={metadata.numeric_defaults} values={row} setValues={next => update('numeric_defaults', (values.numeric_defaults as ConfigValues[]).map((value, position) => position === index ? next : value))} disabled={disabled || !numericWritable} errors={{ ...command.failure?.fields, ...errors }} prefix={'numeric_defaults.' + index + '.'} />{errors['numeric_defaults.' + index] && <Notice tone="danger">{errors['numeric_defaults.' + index]}</Notice>}<Button type="button" variant="ghost" disabled={disabled || !numericWritable} onClick={() => update('numeric_defaults', (values.numeric_defaults as ConfigValues[]).filter((_value, position) => position !== index))}>Remove dimension {index + 1}</Button></FieldGroup>)}
          {!((values.numeric_defaults as ConfigValues[]).length) && <p>No dimension defaults are set. Native/unit defaults are inherited.</p>}
          <Button type="button" disabled={disabled || !numericWritable || (values.numeric_defaults as ConfigValues[]).length >= 7} onClick={() => { const row = configInitial(metadata.numeric_defaults), used = new Set((values.numeric_defaults as ConfigValues[]).map(value => value.dimension)); row.dimension = metadata.numeric_defaults.find(field => field.key === 'dimension')?.control?.choices.find(choice => !used.has(choice.value))?.value ?? ''; update('numeric_defaults', [...values.numeric_defaults as ConfigValues[], row]); }}>Add dimension defaults</Button>
        </section>
        <Notice>Numeric values are stored as exact decimals. Saving defaults does not round saved quantities or prices, change active product settings, or publish a revision.</Notice>
        {command.failure?.status === 409 || command.failure?.status === 403 ? <Button type="button" onClick={() => setDiscard(true)}>Reload and review</Button> : null}
        {errors.version && <Notice tone="danger">{errors.version}</Notice>}
        </div></CardBody><FormActions cancel={{ href: back, onClick: guard.leave }}><Button type="submit" loading={command.pending} disabled={immutable || command.blocked && !command.uncertain || !!before && !dirty && !command.uncertain}>{command.uncertain ? 'Retry same draft save' : before ? 'Save draft changes' : 'Save draft'}</Button></FormActions></Card>
      </form></FormLayout>
    </>}<ConfirmDialog open={discard} title="Discard this draft's unsaved changes?" confirmLabel="Discard and reload" onCancel={() => setDiscard(false)} onConfirm={() => { setDiscard(false); reload(); }}>Reloading replaces the values in this editor with the latest saved draft.</ConfirmDialog>{guard.confirmation}</div>;
}
