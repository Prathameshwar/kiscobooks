'use client';
import { useState } from 'react';
import { NotificationHistory } from './History';
import { Button, CheckCircleIcon, CustomersIcon, EmptyState, Notice, SearchIcon, XCircleIcon } from '@janso/ui';
import type { Consent, Endpoint, Page, Suppression } from '../../lib/notification-api';
import { isNotificationId } from '../../lib/notification-navigation';
import { ConfirmAction, Editor, Facts, ListFilters, NotificationTable, ResourceState, StateBadge, Surface, channelField, defaultTime, instant, option, readable, useListResource, useNotifications, useResource } from './common';

export function NotificationRecipients() {
  const { query, can, href } = useNotifications(); const subject = query.get('subject_id'), endpoint = query.get('recipient_endpoint_id');
  const validSubject = !!subject && isNotificationId(subject), validEndpoint = !!endpoint && isNotificationId(endpoint);
  const listPath = useListResource('recipient-endpoints', ['subject_id']);
  const state = useResource<Page<Endpoint> | Endpoint>(validEndpoint ? 'recipient-endpoints/' + endpoint : validSubject ? listPath : undefined);
  const [history, setHistory] = useState<Endpoint>();
  const normalized = state.data && ('items' in state.data ? state.data : { items: [state.data], page: { next_cursor: null, has_more: false } });
  return <><Surface icon={<CustomersIcon />} title="Recipient endpoints" subtitle="Look up a source-issued subject reference, or open a masked endpoint from delivery history."
    footer={<span>Addresses are held by the source record. Nothing on this screen creates or changes one.</span>}>
    <ListFilters path="recipients" fields={[{ name: 'subject_id', label: 'Subject reference (UUID)' }]} />
    {/* A lookup screen with nothing looked up yet is empty, not broken — an empty state says what
      * to type; a danger notice said the reader had done something wrong by arriving. */}
    {!validSubject && !validEndpoint ? <EmptyState icon={<SearchIcon />}
      title={subject || endpoint ? 'Enter a valid source-issued UUID reference.' : 'Search for a recipient endpoint'}
      body={subject || endpoint ? 'The reference must be a UUID issued by the source record.' : 'Recipients come from authorized source records. This view does not create or change their addresses.'} />
      : <NotificationTable title="Recipient endpoints" state={{ ...state, data: normalized }} path={validEndpoint ? undefined : 'recipients'} noun="recipient endpoint"
        empty="No endpoint is registered for that reference in this scope." filtered columns={[
          // Plain text, not `masked`: the service already redacts this value, and that cell type
          // would prepend a second mask to an address that is already partly starred out.
          { key: 'destination_masked', header: 'Destination' }, { key: 'subject_type', header: 'Source recipient type' }, { key: 'channel', header: 'Channel' },
          { key: 'verification_status', header: 'Verification', type: 'custom', render: row => <StateBadge value={row.verification_status} /> },
          { key: 'health_status', header: 'Health', type: 'custom', render: row => <StateBadge value={row.health_status} /> }, { key: 'is_active', header: 'Active', type: 'boolean' },
          { key: 'history', header: 'History', type: 'custom', render: row => <Button variant="ghost" onClick={() => setHistory(row)}>Recipient history</Button> },
          ...(can('consent', 'manage') ? [{ key: 'consent', header: 'Policy', type: 'custom' as const, render: (row: Endpoint) => <a className="janso-link" href={href('consent') + '?recipient_endpoint_id=' + row.id}>Manage consent</a> }] : []),
        ]} />}
  </Surface>
    {history && <NotificationHistory key={history.id} entity="recipient_endpoint" identity={history.id} companyId={history.company_id} />}
  </>;
}
export function NotificationConsent() {
  const { query, can, href } = useNotifications(); const endpointId = query.get('recipient_endpoint_id'); const valid = !!endpointId && isNotificationId(endpointId);
  const resource = useListResource('consent-states', ['recipient_endpoint_id']); const state = useResource<Page<Consent>>(valid ? resource : undefined);
  const endpoint = useResource<Endpoint>(valid && can('recipient') ? 'recipient-endpoints/' + endpointId : undefined);
  const [create, setCreate] = useState(false), [history, setHistory] = useState<Consent>();
  return <><Surface icon={<CheckCircleIcon />} title="Recipient consent" subtitle="Record source-backed evidence by endpoint and purpose. Consent events remain immutable."
    action={valid ? <Button onClick={() => setCreate(true)}>Record consent evidence</Button> : undefined}
    footer={<span>Marketing needs recorded consent. Category rules also govern preferences and suppressions; security messages follow the existing mandatory-notification policy.</span>}>
    <ListFilters path="consent" fields={[{ name: 'recipient_endpoint_id', label: 'Recipient endpoint reference (UUID)' }]} />
    {!valid ? <EmptyState icon={<SearchIcon />} title={endpointId ? 'Enter a valid endpoint UUID.' : 'Choose a recipient endpoint'}
      body={endpointId ? 'The reference must be a UUID issued for a recipient endpoint.' : 'Select a recipient endpoint, or enter its reference, to inspect the consent recorded against it.'}
      action={can('recipient') ? <a className="janso-btn janso-btn--ghost" href={href('recipients')}>Open recipient endpoints</a> : undefined} /> : <>
      {can('recipient') && <ResourceState state={endpoint}>{endpoint.data && <Facts items={[
        { label: 'Endpoint', value: <>{endpoint.data.destination_masked} / {readable(endpoint.data.channel)}</> },
        { label: 'Masked record', value: <a className="janso-link" href={href('recipients') + '?recipient_endpoint_id=' + endpointId}>View masked endpoint</a> }]} />}</ResourceState>}
      <NotificationTable title="Consent states" state={state} path="consent" noun="consent state" empty="No consent evidence has been recorded for this endpoint." columns={[
        { key: 'purpose', header: 'Purpose' }, { key: 'state', header: 'Consent', type: 'custom', render: row => <StateBadge value={row.state} /> }, { key: 'effective_at', header: 'Effective at', type: 'datetime' }, { key: 'expires_at', header: 'Expires at', type: 'datetime' },
        { key: 'history', header: 'History', type: 'custom', render: row => <Button variant="ghost" onClick={() => setHistory(row)}>Consent history</Button> }]} />
    </>}
    {create && valid && <Editor title="Record consent evidence" initial={{ purpose: 'marketing', state: 'unknown', lawful_basis: '', evidence_ref: '', source: 'console', source_event_key: crypto.randomUUID(), occurred_at: defaultTime(), expires_at: '' }} fields={[
      { name: 'purpose', label: 'Purpose category', type: 'select', required: true, options: ['marketing', 'transactional', 'operational', 'security'].map(value => option(value)) },
      { name: 'state', label: 'Consent state', type: 'select', required: true, options: ['unknown', 'granted', 'denied', 'withdrawn'].map(value => option(value)) },
      { name: 'lawful_basis', label: 'Lawful basis', maxLength: 40 }, { name: 'evidence_ref', label: 'Evidence reference', required: true, maxLength: 500, help: 'Use an authorized evidence reference. Do not paste message content or sensitive identity data.' },
      { name: 'source', label: 'Evidence source', required: true, maxLength: 40 }, { name: 'occurred_at', label: 'Evidence occurred at (local time)', type: 'datetime-local', required: true }, { name: 'expires_at', label: 'Expires at (optional local time)', type: 'datetime-local' },
    ]} onClose={() => { setCreate(false); state.refresh(); }} submit={async (values, action) => {
      await action.send('consent-events', 'POST', { ...values, recipient_endpoint_id: endpointId, lawful_basis: values.lawful_basis || null, evidence_ref: values.evidence_ref, occurred_at: instant(values.occurred_at), expires_at: values.expires_at ? instant(values.expires_at) : null }, true);
    }}><Notice tone="warning" title="Evidence is immutable">Confirm the evidence and selected endpoint before saving. An older event is retained as evidence without replacing a newer consent state.</Notice></Editor>}
  </Surface>
    {history && <NotificationHistory key={history.id} entity="consent_state" identity={history.id} />}
  </>;
}
export function NotificationSuppressions() {
  const state = useResource<Page<Suppression>>(useListResource('suppressions', ['channel']));
  const [create, setCreate] = useState(false), [expire, setExpire] = useState<Suppression>(), [history, setHistory] = useState<Suppression>();
  const add = <Button onClick={() => setCreate(true)}>Add suppression</Button>;
  return <><Surface icon={<XCircleIcon />} title="Suppressions" subtitle="Block eligible future delivery for a destination, category or event. Addresses are hashed server-side."
    action={add} footer={<span>A suppression does not recall provider submissions already in progress.</span>}>
    <ListFilters path="suppressions" fields={[{ name: 'channel', label: 'Channel', values: ['email', 'sms', 'whatsapp'] }]} />
    <NotificationTable title="Suppressions" state={state} path="suppressions" noun="suppression"
      empty="Nothing is suppressed in this scope. Provider complaints and bounces also add entries here." columns={[
        { key: 'channel', header: 'Channel' }, { key: 'scope_type', header: 'Scope' }, { key: 'scope_key', header: 'Scoped purpose' }, { key: 'reason', header: 'Reason' }, { key: 'source', header: 'Source' }, { key: 'valid_from', header: 'From', type: 'datetime' }, { key: 'valid_to', header: 'Until', type: 'datetime' },
        { key: 'history', header: 'History', type: 'custom', render: row => <Button variant="ghost" onClick={() => setHistory(row)}>Suppression history</Button> },
        { key: 'expire', header: 'Release', type: 'custom', render: row => <Button variant="ghost" disabled={!!row.valid_to && new Date(row.valid_to).getTime() <= Date.now()} onClick={() => setExpire(row)}>End suppression</Button> },
      ]} />
    {create && <Editor title="Add suppression" initial={{ channel: 'email', destination: '', scope_type: 'global', scope_key: '', reason: '', valid_from: defaultTime(), valid_to: '' }} fields={values => [
      channelField, { name: 'destination', label: 'Destination to suppress', required: true, maxLength: 320, help: 'Enter the exact email address or E.164 number. It is used to compute a hash and is not stored in this form after closing.' },
      { name: 'scope_type', label: 'Suppression scope', type: 'select', required: true, options: [option('global', 'All eligible purposes'), option('category', 'One category'), option('event', 'One event purpose')] },
      ...(values.scope_type !== 'global' ? [{ name: 'scope_key', label: values.scope_type === 'category' ? 'Category' : 'Event purpose key', type: values.scope_type === 'category' ? 'select' as const : 'text' as const, required: true, options: ['transactional', 'operational', 'marketing', 'security'].map(value => option(value)) }] : []),
      { name: 'reason', label: 'Reason code', required: true, maxLength: 40 }, { name: 'valid_from', label: 'Effective from (local time)', type: 'datetime-local', required: true }, { name: 'valid_to', label: 'Effective until (optional local time)', type: 'datetime-local' },
    ]} onChange={(values, name) => name === 'scope_type' ? { ...values, scope_key: values.scope_type === 'category' ? 'marketing' : '' } : values} onClose={() => { setCreate(false); state.refresh(); }} submit={async (values, action) => {
      await action.send('suppressions', 'POST', { ...values, destination: values.destination.trim(), scope_key: values.scope_type === 'global' ? '' : values.scope_key, valid_from: instant(values.valid_from), valid_to: values.valid_to ? instant(values.valid_to) : null }, true);
    }}><Notice tone="warning" title="Review before saving">Check the destination and scope. A suppression does not recall provider submissions already in progress.</Notice></Editor>}
    {expire && <ConfirmAction title="End suppression" label="End suppression" body="Eligible future notifications may use this destination again, subject to current consent and other policies." onDone={() => { setExpire(undefined); state.refresh(); }} perform={async action => { await action.send(`suppressions/${expire.id}/expire`, 'POST', {}); }} />}
  </Surface>
    {history && <NotificationHistory key={history.id} entity="suppression" identity={history.id} />}
  </>;
}
