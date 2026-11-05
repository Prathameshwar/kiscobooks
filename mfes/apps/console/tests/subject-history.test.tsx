import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { Providers } from '../app/providers';
import { sessionFor } from './helpers';
import { SubjectHistory } from '../app/components/SubjectHistory';

const { audit } = vi.hoisted(() => ({ audit: vi.fn() }));
vi.mock('../app/components/AuditEvents', () => ({ AuditEvents: (props: object) => { audit(props); return <p>Central evidence</p>; } }));
beforeEach(() => audit.mockClear());

it('does not request history without audit permission', async () => {
  render(<Providers session={await sessionFor({ permissions: [] })}><SubjectHistory company="company" entity="catalog.item" id="item" /></Providers>);
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
  expect(audit).not.toHaveBeenCalled();
});

it('loads fixed company and subject filters only when opened', async () => {
  const session = await sessionFor({ permissions: ['audit.read'] });
  session.grants = [{ scope_type: 'company', scope_id: 'company', permissions: ['audit.read'], valid_from: '2000-01-01', valid_to: null }];
  render(<Providers session={session}><SubjectHistory company="company" entity="catalog.item" id="item" /></Providers>);
  expect(audit).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Show audit history' }));
  expect(audit).toHaveBeenLastCalledWith(expect.objectContaining({ companyId: 'company', entityType: 'catalog.item', entityId: 'item' }));
  fireEvent.click(screen.getByRole('button', { name: 'Hide audit history' }));
  expect(screen.queryByText('Central evidence')).not.toBeInTheDocument();
});
