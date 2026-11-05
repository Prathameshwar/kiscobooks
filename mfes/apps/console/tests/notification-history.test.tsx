import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { NotificationHistory } from '../app/components/notifications/History';
import { ALL_COMPANIES, NotificationScope } from '../app/components/notifications/common';
import { ID } from './notification-fixtures';
vi.mock('../app/components/PlatformHistory', () => ({ PlatformHistory: (props: { entityType: string; entityId: string }) => <p>Platform {props.entityType} {props.entityId}</p> }));
vi.mock('../app/components/AuditEvents', () => ({ AuditEvents: (props: { entityType: string; entityId: string; companyId?: string }) => <p>Tenant {props.entityType} {props.entityId} {props.companyId ?? 'tenant-wide'}</p> }));
function mount(owner: 'platform' | 'tenant', permissions: string[], companyId?: string) {
  render(<NotificationScope owner={owner} permissions={permissions} query={new URLSearchParams()}>
    <NotificationHistory entity="notification_template" identity={ID} companyId={companyId} />
  </NotificationScope>);
}
it('uses the existing platform history boundary for an exact notification entity', () => {
  mount('platform', ['platform.notification_template.read']);
  expect(screen.getByText(`Platform notification.notification_template ${ID}`)).toBeVisible();
  expect(screen.queryByText(/Tenant/)).not.toBeInTheDocument();
});
it('loads tenant audit only on demand and removes the all-company sentinel', () => {
  mount('tenant', ['notification.template.read', 'audit.read'], ALL_COMPANIES);
  expect(screen.queryByText(/Tenant/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Show history' }));
  expect(screen.getByText(`Tenant notification.notification_template ${ID} tenant-wide`)).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Hide history' }));
  expect(screen.queryByText(/Tenant/)).not.toBeInTheDocument();
});
it('retains a real company scope and requires the separate tenant audit grant', () => {
  mount('tenant', ['notification.template.read'], ID);
  expect(screen.queryByRole('button', { name: 'Show history' })).not.toBeInTheDocument();
});
it('passes the company reference to an authorized tenant audit view', () => {
  mount('tenant', ['audit.read'], ID);
  fireEvent.click(screen.getByRole('button', { name: 'Show history' }));
  expect(screen.getByText(`Tenant notification.notification_template ${ID} ${ID}`)).toBeVisible();
});
