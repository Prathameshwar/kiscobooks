'use client';

import { useState } from 'react';
import { Button, Card, CardBody, PermissionProvider, SectionHeader } from '@janso/ui';
import { AuditEvents } from './AuditEvents';
import { useCompanyPermission } from '../lib/company-access';

/** Load central evidence on demand, with the owner and company fixed. */
export function SubjectHistory({ company, entity, id }: { company: string; entity: string; id: string }) {
  const canRead = useCompanyPermission('audit.read', company);
  const canExport = useCompanyPermission('audit.export', company);
  const [open, setOpen] = useState(false);
  if (!canRead) return null;
  return <Card><CardBody>
    <SectionHeader title="Audit history" description="Who changed this record, when, and the evidence retained for each change." />
    <Button variant="ghost" aria-expanded={open} onClick={() => setOpen(value => !value)}>{open ? 'Hide audit history' : 'Show audit history'}</Button>
    {open && <PermissionProvider permissions={canExport ? ['audit.read', 'audit.export'] : ['audit.read']}>
      <AuditEvents key={company + ':' + entity + ':' + id} companyId={company} entityType={entity} entityId={id} />
    </PermissionProvider>}
  </CardBody></Card>;
}
