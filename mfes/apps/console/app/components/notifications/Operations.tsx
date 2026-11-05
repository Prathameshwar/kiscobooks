'use client';
import { useState } from 'react';
import { NotificationHistory } from './History';
import { AuditIcon, BellIcon, Button, ClockIcon, MailIcon, Notice, RefreshIcon, useFormatters, type Column } from '@janso/ui';
import type { Attempt, Delivery, DeliveryDetail, DeliveryEvent, NotificationRequest, Page, PlanningOutcome, ProviderReceipt, RequestDetail, Variant, VersionDetail } from '../../lib/notification-api';
import { ActionBar, ChoicePages, ConfirmAction, Editor, Facts, ListFilters, LocalPages, NotificationTable, References, ResourceState, StateBadge, Surface, option, readable, useChoices, useListResource, useNotifications, useResource } from './common';

export function NotificationRequests({ identity }: { identity?: string }) {
  const { href, can } = useNotifications(); const resource = useListResource('requests', ['status', 'event_key']);
  const list = useResource<Page<NotificationRequest>>(identity ? undefined : resource);
  const state = useResource<RequestDetail>(identity ? 'requests/' + identity : undefined);
  const outcomesPath = useListResource(`requests/${identity}/outcomes`, []);
  const outcomes = useResource<Page<PlanningOutcome>>(identity ? outcomesPath : undefined);
  const { dateTime } = useFormatters(); const request = state.data;
  return <><Surface icon={<BellIcon />} title={identity ? 'Notification request' : 'Notification requests'}
    subtitle="Planning completion records which channels were selected or skipped; delivery history records provider outcomes."
    badge={request ? <StateBadge value={request.status} /> : undefined}
    footer={request && can('delivery') ? <a className="janso-link" href={href('deliveries') + '?request_id=' + identity}>View deliveries for this request</a> : undefined}>
    {!identity ? <><ListFilters path="requests" fields={[{ name: 'status', label: 'Planning status', values: ['processing', 'completed', 'failed'] }, { name: 'event_key', label: 'Purpose key' }]} />
      <NotificationTable title="Notification requests" state={list} path="requests" noun="request"
        empty="A request appears here when a source service asks for a notification." columns={[
          { key: 'event_key', header: 'Purpose', type: 'link', href: row => href('requests/' + row.id) }, { key: 'category', header: 'Category' },
          { key: 'status', header: 'Planning', type: 'custom', render: row => <StateBadge value={row.status} /> }, { key: 'received_at', header: 'Received', type: 'datetime' }, { key: 'scheduled_at', header: 'Scheduled', type: 'datetime' },
        ]} /></> : <ResourceState state={state}>{request && <>
          <Facts items={[{ label: 'Purpose', value: readable(request.event_key) }, { label: 'Category', value: readable(request.category) },
            { label: 'Planning', value: <StateBadge value={request.status} /> },
            { label: 'Source', value: request.source_service + ' / ' + readable(request.source_event_key) },
            { label: 'Received', value: dateTime(request.received_at) },
            { label: 'Expires', value: request.expires_at ? dateTime(request.expires_at) : 'No expiry recorded' }]} />
          <NotificationTable title="Channel planning outcomes" state={outcomes} path={'requests/' + identity} noun="planning outcome"
            empty="Planning has recorded no channel decision for this request yet." columns={[
              { key: 'channel', header: 'Channel' }, { key: 'decision', header: 'Planning decision' }, { key: 'reason_code', header: 'Reason', value: row => readable(row.reason_code) }, { key: 'created_at', header: 'Planned', type: 'datetime' },
            ]} />
          <SourceReference request={request} /><References entries={{ Request: request.id, 'Source message': request.source_message_id, 'Source record': request.aggregate_id, 'Target tenant': request.target_tenant_id }} />
          <NotificationHistory entity="notification_request" identity={request.id} companyId={request.company_id} />
        </>}</ResourceState>}
  </Surface></>;
}
function SourceReference({ request }: { request: RequestDetail }) {
  const { permissions, owner, companyId } = useNotifications();
  return owner === 'tenant' && companyId === request.company_id && request.source_service === 'vouchers' && permissions.includes('vouchers.read')
    ? <p><a className="janso-link" href="/vouchers">Open voucher workspace</a> / source reference: <code className="janso-table__code">{request.aggregate_id}</code></p>
    : <p className="janso-meta">The source reference remains available here. Open the source application with the appropriate access to inspect that record.</p>;
}
export function NotificationDeliveries({ identity, recovery = false }: { identity?: string; recovery?: boolean }) {
  if (identity) return <DeliveryRecord identity={identity} />;
  return <DeliveryDirectory recovery={recovery} />;
}
function DeliveryDirectory({ recovery }: { recovery: boolean }) {
  const { href } = useNotifications(); const path = recovery ? 'recovery' : 'deliveries';
  const resource = useListResource(recovery ? 'reconciliation-cases' : 'deliveries', recovery ? [] : ['status', 'channel', 'request_id']);
  const state = useResource<Page<Delivery>>(resource);
  const columns: Column<Delivery>[] = [
    { key: 'destination_masked', header: 'Recipient', type: 'link', href: row => href('deliveries/' + row.id) }, { key: 'channel', header: 'Channel' },
    { key: 'status', header: 'Delivery state', type: 'custom', render: row => <StateBadge value={row.status} /> }, { key: 'status_reason', header: 'Reason', value: row => readable(row.status_reason) }, { key: 'attempt_count', header: 'Attempts' }, { key: 'created_at', header: 'Created', type: 'datetime' }, { key: 'next_attempt_at', header: 'Next attempt', type: 'datetime' },
  ];
  return <Surface icon={recovery ? <RefreshIcon /> : <MailIcon />} title={recovery ? 'Delivery recovery' : 'Delivery history'}
    subtitle={recovery ? 'Unresolved sending states need provider evidence before anything is sent again.' : 'Provider acceptance and confirmed delivery are separate states.'}
    footer={recovery ? <a className="janso-link" href={href('receipts') + '?status=unmatched'}>Inspect unmatched provider receipts</a> : undefined}>
    {/* The warning leads on the recovery screen. It is the one place in this console where the
      * obvious action — retry — is the one that can charge or message somebody twice. */}
    {recovery ? <Notice tone="warning" title="A blind retry can send the message twice">Resolve each case with signed provider evidence. Only verified, matching evidence can settle a delivery that is still sending.</Notice> : null}
    {!recovery && <ListFilters path={path} fields={[{ name: 'channel', label: 'Channel', values: ['email', 'sms', 'whatsapp'] }, { name: 'status', label: 'Status', values: ['pending', 'scheduled', 'retry_wait', 'sending', 'accepted', 'delivered', 'read', 'failed', 'suppressed', 'expired', 'cancelled'] }, { name: 'request_id', label: 'Request reference (UUID)' }]} />}
    <NotificationTable title={recovery ? 'Unresolved deliveries' : 'Deliveries'} state={state} columns={columns} path={path} noun="delivery" nounPlural="deliveries"
      empty={recovery ? 'No sending deliveries currently require reconciliation. Other delivery states are listed in delivery history.' : 'No delivery matches this view.'} />
  </Surface>;
}
function DeliveryRecord({ identity }: { identity: string }) {
  const { href, can } = useNotifications(); const { dateTime } = useFormatters();
  const state = useResource<DeliveryDetail>('deliveries/' + identity); const delivery = state.data;
  const [retry, setRetry] = useState(false), [reconcile, setReconcile] = useState(false);
  return <><Surface icon={<MailIcon />} title={delivery ? 'Delivery to ' + delivery.destination_masked : 'Delivery details'}
    subtitle={delivery ? readable(delivery.channel) + ' / ' + readable(delivery.status_reason) : undefined}
    badge={delivery ? <StateBadge value={delivery.status} /> : undefined}>
    <ResourceState state={state}>{delivery && <>
      {/* Four separate facts, not one status: a provider accepting a message and a recipient
        * receiving it are different claims, and the gap between them is the whole point. */}
      <Facts items={[{ label: 'Created', value: dateTime(delivery.created_at) },
        { label: 'Provider accepted', value: delivery.accepted_at ? dateTime(delivery.accepted_at) : 'Not recorded' },
        { label: 'Delivered', value: delivery.delivered_at ? dateTime(delivery.delivered_at) : 'Not confirmed' },
        { label: 'Completed', value: delivery.completed_at ? dateTime(delivery.completed_at) : 'Not complete' },
        { label: 'Attempts', value: String(delivery.attempt_count) }]} />
      {delivery.status === 'sending' && <Notice tone="warning" title="The provider outcome is unresolved">Keep this delivery in recovery until signed provider evidence establishes its outcome.</Notice>}
      {can('delivery', 'retry') && (['failed', 'expired'].includes(delivery.status) || ['sending', 'accepted'].includes(delivery.status)) ? <ActionBar>
        {['failed', 'expired'].includes(delivery.status) ? <Button onClick={() => setRetry(true)}>Retry delivery</Button> : null}
        {['sending', 'accepted'].includes(delivery.status) ? <Button onClick={() => setReconcile(true)}>Link verified receipt</Button> : null}
      </ActionBar> : null}
      {/* The cross-references are a row of links, kept apart from the verbs above: a reader
        * following lineage is not the same reader about to re-send a message. */}
      <nav className="janso-page-navigation" aria-label="Delivery lineage">
        {can('request') && <a className="janso-link" href={href('requests/' + delivery.request_id)}>Open request and planning</a>}
        {can('provider') && <a className="janso-link" href={href('providers/' + delivery.provider_account_id)}>Open provider</a>}
        {can('route') && <a className="janso-link" href={href('routing/' + delivery.routing_rule_id)}>Open delivery route</a>}
        {can('recipient') && <a className="janso-link" href={href('recipients') + '?recipient_endpoint_id=' + delivery.recipient_endpoint_id}>View masked recipient</a>}
        {can('consent', 'manage') && <a className="janso-link" href={href('consent') + '?recipient_endpoint_id=' + delivery.recipient_endpoint_id}>Inspect consent</a>}
      </nav>
      {/* Outside the nav row: it resolves two records first, so it may render a placeholder, and a
        * skeleton inside a row of links would reflow the links beside it. */}
      {can('template') && <TemplateLineage versionId={delivery.template_version_id} />}
      <References entries={{ Delivery: delivery.id, 'Provider message': delivery.provider_message_id, 'Template version': delivery.template_version_id, Assignment: delivery.use_case_binding_id, 'Provider template binding': delivery.provider_template_binding_id, Sender: delivery.sender_identity_id, Route: delivery.routing_rule_id }} />
      {retry && <ConfirmAction title="Retry delivery" label="Retry delivery" body="The API will check expiry, retained content and current policy. Historical attempts are preserved; the provider may still reject this retry." onDone={() => { setRetry(false); state.refresh(); }} perform={async action => { await action.send(`deliveries/${identity}/retry`, 'POST', {}, true); }} />}
      {reconcile && <ReceiptLinker delivery={delivery} onClose={() => { setReconcile(false); state.refresh(); }} />}
    </>}</ResourceState></Surface>
    {delivery && <><AttemptHistory identity={identity} /><DeliveryEvents identity={identity} /><NotificationHistory entity="notification_delivery" identity={identity} /></>}
  </>;
}
function TemplateLineage({ versionId }: { versionId: string }) {
  const { href } = useNotifications(); const version = useResource<VersionDetail>('template-versions/' + versionId);
  const variant = useResource<Variant>(version.data ? 'variants/' + version.data.template_variant_id : undefined);
  return <ResourceState state={version}><ResourceState state={variant}>{variant.data && <a className="janso-link" href={href(`templates/${variant.data.template_id}/variants/${variant.data.id}/versions/${versionId}`)}>Open frozen template version</a>}</ResourceState></ResourceState>;
}
function AttemptHistory({ identity }: { identity: string }) {
  const [cursor, setCursor] = useState<string | null>(null); const state = useResource<Page<Attempt>>(`deliveries/${identity}/attempts?limit=50` + (cursor ? '&cursor=' + encodeURIComponent(cursor) : ''));
  return <Surface icon={<RefreshIcon />} title="Attempt history" subtitle="One row per transport attempt, with what the provider returned.">
    <NotificationTable title="Delivery attempts" state={state} noun="attempt" empty="No attempt has been made for this delivery yet." columns={[
      { key: 'attempt_number', header: 'Attempt' }, { key: 'outcome', header: 'Transport outcome' }, { key: 'http_status', header: 'HTTP status' }, { key: 'provider_error_code', header: 'Reason', value: row => readable(row.provider_error_code) }, { key: 'started_at', header: 'Started', type: 'datetime' }, { key: 'completed_at', header: 'Completed', type: 'datetime' },
    ]} /><LocalPages cursor={cursor} next={state.data?.page.next_cursor} setCursor={setCursor} name="attempt" /></Surface>;
}
function DeliveryEvents({ identity }: { identity: string }) {
  const [cursor, setCursor] = useState<string | null>(null); const state = useResource<Page<DeliveryEvent>>(`deliveries/${identity}/events?limit=50` + (cursor ? '&cursor=' + encodeURIComponent(cursor) : ''));
  return <Surface icon={<ClockIcon />} title="Delivery timeline" subtitle="Every state change, and the evidence that caused it.">
    <NotificationTable title="Delivery events" state={state} noun="event" empty="No state change has been recorded for this delivery." columns={[
      { key: 'observed_at', header: 'Observed', type: 'datetime' }, { key: 'source', header: 'Source' }, { key: 'from_status', header: 'Previous state' }, { key: 'to_status', header: 'New state', type: 'custom', render: row => <StateBadge value={row.to_status} /> }, { key: 'reason_code', header: 'Reason', value: row => readable(row.reason_code) },
    ]} /><LocalPages cursor={cursor} next={state.data?.page.next_cursor} setCursor={setCursor} name="event" /></Surface>;
}
export function NotificationReceipts({ identity }: { identity?: string }) {
  const { href } = useNotifications(); const resource = useListResource('provider-events', ['status', 'provider_account_id']);
  const state = useResource<Page<ProviderReceipt>>(identity ? undefined : resource), detail = useResource<ProviderReceipt>(identity ? 'provider-events/' + identity : undefined);
  return <><Surface icon={<AuditIcon />} title={identity ? 'Provider receipt' : 'Provider receipt inbox'}
    subtitle="Verified receipt references and processing state. Raw callback bodies and recipient data are excluded."
    badge={detail.data ? <><StateBadge value={detail.data.processing_status} /> <StateBadge value={detail.data.signature_verified ? 'verified' : 'error'} /></> : undefined}
    footer={detail.data?.delivery_id ? <a className="janso-link" href={href('deliveries/' + detail.data.delivery_id)}>Open correlated delivery</a> : undefined}>
    {!identity ? <><ListFilters path="receipts" fields={[{ name: 'status', label: 'Processing status', values: ['pending', 'processed', 'unmatched', 'error'] }, { name: 'provider_account_id', label: 'Provider reference (UUID)' }]} />
      <NotificationTable title="Provider receipts" state={state} path="receipts" noun="provider receipt"
        empty="No provider callback has been recorded for this view." columns={[
          { key: 'event_type', header: 'Provider event', type: 'link', href: row => href('receipts/' + row.id) }, { key: 'processing_status', header: 'Processing', type: 'custom', render: row => <StateBadge value={row.processing_status} /> }, { key: 'signature_verified', header: 'Verified signature', type: 'boolean' }, { key: 'provider_message_id', header: 'Provider message reference', type: 'code' }, { key: 'received_at', header: 'Received', type: 'datetime' },
        ]} /></> : <ResourceState state={detail}>{detail.data && <>
          <Facts items={[{ label: 'Provider event', value: detail.data.event_type },
            { label: 'Processing', value: <StateBadge value={detail.data.processing_status} /> },
            { label: 'Signature', value: detail.data.signature_verified ? 'Verified against the registered provider trust configuration' : 'Not verified — this evidence cannot settle a delivery' }]} />
          <References entries={{ Receipt: detail.data.id, 'Provider message': detail.data.provider_message_id, 'Native attempt': detail.data.attempt_key, Provider: detail.data.provider_account_id }} />
          <Notice>Only verified, matching evidence can resolve a delivery. Manual reconciliation cannot assert delivery success.</Notice>
          <NotificationHistory entity="provider_event" identity={detail.data.id} />
        </>}</ResourceState>}
  </Surface></>;
}
function ReceiptLinker({ delivery, onClose }: { delivery: DeliveryDetail; onClose: () => void }) {
  const receipts = useChoices<ProviderReceipt>('provider-events?provider_account_id=' + delivery.provider_account_id);
  return <Editor title="Link verified receipt" initial={{ provider_event_id: '' }} fields={[{ name: 'provider_event_id', label: 'Matching provider receipt', type: 'select', required: true, options: [option('', 'Choose verified receipt evidence'), ...receipts.items.filter(row => row.signature_verified && !!row.provider_message_id && (!row.delivery_id || row.delivery_id === delivery.id)).map(row => option(row.id, `${row.event_type} / ${row.provider_message_id} / ${row.processing_status}`))] }]} onClose={onClose} submit={async (values, action) => { await action.send(`deliveries/${delivery.id}/reconciliation`, 'POST', values, true); }}><ChoicePages choices={receipts} label="receipt evidence" /><Notice tone="warning" title="The evidence must match this delivery">The API requires a message identity proven by this delivery's attempt. Selecting an unrelated receipt will be rejected. Signed normalization determines the resulting delivery state.</Notice></Editor>;
}
