'use client';

import { ActionCard, AuditIcon, PageHeader, PageNavigation, ReceiptIcon } from '@janso/ui';

export function LogsAndActivities({ canAudit, canActivity }: { canAudit: boolean; canActivity: boolean }) {
  return <div className="janso-page">
    <PageNavigation back={{ href: '/', label: 'business overview' }} breadcrumbs={[{ label: 'Business overview', href: '/' }, { label: 'Logs and activities' }]} />
    <PageHeader overline="Administer" title="Logs and activities" lede="Review audit evidence and recent changes for the company currently open." />
    <section aria-labelledby="history-views-title">
    <h2 id="history-views-title" className="janso-visually-hidden">Choose a history view</h2>
    <div className="janso-action-card-grid">
      <ActionCard title="Audit logs" description="Inspect recorded changes, compare before and after values, and export authorized audit evidence."
        icon={<AuditIcon />} actionLabel="Open audit logs" {...(canAudit ? { href: '/audit' } : { disabledReason: 'Audit read access is required for this company.' })} />
      <ActionCard title="Activities" description="Follow recent company changes and open the related audit history when your access allows it."
        icon={<ReceiptIcon />} actionLabel="Open activities" {...(canActivity ? { href: '/activity' } : { disabledReason: 'Activity read access is required for this company.' })} />
    </div>
    </section>
  </div>;
}
