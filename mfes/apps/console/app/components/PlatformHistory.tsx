'use client';

import { useState } from 'react';
import { Button, Card, CardBody, CardHeader } from '@janso/ui';
import { AuditEvents } from './AuditEvents';

export function platformHistoryHref(entityType?: string, entityId?: string): string {
  const query = new URLSearchParams();
  if (entityType) query.set('entity_type', entityType);
  if (entityId) query.set('entity_id', entityId);
  return '/platform/history' + (query.size ? '?' + query : '');
}

export function PlatformHistory({ entityType, entityId, revision }: { entityType: string; entityId?: string; revision?: string | number }) {
  const [open, setOpen] = useState(false);
  return <Card><CardHeader title="Administrative history" subtitle="Changes and access recorded for this subject" /><CardBody>
    <Button variant="ghost" aria-expanded={open} onClick={() => setOpen(value => !value)}>{open ? 'Hide history' : 'Show history'}</Button>
    {open ? <AuditEvents key={String(revision ?? '')} platform entityType={entityType} entityId={entityId} /> : null}
  </CardBody></Card>;
}
