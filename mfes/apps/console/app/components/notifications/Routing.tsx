'use client';
import { useState } from 'react';
import { NotificationHistory } from './History';
import { ActivityIcon, Button, HelpIcon, Notice } from '@janso/ui';
import type { EffectiveResult, Page, Provider, Route, RouteDetail, Sender, UseCase } from '../../lib/notification-api';
import { ALL_COMPANIES, ActionBar, ChoicePages, ConfirmAction, Editor, Facts, ListFilters, NotificationTable, References, ResourceState, StateBadge, Surface, channelField, numeric, option, readable, useChoices, useListResource, useNotifications, useResource, type FormField, type FormValues } from './common';

export function NotificationRouting({ identity }: { identity?: string }) {
  const { can, href } = useNotifications();
  const listResource = useListResource('routing-rules', ['channel', 'event_key', 'sort']);
  const list = useResource<Page<Route>>(identity ? undefined : listResource);
  const record = useResource<RouteDetail>(identity ? 'routing-rules/' + identity : undefined);
  const [edit, setEdit] = useState(false), [toggle, setToggle] = useState(false), [inspect, setInspect] = useState(false);
  const [result, setResult] = useState<EffectiveResult>();
  const row = record.data;
  const provider = useResource<Provider>(row && can('provider') ? 'provider-accounts/' + row.provider_account_id : undefined);
  const sender = useResource<Sender>(row && can('provider') ? 'sender-identities/' + row.sender_identity_id : undefined);
  const manage = can('route', 'manage') ? <Button disabled={!!identity && !row} onClick={() => setEdit(true)}>{identity ? 'Edit route' : 'Add route'}</Button> : undefined;
  return <><Surface icon={<ActivityIcon />} title={row ? 'Route for ' + readable(row.event_key) : 'Delivery routes'}
    subtitle="Routes choose a verified transport and sender. Template assignment determines the content."
    badge={row ? <StateBadge value={row.is_active ? 'active' : 'disabled'} /> : undefined} action={manage}>
    {!identity && <ListFilters path="routing" fields={[{ name: 'channel', label: 'Channel', values: ['email', 'sms', 'whatsapp'] }, { name: 'event_key', label: 'Purpose key' }, { name: 'sort', label: 'Sort', values: ['-created_at', 'created_at', 'priority', '-priority'] }]} />}
    {!identity ? <NotificationTable title="Delivery routes" state={list} path="routing" noun="delivery route"
      empty="A route binds a purpose and channel to an active provider and a verified sender." columns={[
        { key: 'event_key', header: 'Purpose', type: 'link', href: item => href('routing/' + item.id) }, { key: 'channel', header: 'Channel' }, { key: 'category', header: 'Category' }, { key: 'priority', header: 'Priority' }, { key: 'weight', header: 'Weight' }, { key: 'is_active', header: 'Active', type: 'boolean' },
      ]} /> : <ResourceState state={record}>{row && <>
        {can('provider') && <><ResourceState state={provider} /><ResourceState state={sender} /></>}
        <Facts items={[{ label: 'Channel', value: readable(row.channel) }, { label: 'Category', value: readable(row.category) },
          ...(can('provider') ? [
            { label: 'Provider', value: <a className="janso-link" href={href('providers/' + row.provider_account_id)}>{provider.data?.display_name ?? 'View provider'}</a> },
            { label: 'Sender', value: <a className="janso-link" href={href(`providers/${row.provider_account_id}/senders/${row.sender_identity_id}`)}>{sender.data?.display_name ?? 'View sender'}</a> },
          ] : []),
          { label: 'Priority / weight', value: row.priority + ' / ' + row.weight },
          { label: 'Maximum attempts', value: String(row.max_attempts) },
          { label: 'Provider timeout', value: row.timeout_seconds + ' seconds' },
          { label: 'Backoff', value: row.initial_backoff_seconds + ' to ' + row.max_backoff_seconds + ' seconds' },
        ]} />
        {can('route', 'manage') && <ActionBar><Button variant={row.is_active ? 'danger' : 'ghost'} onClick={() => setToggle(true)}>{row.is_active ? 'Deactivate route' : 'Reactivate route'}</Button></ActionBar>}
        <References entries={{ Route: row.id, Provider: row.provider_account_id, Sender: row.sender_identity_id, 'Company scope': row.company_id }} />
        <NotificationHistory entity="routing_rule" identity={row.id} companyId={row.company_id} />
      </>}</ResourceState>}
    {edit && <RouteEditor route={row} onClose={() => { setEdit(false); list.refresh(); record.refresh(); }} />}
    {toggle && row && <ConfirmAction title={row.is_active ? 'Deactivate route' : 'Reactivate route'} body="This changes whether new dispatches may use this route. Retained delivery evidence is preserved." onDone={() => { setToggle(false); record.refresh(); }} perform={async action => { await action.send('routing-rules/' + row.id, 'PATCH', { is_active: !row.is_active, expected_updated_at: row.updated_at }); }} />}
  </Surface>
    <Surface icon={<HelpIcon />} title="Check effective policy" subtitle="Inspect server-selected content and routing without sending a message."
      badge={result ? <StateBadge value={result.ready ? 'ready' : 'pending'} /> : undefined}
      action={can('template') ? <Button variant="ghost" onClick={() => setInspect(true)}>Check policy</Button> : undefined}
      footer={<span>Policy readiness is not evidence that a recipient has received a message.</span>}>
      {!can('template') ? <Notice>Template read access is also required to inspect effective policy.</Notice> : null}
      {inspect && <PolicyEditor onClose={() => setInspect(false)} onResult={setResult} />}
      {result && <section aria-label="Effective policy result">
        {result.reasons.length ? <Notice tone={result.ready ? 'info' : 'warning'} title={result.ready ? 'Selected by the server' : 'Nothing would be sent'}>
          <ul>{result.reasons.map(reason => <li key={reason}>{readable(reason)}</li>)}</ul></Notice> : null}
        {result.route_id && <a className="janso-link" href={href('routing/' + result.route_id)}>Open selected route</a>}
        <References entries={{ 'Selected template version': result.template_version_id, 'Selected route': result.route_id }} />
      </section>}
    </Surface>
  </>;
}
function RouteEditor({ route, onClose }: { route?: RouteDetail; onClose: () => void }) {
  const { owner, companyId, can } = useNotifications();
  const [providerId, setProviderId] = useState('');
  const providers = useChoices<Provider>(!route && can('provider') ? 'provider-accounts?status=active' : undefined);
  const senders = useChoices<Sender>(!route && can('provider') && providerId ? 'sender-identities?provider_account_id=' + providerId : undefined);
  const cases = useResource<UseCase[]>(!route && can('template') ? 'use-cases' : undefined);
  const initial: FormValues = { event_key: route?.event_key ?? '', category: route?.category ?? 'transactional', channel: route?.channel ?? 'email', provider_account_id: route?.provider_account_id ?? '', sender_identity_id: route?.sender_identity_id ?? '', company_id: route?.company_id ?? companyId ?? ALL_COMPANIES,
    priority: String(route?.priority ?? 0), weight: String(route?.weight ?? 1), max_attempts: String(route?.max_attempts ?? 3), timeout_seconds: String(route?.timeout_seconds ?? 20), initial_backoff_seconds: String(route?.initial_backoff_seconds ?? 5), max_backoff_seconds: String(route?.max_backoff_seconds ?? 300) };
  const numberFields: FormField[] = [
    { name: 'priority', label: 'Priority', type: 'number', required: true, min: 0, max: 32767, help: 'Lower values are considered first.' },
    { name: 'weight', label: 'Weight', type: 'number', required: true, min: 1, max: 32767 },
    { name: 'max_attempts', label: 'Maximum attempts per retry cycle', type: 'number', required: true, min: 1, max: 100 },
    { name: 'timeout_seconds', label: 'Provider timeout (seconds)', type: 'number', required: true, min: 1, max: 3600 },
    { name: 'initial_backoff_seconds', label: 'Initial backoff (seconds)', type: 'number', required: true, min: 1, max: 86400 },
    { name: 'max_backoff_seconds', label: 'Maximum backoff (seconds)', type: 'number', required: true, min: 1, max: 604800 },
  ];
  return <Editor title={route ? 'Edit route' : 'Add route'} initial={initial} fields={values => [
    ...(!route ? [
      cases.data ? { name: 'event_key', label: 'Registered purpose', type: 'select' as const, required: true, options: [option('', 'Choose a purpose'), ...cases.data.map(item => option(item.key, readable(item.key)))] } : { name: 'event_key', label: 'Purpose key', required: true },
      { name: 'category', label: 'Category', type: 'select' as const, required: true, options: ['security', 'transactional', 'operational', 'marketing'].map(value => option(value)) }, channelField,
      { name: 'provider_account_id', label: 'Provider account', type: 'select' as const, required: true, options: [option('', 'Choose an active provider'), ...providers.items.filter(item => item.channel === values.channel && item.status === 'active').map(item => option(item.id, item.display_name))] },
      { name: 'sender_identity_id', label: 'Sender identity', type: 'select' as const, required: true, options: [option('', 'Choose a verified sender'), ...senders.items.filter(item => item.provider_account_id === values.provider_account_id && item.is_active && item.verification_status === 'verified').map(item => option(item.id, item.display_name))] },
      ...(owner === 'tenant' ? [{ name: 'company_id', label: 'Company scope', type: 'select' as const, required: true, options: [option(ALL_COMPANIES, 'All permitted companies'), ...(companyId ? [option(companyId, 'Current company')] : [])] }] : []),
    ] : []), ...numberFields,
  ]} onChange={(values, name) => {
    if (name === 'channel') { setProviderId(''); return { ...values, provider_account_id: '', sender_identity_id: '' }; }
    if (name === 'provider_account_id') { setProviderId(values.provider_account_id); return { ...values, sender_identity_id: '' }; }
    if (name === 'event_key') return { ...values, category: cases.data?.find(item => item.key === values.event_key)?.category ?? values.category };
    return values;
  }} onClose={onClose} submit={async (values, action) => {
    const parameters = { priority: numeric(values.priority, 'Priority', 0, 32767), weight: numeric(values.weight, 'Weight', 1, 32767), max_attempts: numeric(values.max_attempts, 'Maximum attempts', 1, 100), timeout_seconds: numeric(values.timeout_seconds, 'Timeout', 1, 3600), initial_backoff_seconds: numeric(values.initial_backoff_seconds, 'Initial backoff', 1, 86400), max_backoff_seconds: numeric(values.max_backoff_seconds, 'Maximum backoff', 1, 604800) };
    if (parameters.max_backoff_seconds < parameters.initial_backoff_seconds) throw { status: 422, message: 'Maximum backoff cannot be shorter than initial backoff.' };
    if (route) await action.send('routing-rules/' + route.id, 'PATCH', { ...parameters, expected_updated_at: route.updated_at });
    else await action.send('routing-rules', 'POST', { ...parameters, company_id: owner === 'platform' ? ALL_COMPANIES : values.company_id, event_key: values.event_key, category: values.category, channel: values.channel, provider_account_id: values.provider_account_id, sender_identity_id: values.sender_identity_id }, true);
  }}>{!route && <><ChoicePages choices={providers} label="providers" /><ChoicePages choices={senders} label="senders" /><ResourceState state={cases} />{!can('provider') && <Notice>Provider read access is required to choose a provider and sender for a new route.</Notice>}</>}</Editor>;
}
function PolicyEditor({ onClose, onResult }: { onClose: () => void; onResult: (result: EffectiveResult) => void }) {
  const { owner, companyId } = useNotifications(); const cases = useResource<UseCase[]>('use-cases');
  return <Editor title="Check effective policy" initial={{ event_key: '', trigger_key: '', channel: 'email', locale: '', company_id: companyId ?? ALL_COMPANIES }} fields={values => {
    const useCase = cases.data?.find(item => item.key === values.event_key);
    return [{ name: 'event_key', label: 'Registered purpose', type: 'select', required: true, options: [option('', 'Choose a purpose'), ...(cases.data ?? []).map(item => option(item.key, readable(item.key)))] },
      { name: 'trigger_key', label: 'Source trigger', type: 'select', required: true, options: (useCase?.triggers ?? []).map(value => option(value, readable(value))) },
      { ...channelField, options: (useCase?.channels ?? ['email', 'sms', 'whatsapp']).map(value => option(value)) },
      { name: 'locale', label: 'Requested language (optional)' },
      ...(owner === 'tenant' ? [{ name: 'company_id', label: 'Company scope', type: 'select' as const, required: true, options: [option(ALL_COMPANIES, 'All permitted companies'), ...(companyId ? [option(companyId, 'Current company')] : [])] }] : [])];
  }} onChange={(values, name) => name === 'event_key' ? { ...values, trigger_key: cases.data?.find(item => item.key === values.event_key)?.triggers[0] ?? '', channel: cases.data?.find(item => item.key === values.event_key)?.channels[0] ?? 'email' } : values} onClose={onClose} submit={async (values, action) => { onResult(await action.send('effective-policy', 'POST', { ...values, company_id: owner === 'platform' ? ALL_COMPANIES : values.company_id, locale: values.locale || null })); }}><ResourceState state={cases} /></Editor>;
}
