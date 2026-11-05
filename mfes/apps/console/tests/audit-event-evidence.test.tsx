import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { AuditEventPanel } from '../app/components/AuditEventPanel';
import { getAuditTrail } from '../app/lib/audit-trail';
import { normalizeChanges } from '../app/lib/audit-api';

it('distinguishes missing historical evidence from a recorded null', async () => {
  const trail = await getAuditTrail();
  const event = trail.events[0]!;
  render(<AuditEventPanel event={event} load={async () => ({ ...trail.details[event.id]!, changes: normalizeChanges({ status: 'ACTIVE', prior: { from: 'DRAFT' }, created: { from: null, to: 'yes' } }) })} />);
  await screen.findByText('ACTIVE');
  expect(screen.getByRole('row', { name: 'status Not recorded ACTIVE' })).toBeVisible();
  expect(screen.getByRole('row', { name: 'prior DRAFT Not recorded' })).toBeVisible();
  expect(screen.getByRole('row', { name: 'created yes' })).toBeVisible();
});
