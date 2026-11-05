'use client';
import { useState } from 'react';
import { AuditIcon, Button } from '@janso/ui';
import { PlatformHistory } from '../PlatformHistory';
import { AuditEvents } from '../AuditEvents';
import { ALL_COMPANIES, Surface, useNotifications } from './common';

export function NotificationHistory({ entity, identity, companyId }: { entity: string; identity: string; companyId?: string }) {
  const { owner, permissions } = useNotifications(); const [open, setOpen] = useState(false);
  if (owner === 'platform') return <PlatformHistory entityType={'notification.' + entity} entityId={identity} />;
  if (!permissions.includes('audit.read')) return null;
  // Loaded on demand: an audit query is not free, and most readers of a record never open it.
  return <Surface icon={<AuditIcon />} title="Administrative history" subtitle="Who changed this record, and when."
    action={<Button variant="ghost" aria-expanded={open} onClick={() => setOpen(value => !value)}>{open ? 'Hide history' : 'Show history'}</Button>}>
    {open ? <AuditEvents entityType={'notification.' + entity} entityId={identity} companyId={companyId === ALL_COMPANIES ? undefined : companyId} />
      : <p className="janso-meta">History is loaded when you open it.</p>}
  </Surface>;
}
