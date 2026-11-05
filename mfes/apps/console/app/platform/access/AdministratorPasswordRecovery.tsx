'use client';
import { useEffect, useRef, useState } from 'react';
import type { components } from '@janso/api-client/identity';
import { Button, Card, CardBody, CardHeader, ConfirmDialog, Notice, Select, TextField, formatDateTime, useDisplayConfig } from '@janso/ui';
import { platformCall, platformFailure, PlatformError, type PlatformFailure } from '../../lib/platform-api';
import { administratorPath, type Administrator } from '../../lib/platform-access';
import { acceptableRecoveryLink } from '../../lib/recovery-link';

type Recovery = components['schemas']['AdministratorRecoveryLink'];
/** Ephemeral recovery link, from whichever provider the installation uses. Never autosaved, cached or automatically retried. */
export function AdministratorPasswordRecovery({ administrator, returnTo, disabled, onBusyChange, onReview }: { administrator: Administrator; returnTo: string; disabled?: boolean; onBusyChange?: (busy: boolean) => void; onReview?: () => void }) {
  const [open, setOpen] = useState(false), [reason, setReason] = useState(''), [fieldError, setFieldError] = useState('');
  const [delivery, setDelivery] = useState<'link' | 'email'>('link'), [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<PlatformFailure | null>(null), [result, setResult] = useState<Recovery | null>(null), [message, setMessage] = useState('');
  const busy = useRef(false), mounted = useRef(true), display = useDisplayConfig();
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    if (!result) return;
    const timer = window.setTimeout(() => { setResult(null); setMessage('The recovery link has expired. Create another link if it is still needed.'); }, Math.max(0, Date.parse(result.expires_at) - Date.now()));
    return () => window.clearTimeout(timer);
  }, [result]);
  const deliveries = administrator.recovery_deliveries ?? [];
  async function save() {
    if (busy.current || !deliveries.includes(delivery)) return;
    if (reason.trim().length < 3 || reason.length > 500 || /[\x00-\x1f\x7f]/.test(reason)) { setFieldError('Enter a reason with 3–500 characters and no control characters.'); return; }
    busy.current = true; setPending(true); onBusyChange?.(true); setFailure(null); setResult(null); setMessage('');
    try {
      const value = await platformCall<Recovery>(administratorPath(administrator.tenant.id, administrator.id) + '/password-recovery', 'POST', {
        delivery, reason: reason.trim(), expected_updated_at: administrator.updated_at, expected_assignment_updated_at: administrator.assignment_updated_at,
      });
      if (value.tenant_id !== administrator.tenant.id || value.administrator_id !== administrator.id || value.delivery !== delivery
        || !Number.isFinite(Date.parse(value.expires_at)) || Date.parse(value.expires_at) <= Date.now() || Date.parse(value.expires_at) > Date.now() + 11 * 60_000) throw new Error('Unexpected recovery receipt');
      if (delivery === 'link') {
        const url = new URL(value.recovery_url ?? '');
        if (!acceptableRecoveryLink(url)) throw new Error('Unexpected recovery link');
      } else if (value.recovery_url != null) throw new Error('Unexpected email receipt');
      if (mounted.current) { setResult(value); setOpen(false); setReason(''); setMessage(delivery === 'email' ? 'Recovery email requested for ' + administrator.email + '. Delivery is handled by the sign-in provider.' : 'Recovery link created. Share it privately with ' + administrator.email + '.'); }
    } catch (error) { if (mounted.current) setFailure(platformFailure(error)); }
    finally { busy.current = false; if (mounted.current) { setPending(false); onBusyChange?.(false); } }
  }
  return <div id="password-recovery"><Card>
    <CardHeader title="Password recovery" subtitle="The administrator chooses a new password securely in the sign-in service." />
    <CardBody><div className="janso-flow">
      <p>Recovery links expire after 10 minutes. Creating a link does not activate an account or change its password.</p>
      {!deliveries.includes('link') && <Notice tone="info">Password recovery requires an active workspace, an accepted active administrator assignment, and configured billing sign-in recovery.</Notice>}
      {deliveries.includes('link') && !deliveries.includes('email') && <Notice tone="info">Recovery email will become available when the sign-in provider’s email settings are configured.</Notice>}
      <Button variant="ghost" disabled={disabled || pending || !deliveries.includes('link')} onClick={() => { setOpen(true); setFailure(null); setReason(''); setFieldError(''); }}>Reset password</Button>
      {message && <Notice tone="success">{message}</Notice>}
      {result?.recovery_url && <>
        <TextField label="Password recovery link" value={result.recovery_url} readOnly autoComplete="off" hint={'Expires at ' + formatDateTime(result.expires_at, display) + '. Anyone with this link can start recovery; share it securely.'} />
        <div className="janso-page-navigation"><Button variant="ghost" onClick={async () => { try { await navigator.clipboard.writeText(result.recovery_url!); setMessage('Recovery link copied. Share it privately with the administrator.'); } catch { setMessage('Select and copy the recovery link above.'); } }}>Copy recovery link</Button>
          <Button variant="ghost" onClick={() => { setResult(null); setMessage('Recovery link hidden. It remains valid until it expires or is used.'); }}>Hide recovery link</Button></div>
      </>}
    </div></CardBody>
    <ConfirmDialog open={open} title="Reset administrator password?" confirmLabel={delivery === 'link' ? 'Create recovery link' : 'Email recovery link'} busy={pending} onConfirm={save} onCancel={() => { if (!busy.current) { setOpen(false); setFailure(null); } }}>
      <p>Recover the password for {administrator.display_name} ({administrator.email}). The administrator must complete recovery before the password changes.</p>
      <Select label="Delivery" value={delivery} disabled={pending} onChange={value => setDelivery(value as 'link' | 'email')} options={[
        { value: 'link', label: 'Show expiring recovery link' }, { value: 'email', label: 'Email recovery link', disabled: !deliveries.includes('email') },
      ]} />
      <TextField label="Reason" required minLength={3} maxLength={500} value={reason} error={fieldError} disabled={pending} onChange={event => { setReason(event.target.value); setFieldError(''); }} />
      <PlatformError value={failure} returnTo={returnTo} />
      {failure?.status === 409 && onReview && <Button variant="ghost" onClick={() => { setOpen(false); setFailure(null); setReason(''); onReview(); }}>Refresh and review</Button>}
      {failure && failure.status >= 500 && <Notice tone="warning">The request was not automatically retried. A link or email may already have been created. Check with the administrator before requesting another.</Notice>}
    </ConfirmDialog>
  </Card></div>;
}
