'use client';

import { useState } from 'react';
import { NotificationHistory } from './History';
import { Button, CopyIcon, MailIcon, MessageIcon, Notice, ShieldIcon, UserIcon, type Column } from '@janso/ui';
import type { CallbackConfiguration, Job, Page, Provider, ProviderDetail, Sender } from '../../lib/notification-api';
import { ActionBar, ConfirmAction, Editor, Facts, Feedback, JobStatus, ListFilters, NotificationTable, References, ResourceState, StateBadge, Surface, option, readable, useActions, useListResource, useNotifications, useResource, type FormField, type FormValues } from './common';

const CHANNEL_ICON = (channel?: string) => channel === 'sms' || channel === 'whatsapp' ? <MessageIcon /> : <MailIcon />;

export function NotificationProviders({ route }: { route: readonly string[] }) {
  return route[1] ? route[2] === 'senders' ? <SenderManagement providerId={route[1]} senderId={route[3]} /> : <ProviderRecord identity={route[1]} /> : <ProviderDirectory />;
}
function ProviderDirectory() {
  const { can, href } = useNotifications(); const resource = useListResource('provider-accounts', ['channel', 'status', 'q', 'sort']);
  const state = useResource<Page<Provider>>(resource), [create, setCreate] = useState(false);
  const columns: Column<Provider>[] = [
    { key: 'display_name', header: 'Provider account', type: 'link', href: row => href('providers/' + row.id) },
    { key: 'channel', header: 'Channel' }, { key: 'provider_key', header: 'Provider' },
    { key: 'status', header: 'Status', type: 'custom', render: row => <StateBadge value={row.status} /> },
    { key: 'region', header: 'Region' }, { key: 'updated_at', header: 'Updated', type: 'datetime' },
  ];
  return <Surface icon={<ShieldIcon />} title="Provider accounts" subtitle="Choose a registered credential binding, validate the account, then verify its senders." action={can('provider', 'manage') && <Button onClick={() => setCreate(true)}>Add provider</Button>}>
    <ListFilters path="providers" fields={[{ name: 'channel', label: 'Channel', values: ['email', 'sms', 'whatsapp'] }, { name: 'status', label: 'Status', values: ['pending', 'active', 'disabled'] }, { name: 'q', label: 'Name or key prefix' }, { name: 'sort', label: 'Sort', values: ['-updated_at', 'updated_at', 'display_name', '-display_name'] }]} />
    <NotificationTable title="Provider accounts" columns={columns} state={state} path="providers" noun="provider account"
      empty="A provider account binds a registered credential to one channel. Credential values stay outside the console." />
    {create && <ProviderEditor onClose={() => { setCreate(false); state.refresh(); }} />}
  </Surface>;
}
function ProviderEditor({ provider, onClose }: { provider?: ProviderDetail; onClose: () => void }) {
  const refs = useResource<string[]>('credential-bindings');
  const initial: FormValues = provider ? { display_name: provider.display_name, credential_ref: provider.credential_ref, callback_secret_ref: provider.callback_secret_ref ?? '', region: provider.region ?? '',
    provider_key: provider.provider_key, sns_topic_arn: String(provider.capabilities?.sns_topic_arn ?? ''), verification_token_ref: String(provider.capabilities?.verification_token_ref ?? '') }
    : { key: '', display_name: '', provider_key: 'ses', credential_ref: '', callback_secret_ref: '', region: '', sns_topic_arn: '', verification_token_ref: '', callback_key: crypto.randomUUID().replaceAll('-', '') };
  const refOptions = [option('', 'Choose a registered binding'), ...(refs.data ?? []).map(ref => option(ref, ref))];
  const fields = (values: FormValues): FormField[] => [
    ...(!provider ? [{ name: 'key', label: 'Account key', required: true, maxLength: 80 }, { name: 'provider_key', label: 'Provider', required: true, type: 'select' as const, options: [option('ses', 'Amazon SES (Email)'), option('twilio', 'Twilio (SMS)'), option('meta', 'Meta (WhatsApp)')] }] : []),
    { name: 'display_name', label: 'Account name', required: true, maxLength: 150 },
    { name: 'credential_ref', label: 'Credential binding', type: 'select', required: true, options: refOptions, help: 'Bindings are registered for this owner. Credential values stay outside the console.' },
    ...(['twilio', 'meta'].includes(values.provider_key) ? [{ name: 'callback_secret_ref', label: 'Callback signature binding', type: 'select' as const, required: true, options: refOptions }] : []),
    ...(values.provider_key === 'ses' ? [{ name: 'region', label: 'AWS region', required: true, maxLength: 40 }, { name: 'sns_topic_arn', label: 'SES receipt SNS topic ARN', maxLength: 255, help: 'The topic must be registered for this owner by the operator.' }] : []),
    ...(values.provider_key === 'meta' ? [{ name: 'verification_token_ref', label: 'WhatsApp verification-token binding', type: 'select' as const, options: refOptions, required: true }] : []),
  ];
  return <Editor title={provider ? 'Edit provider' : 'Add provider'} initial={initial} fields={fields} onClose={onClose} submit={async (values, action) => {
    if (!refs.data?.includes(values.credential_ref)) throw { status: 422, message: 'Choose an available registered credential binding.' };
    const body = { display_name: values.display_name.trim(), credential_ref: values.credential_ref,
      callback_secret_ref: ['twilio', 'meta'].includes(values.provider_key) ? values.callback_secret_ref : null,
      region: values.provider_key === 'ses' ? values.region : null,
      capabilities: { sns_topic_arn: values.provider_key === 'ses' ? values.sns_topic_arn || null : null, verification_token_ref: values.provider_key === 'meta' ? values.verification_token_ref : null } };
    if (provider) await action.send('provider-accounts/' + provider.id, 'PATCH', { ...body, expected_updated_at: provider.updated_at });
    else await action.send('provider-accounts', 'POST', { ...body, key: values.key, callback_key: values.callback_key, provider_key: values.provider_key, channel: ({ ses: 'email', twilio: 'sms', meta: 'whatsapp' } as Record<string, string>)[values.provider_key] });
  }}><ResourceState state={refs} />{refs.data?.length === 0 && <Notice tone="warning" title="No credential bindings are registered">An operator must configure a binding for this owner before this account can be saved.</Notice>}
    {provider && <Notice tone="warning" title="This resets verification">Changing credentials or region resets account and sender verification. Validate the account and reverify senders afterward.</Notice>}
  </Editor>;
}
function ProviderRecord({ identity }: { identity: string }) {
  const { can, href } = useNotifications(); const state = useResource<ProviderDetail>('provider-accounts/' + identity);
  const callback = useResource<CallbackConfiguration>('provider-accounts/' + identity + '/callback-configuration');
  const [edit, setEdit] = useState(false), [toggle, setToggle] = useState(false), [job, setJob] = useState<string>(); const action = useActions(); const copyAction = useActions(); const provider = state.data;
  return <><Surface icon={CHANNEL_ICON(provider?.channel)} title={provider?.display_name ?? 'Provider details'} subtitle={provider ? readable(provider.channel) + ' transport through ' + provider.provider_key : undefined}
    badge={provider ? <StateBadge value={provider.status} /> : undefined}
    footer={provider ? <a className="janso-link" href={href(`providers/${identity}/senders`)}>Manage sender identities</a> : undefined}>
    <ResourceState state={state}>{provider && <>
      <Facts items={[{ label: 'Channel', value: readable(provider.channel) }, { label: 'Provider', value: provider.provider_key },
        { label: 'Region', value: provider.region ?? 'No region required' },
        { label: 'Status', value: <StateBadge value={provider.status} /> },
        { label: 'Credential binding', value: <code className="janso-table__code">{provider.credential_ref}</code> }]} />
      {can('provider', 'manage') && <ActionBar>
        <Button disabled={action.busy} onClick={() => action.run(async () => { const result = await action.send<Job>(`provider-accounts/${identity}/validate`, 'POST', {}, true); setJob(result.id); }, 'Validation queued.')}>Validate provider</Button>
        <Button variant="ghost" onClick={() => setEdit(true)}>Edit provider</Button>
        <Button variant={provider.status === 'disabled' ? 'ghost' : 'danger'} onClick={() => setToggle(true)}>{provider.status === 'disabled' ? 'Prepare for validation' : 'Disable provider'}</Button></ActionBar>}
      <Feedback action={action} />
      <References entries={{ Account: identity, 'Credential binding': provider.credential_ref }} />
      {edit && <ProviderEditor provider={provider} onClose={() => { setEdit(false); state.refresh(); callback.refresh(); }} />}
      {toggle && <ConfirmAction title={provider.status === 'disabled' ? 'Prepare provider for validation' : 'Disable provider'} body={provider.status === 'disabled' ? 'The account will remain pending until provider validation succeeds.' : 'New sends using this provider will stop. In-flight submissions cannot be recalled.'} onDone={() => { setToggle(false); state.refresh(); }} perform={async command => { await command.send('provider-accounts/' + identity, 'PATCH', { status: provider.status === 'disabled' ? 'pending' : 'disabled', expected_updated_at: provider.updated_at }); }} />}
    </>}</ResourceState></Surface>
    <Surface icon={<ShieldIcon />} title="Callback configuration" subtitle="Where this provider sends signed receipts, and how their signature is checked."
      action={callback.data?.url ? <Button variant="ghost" disabled={copyAction.busy} onClick={() => copyAction.run(async () => { if (!navigator.clipboard) throw { status: 503, message: 'Copy is unavailable in this browser. Select and copy the URL above.' }; await navigator.clipboard.writeText(callback.data!.url!); }, 'Callback URL copied.')}><CopyIcon size={14} /> Copy callback URL</Button> : undefined}>
      <Feedback action={copyAction} />
      <ResourceState state={callback}>{callback.data && <>
        <Facts items={[{ label: 'Signature scheme', value: callback.data.signature_scheme },
          { label: 'Callback URL', value: callback.data.url ? <code className="janso-table__code">{callback.data.url}</code> : 'The operator has not configured a public HTTPS callback origin.' }]} />
        <Notice>The URL is configuration information. Confirm provider registration and signed receipt delivery with a canary before activation.</Notice></>}</ResourceState></Surface>
    {job && <JobStatus key={job} identity={job} onComplete={state.refresh} />}
    {provider && <NotificationHistory entity="provider_account" identity={identity} />}
  </>;
}
function SenderManagement({ providerId, senderId }: { providerId: string; senderId?: string }) {
  const { href, can } = useNotifications(); const provider = useResource<ProviderDetail>('provider-accounts/' + providerId);
  const resource = useListResource('sender-identities', []);
  const list = useResource<Page<Sender>>(senderId ? undefined : resource + '&provider_account_id=' + providerId);
  const record = useResource<Sender>(senderId ? 'sender-identities/' + senderId : undefined);
  const [editor, setEditor] = useState(false), [toggle, setToggle] = useState(false), [job, setJob] = useState<string>(); const action = useActions();
  const row = record.data; const mismatch = row && row.provider_account_id !== providerId;
  const fields: FormField[] = [
    ...(!row ? [{ name: 'key', label: 'Sender key', required: true, maxLength: 80 }, { name: 'external_sender_id', label: provider.data?.channel === 'whatsapp' ? 'WhatsApp phone number ID' : provider.data?.channel === 'sms' ? 'SMS sender number (E.164)' : 'Sender email identity', required: true, maxLength: 255 }] : []),
    { name: 'display_name', label: 'Sender name', required: true, maxLength: 150 },
  ];
  const columns: Column<Sender>[] = [{ key: 'display_name', header: 'Sender', type: 'link', href: item => href(`providers/${providerId}/senders/${item.id}`) }, { key: 'sender_type', header: 'Channel' }, { key: 'external_sender_id', header: 'Registered identity' }, { key: 'verification_status', header: 'Verification', type: 'custom', render: item => <StateBadge value={item.verification_status} /> }, { key: 'is_active', header: 'Active', type: 'boolean' }];
  const add = can('provider', 'manage') && !mismatch ? <Button disabled={!provider.data || (!!senderId && !row)} onClick={() => setEditor(true)}>{row ? 'Edit sender' : 'Add sender'}</Button> : undefined;
  return <Surface icon={<UserIcon />} title={row?.display_name ?? 'Sender identities'}
    subtitle={row ? readable(row.sender_type) + ' sender registered with this provider account' : 'Every send names a verified sender registered with this provider account.'}
    badge={row ? <><StateBadge value={row.verification_status} /> <StateBadge value={row.is_active ? 'active' : 'disabled'} /></> : undefined}
    action={add} footer={<a className="janso-link" href={href('providers/' + providerId)}>Back to provider</a>}>
    <ResourceState state={provider} />
    {!senderId ? <NotificationTable title="Sender identities" columns={columns} state={list} path={`providers/${providerId}/senders`} noun="sender identity" nounPlural="sender identities"
      empty="A sender identity is the address or number the provider has confirmed you may send from." /> : <ResourceState state={record}>
      {mismatch ? <Notice tone="danger">This sender does not belong to the selected provider.</Notice> : row && <>
        <Facts items={[{ label: 'Registered identity', value: <code className="janso-table__code">{row.external_sender_id}</code> },
          { label: 'Channel', value: readable(row.sender_type) },
          { label: 'Verification', value: <StateBadge value={row.verification_status} /> },
          { label: 'Admission', value: row.is_active && row.verification_status === 'verified' && provider.data?.status === 'active' ? 'Verified and active; routing policy still applies' : 'Not ready for routing' }]} />
        <Notice>Verification comes from the provider. Reactivating a sender requires a fresh verification check.</Notice>
        {can('provider', 'manage') && <ActionBar>
          {['verify', 'sync'].map(operation => <Button key={operation} variant={operation === 'verify' ? 'primary' : 'ghost'} disabled={action.busy} onClick={() => action.run(async () => { const result = await action.send<Job>(`sender-identities/${row.id}/${operation}`, 'POST', {}, true); setJob(result.id); }, 'Sender check queued.')}>{operation === 'verify' ? 'Verify sender' : 'Refresh verification'}</Button>)}
          <Button variant={row.is_active ? 'danger' : 'ghost'} onClick={() => setToggle(true)}>{row.is_active ? 'Deactivate sender' : 'Reactivate sender'}</Button></ActionBar>}
        <References entries={{ Sender: row.id, Provider: providerId }} />
      </>}</ResourceState>}
    <Feedback action={action} />
    {editor && !mismatch && <Editor title={row ? 'Edit sender' : 'Add sender'} fields={fields} initial={row ? { display_name: row.display_name } : { key: '', display_name: '', external_sender_id: '' }} onClose={() => { setEditor(false); list.refresh(); record.refresh(); }} submit={async (values, command) => {
      if (row) await command.send('sender-identities/' + row.id, 'PATCH', { display_name: values.display_name, expected_updated_at: row.updated_at });
      else await command.send('sender-identities', 'POST', { ...values, provider_account_id: providerId, sender_type: provider.data!.channel });
    }} />}
    {toggle && row && <ConfirmAction title={row.is_active ? 'Deactivate sender' : 'Reactivate sender'} body={row.is_active ? 'New sends will no longer use this sender.' : 'This sender will become unverified until the provider confirms its identity again.'} onDone={() => { setToggle(false); record.refresh(); }} perform={async command => { await command.send('sender-identities/' + row.id, 'PATCH', { is_active: !row.is_active, expected_updated_at: row.updated_at }); }} />}
    {job && <JobStatus key={job} identity={job} onComplete={record.refresh} />}
    {row && !mismatch && <NotificationHistory entity="sender_identity" identity={row.id} />}
  </Surface>;
}
