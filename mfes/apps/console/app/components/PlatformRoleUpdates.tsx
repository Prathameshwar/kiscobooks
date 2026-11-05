'use client';

import { useState } from 'react';
import type { components } from '@janso/api-client/identity';
import { Button, Card, CardBody, Notice, SectionHeader, TextField } from '@janso/ui';
import { serviceCall } from '../lib/service-call';
import { useServiceCommand, useServiceRead, type ServiceReader } from '../lib/service-resource';

type Plan = components['schemas']['RoleSeedPlan'];
type Result = components['schemas']['RoleSeedResult'];
const reader: ServiceReader = request => serviceCall('/api/platform', { ...request, service: 'identity' }, 'system role');
const digest = (value: unknown): value is string => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);

export function PlatformRoleUpdates() {
  const plan = useServiceRead<Plan>('/v1/platform/system-roles', reader, value => {
    if (!digest(value.current_digest) || !digest(value.catalogue_digest) || !Array.isArray(value.changes) || value.changes.length > 100) throw { status: 502, message: 'Role update preview could not be verified.' };
    const keys = new Set<string>();
    for (const change of value.changes) {
      if (!change || typeof change.key !== 'string' || !/^[a-z][a-z0-9_]{2,59}$/.test(change.key) || keys.has(change.key) || !Array.isArray(change.added) || !Array.isArray(change.removed) || [...change.added, ...change.removed].some(key => typeof key !== 'string' || !/^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$/.test(key)) || typeof change.metadata_changed !== 'boolean' || typeof change.deactivate !== 'boolean') throw { status: 502, message: 'Role update preview could not be verified.' };
      keys.add(change.key);
    }
  });
  const command = useServiceCommand(reader, 'system role update');
  const [reason, setReason] = useState(''), [result, setResult] = useState<Result | null>(null);
  async function apply() {
    if (!plan.data || !reason.trim() || command.pending) return;
    const saved = await command.execute<Result>({ path: '/v1/platform/system-roles/reconcile', method: 'POST', body: {
      expected_current_digest: plan.data.current_digest,
      expected_catalogue_digest: plan.data.catalogue_digest,
      reason: reason.trim(),
    } }, value => {
      if (!digest(value.current_digest) || !digest(value.catalogue_digest) || value.catalogue_digest !== plan.data!.catalogue_digest || typeof value.changed !== 'boolean' || !Number.isSafeInteger(value.added_grants) || value.added_grants < 0 || !Number.isSafeInteger(value.removed_grants) || value.removed_grants < 0) throw { status: 502, message: 'The role update result could not be verified. Retry the same update.' };
    });
    if (saved) { setResult(saved); setReason(''); plan.refresh(); }
  }
  return <div className="janso-flow">
    <Notice>Updates apply the shipped system roles. User assignments and custom tenant roles retain their identities. Review every change before applying it.</Notice>
    {plan.loading && <p role="status">Loading role update preview…</p>}
    {plan.failure && <Notice tone="warning">Role changes could not be loaded. <Button variant="ghost" onClick={plan.refresh}>Reload role changes</Button></Notice>}
    {result && <Notice tone="success">{result.changed ? 'System roles updated.' : 'System roles already match the shipped catalogue.'} Added {result.added_grants} grants; removed {result.removed_grants} grants.</Notice>}
    {plan.data && <Card><CardBody>
      <SectionHeader title="Review role changes" description="Only permissions defined by the application can be applied." />
      {plan.data.changes.length ? <ul>{plan.data.changes.map(change => <li key={change.key}>
        <strong>{change.key}</strong>
        {!!change.added.length && <p>Add: {change.added.join(', ')}</p>}
        {!!change.removed.length && <p>Remove: {change.removed.join(', ')}</p>}
        {change.metadata_changed && <p>Update role details or activation.</p>}
        {change.deactivate && <p>Deactivate the retired role; preserve its assignments.</p>}
      </li>)}</ul> : <p>No role changes are pending.</p>}
      <form onSubmit={event => { event.preventDefault(); void apply(); }}>
        <TextField label="Reason for role update" value={reason} required minLength={3} maxLength={500} disabled={command.pending || command.uncertain} onChange={event => { setReason(event.target.value); setResult(null); }} />
        <Button type="submit" loading={command.pending} disabled={plan.loading || command.pending || reason.trim().length < 3 || !plan.data.changes.length || command.blocked && !command.uncertain}>{command.uncertain ? 'Retry the same role update' : 'Apply reviewed role updates'}</Button>
      </form>
    </CardBody></Card>}
    {command.failure && <Notice tone="danger">{command.failure.message}{!command.uncertain && <Button variant="ghost" onClick={() => { command.clear(); plan.refresh(); }}>Review role changes again</Button>}</Notice>}
  </div>;
}
