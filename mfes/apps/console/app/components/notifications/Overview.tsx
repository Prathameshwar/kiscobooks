'use client';
import { useState, type ReactNode } from 'react';
import { ActionCard, ActivityIcon, AuditIcon, BellIcon, BookIcon, Button, CheckCircleIcon, CustomersIcon, DocumentIcon, EmptyState, ListRow, MailIcon, MessageIcon, Notice, RefreshIcon, SectionHeader, ShieldIcon, XCircleIcon } from '@janso/ui';
import type { ChannelState } from '../../lib/notification-api';
import { notificationSectionGroups } from '../../lib/notification-navigation';
import { ActionBar, ConfirmAction, Facts, ResourceState, StateBadge, Surface, stateTone, useNotifications, useResource, readable } from './common';

/**
 * One glyph per area. Thirteen cards all carrying the same bell is a grid the eye cannot use —
 * the icon is the only part of a card that can be recognised before the title is read.
 */
const AREA_ICONS: Record<string, ReactNode> = {
  channels: <MessageIcon />, providers: <ShieldIcon />, templates: <DocumentIcon />, assignments: <BookIcon />,
  routing: <ActivityIcon />, recipients: <CustomersIcon />, consent: <CheckCircleIcon />, suppressions: <XCircleIcon />,
  requests: <BellIcon />, deliveries: <MailIcon />, receipts: <AuditIcon />, recovery: <RefreshIcon />,
};
const CHANNEL_ICONS: Record<string, ReactNode> = { email: <MailIcon />, sms: <MessageIcon />, whatsapp: <MessageIcon />, push: <BellIcon /> };

export function NotificationOverview() {
  const { owner, permissions, href, can } = useNotifications();
  const state = useResource<ChannelState[]>(can('provider') ? 'channels' : undefined);
  const rows = state.data?.filter(row => row.channel !== 'push') ?? [];
  return <><Surface icon={<BellIcon />} title="Notification setup" subtitle="Configure transport, verify senders, prepare templates, assign their purpose, then check routing."
    footer={<span>Readiness describes configuration. Delivery history records what happened when a message was sent.</span>}>
    <p>{owner === 'platform' ? 'Manage delivery for platform staff and people who do not yet belong to a tenant.' : 'Manage message delivery, templates and recipient policies for your organisation.'}</p>
    {can('provider') ? <ResourceState state={state}>
      {/* A row per channel rather than a paragraph per channel: the two badges are the answer the
        * reader came for, and in a paragraph they sat mid-sentence with no column to line up in. */}
      {rows.length ? <div>{rows.map(row => <ListRow key={row.channel} icon={CHANNEL_ICONS[row.channel] ?? <BellIcon />} tone={stateTone(row.ready ? 'ready' : 'pending')}
        href={href('channels')} primary={readable(row.channel)}
        meta={row.reasons.length ? row.reasons.map(readable).join(' · ') : row.ready ? 'Ready to send' : undefined}
        figure={<><StateBadge value={row.is_enabled ? 'active' : 'disabled'} /> <StateBadge value={row.ready ? 'ready' : 'pending'} /></>} />)}</div>
        : <EmptyState icon={<MessageIcon />} title="No channels are configured yet" body="Register a provider account and verify a sender to make a channel ready." action={<a className="janso-btn janso-btn--ghost" href={href('providers')}>Open providers and senders</a>} />}
    </ResourceState> : <Notice>Provider read access is required to show channel readiness.</Notice>}
  </Surface>
    {/* Grouped, because the order is the procedure: transport, then content, then who may receive
      * it, then the record of what happened. One flat grid of thirteen made that order invisible. */}
    {notificationSectionGroups(owner, permissions).map(({ group, items }) => {
      const cards = items.filter(item => item.key !== 'overview');
      if (!cards.length) return null;
      return <section key={group}><SectionHeader overline={group} title={GROUP_TITLES[group] ?? group} description={GROUP_DESCRIPTIONS[group]} />
        <div className="janso-action-card-grid">{cards.map(item => <ActionCard key={item.key} icon={AREA_ICONS[item.key] ?? <BellIcon />} title={item.label} description={item.blurb} actionLabel={'Open ' + item.label.toLowerCase()} href={href(item.key)} />)}</div>
      </section>;
    })}
  </>;
}
const GROUP_TITLES: Record<string, string> = { Transport: 'Transport', Content: 'Message content', Policy: 'Recipients and policy', Operations: 'What happened' };
const GROUP_DESCRIPTIONS: Record<string, string> = {
  Transport: 'The accounts and senders a message can physically leave through.',
  Content: 'What each purpose says, and which template it uses when.',
  Policy: 'Who may be written to, on what evidence, and who must not be.',
  Operations: 'Requests, attempts, provider evidence and anything left unresolved.',
};

export function NotificationChannels() {
  const { can, href } = useNotifications(); const state = useResource<ChannelState[]>('channels');
  return <ResourceState state={state}>{state.data?.length
    ? <div className="janso-action-card-grid">{state.data.map(row => <ChannelCard key={row.channel} row={row} manage={can('provider', 'manage')} refresh={state.refresh} providerHref={href('providers')} />)}</div>
    : <EmptyState icon={<MessageIcon />} title="No channels are available" body="Channel settings appear once the service reports a transport for this owner." />}</ResourceState>;
}
function ChannelCard({ row, manage, refresh, providerHref }: { row: ChannelState; manage: boolean; refresh: () => void; providerHref: string }) {
  const [confirm, setConfirm] = useState(false);
  // Blocked for a reason other than the switch itself: enabling would not make it ready, so the
  // button says so by being unavailable and the reasons below say why.
  const blocked = !row.is_enabled && row.reasons.some(reason => reason !== 'channel_disabled');
  return <Surface icon={CHANNEL_ICONS[row.channel] ?? <BellIcon />} title={readable(row.channel)}
    badge={<><StateBadge value={row.is_enabled ? 'active' : 'disabled'} /> <StateBadge value={row.ready ? 'ready' : 'pending'} /></>}
    footer={<a className="janso-link" href={providerHref}>Manage providers and senders</a>}>
    <Facts items={[{ label: 'Admission', value: row.is_enabled ? 'Enabled for new sends' : 'Disabled for new sends' },
      { label: 'Configuration', value: row.ready ? 'Ready — a validated provider and a verified sender exist' : 'Not ready' }]} />
    {row.reasons.length ? <Notice tone={row.ready ? 'info' : 'warning'} title="Outstanding for this channel">
      <ul>{row.reasons.map(reason => <li key={reason}>{readable(reason)}</li>)}</ul></Notice> : null}
    {manage ? <ActionBar><Button variant={row.is_enabled ? 'ghost' : 'primary'} disabled={blocked} onClick={() => setConfirm(true)}>{row.is_enabled ? 'Disable' : 'Enable'} {readable(row.channel)}</Button></ActionBar> : null}
    {confirm && <ConfirmAction title={(row.is_enabled ? 'Disable ' : 'Enable ') + readable(row.channel)} body={row.is_enabled ? 'New sends using this channel will stop. Submissions already in progress cannot be recalled.' : 'Allow configured notifications to use this channel.'} onDone={() => { setConfirm(false); refresh(); }} perform={async action => { await action.send('channel-settings/' + row.channel, 'PUT', { is_enabled: !row.is_enabled }); }} />}
  </Surface>;
}
