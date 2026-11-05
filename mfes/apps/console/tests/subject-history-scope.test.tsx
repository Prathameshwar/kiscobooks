import { fireEvent, render, screen } from '@testing-library/react';
import { ThemeSwitcher, useCan } from '@janso/ui';
import { expect, it, vi } from 'vitest';
import { Providers } from '../app/providers';
import { SubjectHistory } from '../app/components/SubjectHistory';
import { sessionFor } from './helpers';

vi.mock('../app/components/AuditEvents', () => ({ AuditEvents: () => { const canExport = useCan('audit.export'); return <><p>Evidence</p>{canExport && <button>Export evidence</button>}</>; } }));
const company = '01990000-0000-7000-8000-000000000001';
it('retains scoped access when changing an initially unset theme', async () => {
  const session = await sessionFor({ permissions: ['audit.read'], theme: null });
  session.grants = [{ scope_type: 'tenant', scope_id: null, permissions: ['audit.read'], valid_from: '2000-01-01', valid_to: null }];
  render(<Providers session={session}><ThemeSwitcher /><SubjectHistory company={company} entity="vouchers.type" id={company} /></Providers>);
  fireEvent.click(screen.getByRole('radio', { name: 'Dark' }));
  expect(screen.getByRole('radio', { name: 'Dark' })).toHaveAttribute('aria-checked', 'true');
  expect(screen.getByRole('button', { name: 'Show audit history' })).toBeVisible();
});
it('denies missing ambient authority and an empty record company', async () => {
  const view = render(<SubjectHistory company={company} entity="vouchers.type" id={company} />);
  expect(screen.queryByRole('button')).not.toBeInTheDocument(); view.unmount();
  const session = await sessionFor({ permissions: ['audit.read'] });
  session.grants = [{ scope_type: 'tenant', scope_id: null, permissions: ['audit.read'], valid_from: '2000-01-01', valid_to: null }];
  render(<Providers session={session}><SubjectHistory company="" entity="vouchers.type" id={company} /></Providers>);
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
});
it.each(['other-company', 'expired', 'future', 'department', 'missing'])('hides record audit history for %s authority', async scenario => {
  const session = await sessionFor({ permissions: ['audit.read'] });
  session.company = { id: company, name: 'QA' };
  session.grants = scenario === 'missing' ? [] : [{
    scope_type: scenario === 'department' ? 'department' : 'company',
    scope_id: scenario === 'other-company' ? '01990000-0000-7000-8000-000000000002' : company,
    permissions: ['audit.read'], valid_from: scenario === 'future' ? '2999-01-01' : '2000-01-01',
    valid_to: scenario === 'expired' ? '2001-01-01' : null,
  }];
  render(<Providers session={session}><SubjectHistory company={company} entity="vouchers.type" id={company} /></Providers>);
  expect(screen.queryByRole('button', { name: 'Show audit history' })).not.toBeInTheDocument();
});
it.each(['tenant', 'company'] as const)('shows record audit history for a current %s grant', async scope_type => {
  const session = await sessionFor({ permissions: ['audit.read'] });
  session.company = { id: company, name: 'QA' };
  session.grants = [{ scope_type, scope_id: scope_type === 'tenant' ? null : company, permissions: ['audit.read'], valid_from: '2000-01-01', valid_to: null }];
  render(<Providers session={session}><SubjectHistory company={company} entity="vouchers.type" id={company} /></Providers>);
  expect(screen.getByRole('button', { name: 'Show audit history' })).toBeVisible();
});
it.each([false, true])('scopes audit export independently of record read access (%s)', async allowed => {
  const session = await sessionFor({ permissions: ['audit.read', 'audit.export'] });
  session.company = { id: company, name: 'QA' };
  session.grants = [
    { scope_type: 'company', scope_id: company, permissions: ['audit.read'], valid_from: '2000-01-01', valid_to: null },
    { scope_type: 'company', scope_id: allowed ? company : '01990000-0000-7000-8000-000000000002', permissions: ['audit.export'], valid_from: '2000-01-01', valid_to: null },
  ];
  render(<Providers session={session}><SubjectHistory company={company} entity="vouchers.type" id={company} /></Providers>);
  fireEvent.click(screen.getByRole('button', { name: 'Show audit history' }));
  expect(!!screen.queryByRole('button', { name: 'Export evidence' })).toBe(allowed);
});
