'use client';

import { useEffect, useState } from 'react';
import { NotificationHistory } from './History';
import { BookIcon, Button, Checkbox, DocumentIcon, FieldGroup, FieldPair, MessageIcon, Notice, Select, TextField, Toolbar, type Column } from '@janso/ui';
import type { Activation, Binding, Job, Page, Provider, Template, TemplateDetail, UseCase, Variant, Version, VersionDetail } from '../../lib/notification-api';
import { ALL_COMPANIES, ActionBar, ChoicePages, ConfirmAction, Editor, Facts, Feedback, JobStatus, ListFilters, LocalPages, NotificationTable, References, ResourceState, StateBadge, Surface, Verbatim, channelField, defaultTime, instant, option, readable, useActions, useChoices, useListResource, useNotifications, useResource, type FormField, type FormValues } from './common';

type Variable = { name: string; type: string; required: boolean };
type Definition = { type: string; maxLength?: number };
const properties = (template: TemplateDetail): Record<string, Definition> => (template.variable_schema.properties ?? {}) as Record<string, Definition>;
export function NotificationTemplates({ route }: { route: readonly string[] }) {
  return route[1] ? <TemplateRecord route={route} /> : <TemplateDirectory />;
}
function TemplateDirectory() {
  const { href, can } = useNotifications(); const resource = useListResource('templates', ['event_key']);
  const state = useResource<Page<Template>>(resource), cases = useResource<UseCase[]>('use-cases'); const [create, setCreate] = useState(false);
  const columns: Column<Template>[] = [{ key: 'key', header: 'Template', type: 'link', href: row => href('templates/' + row.id) }, { key: 'event_key', header: 'Purpose' }, { key: 'category', header: 'Category' }, { key: 'default_locale', header: 'Default language' }, { key: 'is_active', header: 'Active', type: 'boolean' }];
  const add = can('template', 'manage') ? <Button disabled={!cases.data?.length} onClick={() => setCreate(true)}>Add template</Button> : undefined;
  return <Surface icon={<DocumentIcon />} title="Templates" subtitle="A template defines purpose and variables; each channel and language has immutable content versions." action={add}>
    <ResourceState state={cases} /><ListFilters path="templates" fields={[{ name: 'event_key', label: 'Purpose' }]} />
    <NotificationTable title="Templates" columns={columns} state={state} path="templates" noun="template"
      empty="A template is created against a registered purpose, which fixes its required variables." />
    {create && <TemplateCreator cases={cases.data ?? []} onClose={() => { setCreate(false); state.refresh(); }} />}
  </Surface>;
}
function VariableBuilder({ rows, update }: { rows: Variable[]; update: (rows: Variable[]) => void }) {
  // One row per variable, as a pair plus its own controls. The flat grid ran a name, a type, a
  // checkbox and a Remove into one undifferentiated column, so which Remove belonged to which
  // variable was a counting exercise.
  return <FieldGroup title="Template variables" hint={<>Use declared names inside double braces, for example {'{{name}}'}. Variable definitions are fixed when the template is created.</>}>
    {rows.map((row, index) => <div key={index}>
      <FieldPair>
        <TextField label={`Variable ${index + 1} name`} value={row.name} required onChange={event => update(rows.map((item, position) => position === index ? { ...item, name: event.target.value } : item))} />
        <Select label={`Variable ${index + 1} type`} value={row.type} options={['string', 'integer', 'boolean'].map(value => option(value))} onChange={value => update(rows.map((item, position) => position === index ? { ...item, type: value } : item))} />
      </FieldPair>
      <Toolbar left={<Checkbox checked={row.required} onChange={event => update(rows.map((item, position) => position === index ? { ...item, required: event.target.checked } : item))}>Required variable {index + 1}</Checkbox>}
        right={<Button variant="ghost" onClick={() => update(rows.filter((_item, position) => position !== index))}>Remove variable {index + 1}</Button>} />
    </div>)}
    <div><Button variant="ghost" disabled={rows.length >= 100} onClick={() => update([...rows, { name: '', type: 'string', required: true }])}>Add variable</Button></div>
  </FieldGroup>;
}
function TemplateCreator({ cases, onClose }: { cases: UseCase[]; onClose: () => void }) {
  const { owner, companyId } = useNotifications();
  const [variables, setVariables] = useState<Variable[]>((cases[0]?.required_variables ?? []).map(name => ({ name, type: 'string', required: true })));
  return <Editor title="Add template" initial={{ key: '', event_key: cases[0]?.key ?? '', default_locale: 'en-IN', company_id: companyId ?? ALL_COMPANIES, description: '' }} fields={[
    { name: 'key', label: 'Template key', required: true, maxLength: 80 },
    { name: 'event_key', label: 'Registered purpose', required: true, type: 'select', options: cases.map(item => option(item.key, readable(item.key))) },
    { name: 'default_locale', label: 'Default language code', required: true, maxLength: 35, help: 'For example en-IN or en.' },
    ...(owner === 'tenant' ? [{ name: 'company_id', label: 'Company scope', type: 'select' as const, required: true, options: [option(ALL_COMPANIES, 'All permitted companies'), ...(companyId ? [option(companyId, 'Current company')] : [])] }] : []),
    { name: 'description', label: 'Description', type: 'textarea', maxLength: 500 },
  ]} onChange={(values, name) => { if (name === 'event_key') setVariables((cases.find(item => item.key === values.event_key)?.required_variables ?? []).map(key => ({ name: key, type: 'string', required: true }))); return values; }} onClose={onClose} submit={async (values, action) => {
    const useCase = cases.find(item => item.key === values.event_key);
    if (!useCase || variables.some(row => !/^[a-zA-Z][a-zA-Z0-9_]*$/.test(row.name)) || new Set(variables.map(row => row.name)).size !== variables.length) throw { status: 422, message: 'Variable names must be unique and use letters, numbers and underscores, starting with a letter.' };
    if (useCase.required_variables.some(name => !variables.some(row => row.name === name && row.required))) throw { status: 422, message: 'Keep the required variables for this registered purpose.' };
    await action.send('templates', 'POST', { key: values.key, company_id: owner === 'platform' ? ALL_COMPANIES : values.company_id, event_key: useCase.key, category: useCase.category, default_locale: values.default_locale, description: values.description || null,
      variable_schema: { type: 'object', properties: Object.fromEntries(variables.map(row => [row.name, { type: row.type, ...(row.type === 'string' ? { maxLength: 10000 } : {}) }])), required: variables.filter(row => row.required).map(row => row.name), additionalProperties: false } });
  }}><VariableBuilder rows={variables} update={setVariables} /></Editor>;
}
function TemplateRecord({ route }: { route: readonly string[] }) {
  const { href, can } = useNotifications(); const identity = route[1]; const state = useResource<TemplateDetail>('templates/' + identity);
  const resource = useListResource(`templates/${identity}/variants`, []); const variants = useResource<Page<Variant>>(route[3] ? undefined : resource);
  const variant = useResource<Variant>(route[3] ? 'variants/' + route[3] : undefined);
  const [edit, setEdit] = useState(false), [createVariant, setCreateVariant] = useState(false), [toggle, setToggle] = useState(false);
  const template = state.data; const validChild = variant.data?.template_id === identity;
  const addVariant = can('template', 'manage') ? <Button disabled={!template} onClick={() => setCreateVariant(true)}>Add channel and language</Button> : undefined;
  return <><Surface icon={<DocumentIcon />} title={template?.key ?? 'Template details'} subtitle={template?.description ?? undefined}
    badge={template ? <StateBadge value={template.is_active ? 'active' : 'disabled'} /> : undefined}
    footer={template ? <a className="janso-link" href={href('assignments')}>Manage purpose assignments</a> : undefined}>
    <ResourceState state={state}>{template && <>
      <Facts items={[{ label: 'Purpose', value: readable(template.event_key) }, { label: 'Category', value: readable(template.category) },
        { label: 'Default language', value: template.default_locale },
        { label: 'Declared variables', value: Object.keys(properties(template)).length
          ? <>{Object.keys(properties(template)).map(name => <code className="janso-table__code" key={name}>{'{{' + name + '}} '}</code>)}</>
          : 'None' },
        { label: 'Company scope', value: template.company_id === ALL_COMPANIES ? 'All companies' : template.company_id }]} />
      {can('template', 'manage') && <ActionBar><Button variant="ghost" onClick={() => setEdit(true)}>Edit template details</Button>
        <Button variant={template.is_active ? 'danger' : 'ghost'} onClick={() => setToggle(true)}>{template.is_active ? 'Deactivate template' : 'Reactivate template'}</Button></ActionBar>}
      <References entries={{ Template: identity, 'Company scope': template.company_id === ALL_COMPANIES ? 'All companies' : template.company_id }} />
      {edit && <Editor title="Edit template details" initial={{ description: template.description ?? '' }} fields={[{ name: 'description', label: 'Description', type: 'textarea', maxLength: 500 }]} onClose={() => { setEdit(false); state.refresh(); }} submit={async (values, action) => { await action.send('templates/' + identity, 'PATCH', { description: values.description || null, expected_updated_at: template.updated_at }); }} />}
      {toggle && <ConfirmAction title={template.is_active ? 'Deactivate template' : 'Reactivate template'} body="This changes eligibility for new dispatches. Existing version history is retained." onDone={() => { setToggle(false); state.refresh(); }} perform={async action => { await action.send('templates/' + identity, 'PATCH', { is_active: !template.is_active, expected_updated_at: template.updated_at }); }} />}
      <NotificationHistory entity="notification_template" identity={template.id} companyId={template.company_id} />
    </>}</ResourceState></Surface>
    {!route[3] ? <Surface icon={<MessageIcon />} title="Channels and languages" subtitle="One variant per channel and language. Content versions live beneath a variant." action={addVariant}>
      <NotificationTable title="Template channels and languages" state={variants} path={`templates/${identity}`} noun="channel and language" nounPlural="channels and languages"
        empty="Add the channel and language this template should be available in." columns={[
          { key: 'channel', header: 'Channel', type: 'link', href: row => href(`templates/${identity}/variants/${row.id}`) }, { key: 'locale', header: 'Language' }, { key: 'is_active', header: 'Active', type: 'boolean' },
        ]} />
      {createVariant && <Editor title="Add channel and language" initial={{ channel: 'email', locale: template?.default_locale ?? 'en-IN' }} fields={[channelField, { name: 'locale', label: 'Language code', required: true, maxLength: 35 }]} onClose={() => { setCreateVariant(false); variants.refresh(); }} submit={async (values, action) => { await action.send(`templates/${identity}/variants`, 'POST', values); }} />}
    </Surface> : <ResourceState state={variant}>{variant.data && template && (validChild ? <VariantRecord template={template} variant={variant.data} versionId={route[5]} refreshVariant={variant.refresh} /> : <Notice tone="danger">This channel and language does not belong to the selected template.</Notice>)}</ResourceState>}
  </>;
}
function VariantRecord({ template, variant, versionId, refreshVariant }: { template: TemplateDetail; variant: Variant; versionId?: string; refreshVariant: () => void }) {
  const { href, can } = useNotifications(); const path = `templates/${template.id}/variants/${variant.id}`;
  const versions = useResource<Page<Version>>(useListResource(`variants/${variant.id}/versions`, []));
  const state = useResource<VersionDetail>(versionId ? 'template-versions/' + versionId : undefined);
  const [create, setCreate] = useState(false), [toggle, setToggle] = useState(false), [activationRevision, setActivationRevision] = useState(0);
  const validVersion = state.data?.template_variant_id === variant.id;
  const add = can('template', 'manage') ? <Button onClick={() => setCreate(true)}>Add content version</Button> : undefined;
  return <><Surface icon={<MessageIcon />} title={readable(variant.channel) + ' / ' + variant.locale} subtitle="Content is immutable. A change is a new version, activated from a chosen time."
    badge={<StateBadge value={variant.is_active ? 'active' : 'disabled'} />} action={add}
    footer={<a className="janso-link" href={href('templates/' + template.id)}>Back to template</a>}>
    <NotificationTable title="Content versions" state={versions} path={path} noun="content version"
      empty="Add the message content for this channel and language." columns={[{ key: 'version', header: 'Version', type: 'link', href: row => href(path + '/versions/' + row.id) }, { key: 'subject_text', header: 'Subject' }, { key: 'created_at', header: 'Created', type: 'datetime' }]} />
    {can('template', 'manage') && <ActionBar><Button variant="ghost" onClick={() => setToggle(true)}>{variant.is_active ? 'Deactivate channel and language' : 'Reactivate channel and language'}</Button></ActionBar>}
    {create && <VersionEditor template={template} variant={variant} onClose={() => { setCreate(false); versions.refresh(); }} />}
    {toggle && <ConfirmAction title={variant.is_active ? 'Deactivate channel and language' : 'Reactivate channel and language'} body="This changes whether new dispatches may use this channel/language variant." onDone={() => { setToggle(false); refreshVariant(); }} perform={async action => { await action.send('variants/' + variant.id, 'PATCH', { is_active: !variant.is_active }); }} />}
  </Surface>
    {versionId && <ResourceState state={state}>{state.data && (validVersion ? <VersionRecord template={template} variant={variant} version={state.data} onActivated={() => setActivationRevision(value => value + 1)} /> : <Notice tone="danger">This version does not belong to the selected channel and language.</Notice>)}</ResourceState>}
    <ActivationHistory variant={variant} revision={activationRevision} />
  </>;
}
function VersionEditor({ template, variant, onClose }: { template: TemplateDetail; variant: Variant; onClose: () => void }) {
  const names = Object.keys(properties(template));
  return <Editor title="Add content version" initial={{ subject_text: '', body_text: '', body_html: '', body_variables: '', header_variables: '', button_variable: '', button_index: '0' }} fields={[
    ...(variant.channel === 'email' ? [{ name: 'subject_text', label: 'Email subject', maxLength: 998 }, { name: 'body_html', label: 'Email HTML (optional)', type: 'textarea' as const, help: 'HTML is previewed as source and is never executed in the console.' }] : []),
    { name: 'body_text', label: 'Message text', type: 'textarea', required: true, maxLength: variant.channel === 'sms' ? 1600 : variant.channel === 'whatsapp' ? 4096 : undefined, help: 'Use declared variables: ' + (names.join(', ') || 'none') },
    ...(variant.channel === 'whatsapp' ? [
      { name: 'body_variables', label: 'Body variables in provider order', help: 'Comma-separated declared variable names matching provider positions 1, 2, and so on.' },
      { name: 'header_variables', label: 'Text header variables in provider order' },
      { name: 'button_variable', label: 'URL button variable', type: 'select' as const, options: [option('', 'No dynamic URL button'), ...names.map(name => option(name, name))] },
      { name: 'button_index', label: 'URL button index', type: 'number' as const, min: 0, max: 9 },
    ] : []),
  ]} onClose={onClose} submit={async (values, action) => {
    const ordered = (value: string) => value.split(',').map(item => item.trim()).filter(Boolean);
    const header = ordered(values.header_variables), body = ordered(values.body_variables);
    if ([...header, ...body, ...(values.button_variable ? [values.button_variable] : [])].some(name => !names.includes(name))) throw { status: 422, message: 'Provider parameters must use declared template variable names.' };
    const components = [
      ...(header.length ? [{ type: 'header', parameters: header.map(variable => ({ type: 'text', variable })) }] : []),
      ...(body.length ? [{ type: 'body', parameters: body.map(variable => ({ type: 'text', variable })) }] : []),
      ...(values.button_variable ? [{ type: 'button', sub_type: 'url', index: values.button_index, parameters: [{ type: 'text', variable: values.button_variable }] }] : []),
    ];
    await action.send(`variants/${variant.id}/versions`, 'POST', { body_text: values.body_text, subject_text: variant.channel === 'email' ? values.subject_text || null : null, body_html: variant.channel === 'email' ? values.body_html || null : null, channel_payload: variant.channel === 'whatsapp' && components.length ? { components } : null });
  }} />;
}
function VersionRecord({ template, variant, version, onActivated }: { template: TemplateDetail; variant: Variant; version: VersionDetail; onActivated: () => void }) {
  const { can } = useNotifications(); const [previewEditor, setPreviewEditor] = useState(false), [activation, setActivation] = useState(false), [bindingEditor, setBindingEditor] = useState(false);
  const [preview, setPreview] = useState<{ subject: string | null; body: string; body_html: string | null }>();
  const [job, setJob] = useState<string>(); const action = useActions();
  const bindings = useResource<Page<Binding>>(variant.channel === 'whatsapp' ? `template-versions/${version.id}/bindings?limit=50` : undefined);
  const providers = useChoices<Provider>(bindingEditor && can('provider') ? 'provider-accounts?channel=whatsapp&status=active' : undefined);
  const [bindingCursor, setBindingCursor] = useState<string | null>(null);
  const bindingPage = useResource<Page<Binding>>(bindingCursor ? `template-versions/${version.id}/bindings?limit=50&cursor=${encodeURIComponent(bindingCursor)}` : undefined);
  const currentBindings = bindingCursor ? bindingPage : bindings;
  const props = properties(template);
  const required = Array.isArray(template.variable_schema.required) ? template.variable_schema.required : [];
  return <><Surface icon={<DocumentIcon />} title={'Version ' + version.version} subtitle="Content is immutable. Create another version to change the message."
    action={<><Button variant="ghost" onClick={() => setPreviewEditor(true)}>Preview with sample variables</Button>
      {can('template', 'manage') ? <Button onClick={() => setActivation(true)}>Activate or schedule version</Button> : null}</>}>
    {version.subject_text ? <Facts items={[{ label: 'Subject', value: version.subject_text }]} /> : null}
    <Verbatim caption="Message text">{version.body_text}</Verbatim>
    {version.body_html && <Verbatim caption="Email HTML source">{version.body_html}</Verbatim>}
    {previewEditor && <Editor title="Preview template" fields={Object.entries(props).map(([name, definition]) => ({ name, label: 'Sample ' + name, type: definition.type === 'boolean' ? 'select' : definition.type === 'integer' || definition.type === 'number' ? 'number' : 'text', required: required.includes(name), options: definition.type === 'boolean' ? [...(!required.includes(name) ? [option('', 'Not supplied')] : []), option('true'), option('false')] : undefined }))} initial={Object.fromEntries(Object.keys(props).map(name => [name, props[name].type === 'boolean' && required.includes(name) ? 'true' : '']))} onClose={() => setPreviewEditor(false)} submit={async (values, command) => {
      const variables = Object.fromEntries(Object.entries(values).filter(([name, value]) => required.includes(name) || value !== '').map(([name, value]) => [name, props[name].type === 'boolean' ? value === 'true' : ['integer', 'number'].includes(props[name].type) ? Number(value) : value]));
      setPreview(await command.send(`template-versions/${version.id}/preview`, 'POST', { variables }));
    }} />}
    {/* The preview is rendered as source, never as markup: this console must be able to show a
      * template that contains a script tag without becoming the page that runs it. */}
    {preview && <section aria-label="Message preview">{preview.subject ? <Facts items={[{ label: 'Rendered subject', value: preview.subject }]} /> : null}
      <Verbatim caption="Rendered message">{preview.body}</Verbatim>
      {preview.body_html && <Verbatim caption="Rendered HTML source">{preview.body_html}</Verbatim>}</section>}
    {activation && <Editor title="Activate version" initial={{ valid_from: defaultTime(), valid_to: '', activation_reason: '' }} fields={[
      { name: 'valid_from', label: 'Active from (local time)', type: 'datetime-local', required: true }, { name: 'valid_to', label: 'Active until (optional local time)', type: 'datetime-local' }, { name: 'activation_reason', label: 'Reason for activation', maxLength: 500 },
    ]} onClose={() => setActivation(false)} submit={async (values, command) => {
      await command.send(`variants/${variant.id}/activate`, 'POST', { template_version_id: version.id, valid_from: instant(values.valid_from), valid_to: values.valid_to ? instant(values.valid_to) : null, activation_reason: values.activation_reason || null }, true);
      onActivated();
    }}><Notice tone="warning" title="This replaces the active version">From the selected time, new dispatches use this version. Selecting an older version creates a new activation; historical sends retain their original content.</Notice></Editor>}
    <References entries={{ Version: version.id }} />
  </Surface>
    {variant.channel === 'whatsapp' && <Surface icon={<MessageIcon />} title="Provider template approval" subtitle="WhatsApp content must be approved by the provider before it can be sent."
      action={can('template', 'manage') ? <Button disabled={!can('provider')} onClick={() => setBindingEditor(true)}>Connect provider template</Button> : undefined}>
      {!can('provider') && can('template', 'manage') && <Notice>Provider read access is required to choose an account for a new binding.</Notice>}
      <NotificationTable title="Provider template bindings" state={currentBindings} noun="provider binding"
        empty="Connect the provider-side template this content corresponds to." columns={[{ key: 'external_template_id', header: 'Provider template' }, { key: 'approval_status', header: 'Approval', type: 'custom', render: row => <StateBadge value={row.approval_status} /> },
          ...(can('template', 'manage') ? [{ key: 'sync', header: 'Refresh', type: 'custom' as const, render: (row: Binding) => <Button variant="ghost" disabled={action.busy} onClick={() => action.run(async () => { const result = await action.send<Job>(`bindings/${row.id}/sync`, 'POST', {}, true); setJob(result.id); }, 'Approval sync queued.')}>Sync approval</Button> }] : []),
        ]} />
      <LocalPages cursor={bindingCursor} next={currentBindings.data?.page.next_cursor} setCursor={setBindingCursor} name="binding" />
      {/* `action` is driven only by "Sync approval" in this card, so its result is stated here —
        * a 409 from the sync reported in the card above, with a table between, is a message the
        * reader has to go looking for. */}
      <Feedback action={action} />
      {bindingEditor && <Editor title="Connect provider template" initial={{ provider_account_id: '', external_template_id: '', external_name: '', external_language: variant.locale }} fields={[
        { name: 'provider_account_id', label: 'WhatsApp provider', type: 'select', required: true, options: [option('', 'Choose a provider'), ...providers.items.map(row => option(row.id, row.display_name))] },
        { name: 'external_template_id', label: 'Provider template ID', required: true }, { name: 'external_name', label: 'Provider template name', required: true }, { name: 'external_language', label: 'Provider language code', required: true },
      ]} onClose={() => { setBindingEditor(false); bindings.refresh(); }} submit={async (values, command) => { await command.send(`template-versions/${version.id}/bindings`, 'POST', { ...values, template_version_id: version.id }); }}><ChoicePages choices={providers} label="WhatsApp providers" /><Notice>Approval is confirmed by the provider and checked against this content. A local binding does not approve a template.</Notice></Editor>}
      {job && <JobStatus key={job} identity={job} onComplete={() => { bindings.refresh(); bindingPage.refresh(); }} />}
    </Surface>}
    <NotificationHistory entity="template_version" identity={version.id} companyId={template.company_id} />
  </>;
}
function ActivationHistory({ variant, revision }: { variant: Variant; revision: number }) {
  const { can } = useNotifications(); const [cursor, setCursor] = useState<string | null>(null), [end, setEnd] = useState<Activation>();
  const state = useResource<Page<Activation>>(`variants/${variant.id}/activations?limit=50` + (cursor ? '&cursor=' + encodeURIComponent(cursor) : ''));
  useEffect(() => { if (revision) state.refresh(); }, [revision]);
  return <Surface icon={<BookIcon />} title="Activation history" subtitle="Which version was live when. A send keeps the content it was given.">
    <NotificationTable title="Activations" state={state} noun="activation" empty="No version has been activated for this channel and language yet." columns={[
      { key: 'valid_from', header: 'Active from', type: 'datetime' }, { key: 'valid_to', header: 'Active until', type: 'datetime' },
      { key: 'template_version_id', header: 'Content version', type: 'code' },
      ...(can('template', 'manage') ? [{ key: 'end', header: 'End activation', type: 'custom' as const, render: (row: Activation) => <Button variant="ghost" disabled={!!row.valid_to && new Date(row.valid_to).getTime() <= Date.now()} onClick={() => setEnd(row)}>Set activation end</Button> }] : []),
    ]} />
    <LocalPages cursor={cursor} next={state.data?.page.next_cursor} setCursor={setCursor} name="activation" />
    {end && <Editor title="End activation" initial={{ valid_to: defaultTime() }} fields={[{ name: 'valid_to', label: 'End at (local time)', type: 'datetime-local', required: true }]} onClose={() => { setEnd(undefined); state.refresh(); }} submit={async (values, action) => { await action.send(`activations/${end.id}/end`, 'POST', { valid_to: instant(values.valid_to) }); }} />}
  </Surface>;
}
