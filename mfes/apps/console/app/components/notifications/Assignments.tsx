'use client';
import { useState } from 'react';
import { NotificationHistory } from './History';
import { BookIcon, Button, Notice } from '@janso/ui';
import type { Assignment, Page, Template, UseCase } from '../../lib/notification-api';
import { ALL_COMPANIES, ChoicePages, Editor, NotificationTable, ResourceState, Surface, defaultTime, instant, option, readable, useChoices, useListResource, useNotifications, useResource } from './common';

export function NotificationAssignments() {
  const { owner, companyId, can, href } = useNotifications();
  const state = useResource<Page<Assignment>>(useListResource('use-case-bindings', []));
  const cases = useResource<UseCase[]>('use-cases');
  const [create, setCreate] = useState(false), [end, setEnd] = useState<Assignment>(), [history, setHistory] = useState<Assignment>();
  const [purpose, setPurpose] = useState('');
  const templates = useChoices<Template>(create && purpose ? 'templates?event_key=' + encodeURIComponent(purpose) : undefined);
  const assign = can('template', 'manage') ? <Button disabled={!cases.data?.length} onClick={() => { setPurpose(cases.data![0].key); setCreate(true); }}>Assign a purpose</Button> : undefined;
  return <><Surface icon={<BookIcon />} title="Purpose assignments" subtitle="Which template a registered trigger uses, for each channel and effective period." action={assign}
    footer={<span>Assignments may not overlap. Platform and tenant purposes are separate catalogues.</span>}>
    <ResourceState state={cases} />
    <NotificationTable title="Purpose assignments" state={state} path="assignments" noun="purpose assignment"
      empty="Assign a template to a registered trigger so a request can find its content." columns={[
        { key: 'event_key', header: 'Purpose' }, { key: 'trigger_key', header: 'Trigger' }, { key: 'channel', header: 'Channel' },
        { key: 'template_id', header: 'Template', type: 'link', href: row => href('templates/' + row.template_id) },
        { key: 'valid_from', header: 'Effective from', type: 'datetime' }, { key: 'valid_to', header: 'Effective until', type: 'datetime' },
        { key: 'history', header: 'History', type: 'custom', render: row => <Button variant="ghost" onClick={() => setHistory(row)}>Assignment history</Button> },
        ...(can('template', 'manage') ? [{ key: 'end', header: 'End assignment', type: 'custom' as const, render: (row: Assignment) => <Button variant="ghost" disabled={!!row.valid_to && new Date(row.valid_to).getTime() <= Date.now()} onClick={() => setEnd(row)}>Set assignment end</Button> }] : []),
      ]} />
    {create && <Editor title="Assign a purpose" initial={{ event_key: purpose, trigger_key: cases.data?.find(item => item.key === purpose)?.triggers[0] ?? '', channel: cases.data?.find(item => item.key === purpose)?.channels[0] ?? 'email', template_id: '', company_id: companyId ?? ALL_COMPANIES, valid_from: defaultTime(), valid_to: '' }} fields={values => {
      const useCase = cases.data?.find(item => item.key === values.event_key);
      return [
        { name: 'event_key', label: 'Registered purpose', type: 'select', required: true, options: (cases.data ?? []).map(item => option(item.key, readable(item.key))) },
        { name: 'trigger_key', label: 'Source trigger', type: 'select', required: true, options: (useCase?.triggers ?? []).map(item => option(item, readable(item))) },
        { name: 'channel', label: 'Channel', type: 'select', required: true, options: (useCase?.channels ?? []).map(value => option(value)) },
        { name: 'template_id', label: 'Template', type: 'select', required: true, options: [option('', 'Choose a template'), ...templates.items.filter(item => item.event_key === values.event_key && item.is_active && (item.company_id === ALL_COMPANIES || item.company_id === values.company_id)).map(item => option(item.id, item.key))] },
        ...(owner === 'tenant' ? [{ name: 'company_id', label: 'Company scope', type: 'select' as const, required: true, options: [option(ALL_COMPANIES, 'All permitted companies'), ...(companyId ? [option(companyId, 'Current company')] : [])] }] : []),
        { name: 'valid_from', label: 'Effective from (local time)', type: 'datetime-local', required: true },
        { name: 'valid_to', label: 'Effective until (optional local time)', type: 'datetime-local' },
      ];
    }} onChange={(values, name) => {
      if (name === 'event_key') { setPurpose(values.event_key); return { ...values, template_id: '', trigger_key: cases.data?.find(item => item.key === values.event_key)?.triggers[0] ?? '', channel: cases.data?.find(item => item.key === values.event_key)?.channels[0] ?? '' }; }
      if (name === 'company_id') return { ...values, template_id: '' };
      return values;
    }} onClose={() => { setCreate(false); state.refresh(); }} submit={async (values, action) => {
      await action.send('use-case-bindings', 'POST', { company_id: owner === 'platform' ? ALL_COMPANIES : values.company_id, event_key: values.event_key, trigger_key: values.trigger_key, channel: values.channel, template_id: values.template_id, valid_from: instant(values.valid_from), valid_to: values.valid_to ? instant(values.valid_to) : null });
    }}><ChoicePages choices={templates} label="templates" /><Notice>The API rejects overlapping assignments. Platform and tenant purposes are separate catalogues.</Notice></Editor>}
    {end && <Editor title="End purpose assignment" initial={{ valid_to: defaultTime() }} fields={[{ name: 'valid_to', label: 'End at (local time)', type: 'datetime-local', required: true }]} onClose={() => { setEnd(undefined); state.refresh(); }} submit={async (values, action) => { await action.send(`use-case-bindings/${end.id}/end`, 'POST', { valid_to: instant(values.valid_to) }); }} />}
  </Surface>
    {/* The chosen row's history sits after the table rather than inside it: a panel opened from a
      * cell used to appear between the table and its pager, moving the rows the reader was in. */}
    {history && <NotificationHistory key={history.id} entity="notification_use_case_binding" identity={history.id} companyId={history.company_id} />}
  </>;
}
