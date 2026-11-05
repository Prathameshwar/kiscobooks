'use client';
import { useState } from 'react';
import type { components } from '@janso/api-client/identity';
import { Button, ConfirmDialog, Notice, TextField } from '@janso/ui';
import { PlatformError } from '../../lib/platform-api';
import { platformAccessReader } from '../../lib/platform-access';
import { useServiceCommand } from '../../lib/service-resource';

type Tenant = Pick<components['schemas']['PlatformTenantItem'], 'id' | 'name' | 'status' | 'updated_at'>;
/** A tenant action screen shared by its directory and detail page. */
export function TenantLifecycleDialog({ tenant, returnTo, onClose, onChanged, onReview }: {
  tenant: Tenant; returnTo: string; onClose: () => void; onChanged: (message: string) => void; onReview: () => void;
}) {
  const command = useServiceCommand(platformAccessReader, 'platform service');
  const [reason, setReason] = useState(''), [error, setError] = useState('');
  const inactive = tenant.status === 'active';
  const label = inactive ? 'Deactivate tenant' : 'Activate tenant';
  async function save() {
    if (command.pending) return;
    if (reason.trim().length < 3 || reason.length > 500 || /[\x00-\x1f\x7f]/.test(reason)) {
      setError('Enter a reason with 3–500 characters and no control characters.'); return;
    }
    const result = await command.execute<components['schemas']['PlatformTenantItem']>({
      path: `/v1/platform/tenants/${tenant.id}/lifecycle`, method: 'POST',
      body: { status: inactive ? 'suspended' : 'active', reason: reason.trim(), expected_updated_at: tenant.updated_at },
    }, value => {
      if (value.id !== tenant.id || value.status !== (inactive ? 'suspended' : 'active') || !Number.isFinite(Date.parse(value.updated_at))) throw new Error('Unexpected tenant receipt');
    });
    if (result) { onChanged(inactive ? 'Tenant deactivated. Workspace access is suspended; records are retained.' : 'Tenant activated. Workspace access is available to active users.'); onClose(); }
  }
  return <ConfirmDialog open title={label + '?'} confirmLabel={command.uncertain ? 'Retry same request' : label}
    tone={inactive ? 'danger' : 'default'} busy={command.pending} onConfirm={save}
    onCancel={() => { if (!command.pending && !command.uncertain) onClose(); }}>
    <p>{inactive ? `Users of ${tenant.name} will lose workspace access. This action is reversible and retains existing records.` : `Workspace access will be restored for ${tenant.name}. Suspended users remain suspended.`}</p>
    <TextField label="Reason" required minLength={3} maxLength={500} error={error} disabled={command.pending || command.uncertain} value={reason} onChange={event => { setReason(event.target.value); setError(''); }} />
    <PlatformError value={command.failure} returnTo={returnTo} />
    {command.uncertain && <Notice tone="warning">The result could not be confirmed. Retry the same request to confirm it safely.</Notice>}
    {command.failure?.status === 409 && <Button variant="ghost" onClick={() => { command.clear(); onClose(); onReview(); }}>Refresh and review</Button>}
  </ConfirmDialog>;
}
