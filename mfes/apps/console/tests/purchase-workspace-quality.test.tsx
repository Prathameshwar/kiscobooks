import { memo } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { PurchaseWorkflowWorkspace } from '../app/components/PurchaseWorkflowWorkspace';
import { purchaseExample } from '../app/lib/purchase-workspace';
const counts = vi.hoisted(() => ({ formattingBroadcasts: 0 }));
vi.mock('@janso/ui', async load => {
  const ui = await load<typeof import('@janso/ui')>();
  const Probe = memo(() => { ui.useDisplayConfig(); counts.formattingBroadcasts += 1; return null; });
  return { ...ui, EntryGrid: (props: Parameters<typeof ui.EntryGrid>[0]) => <><Probe /><ui.EntryGrid {...props} /></> };
});
it('does not broadcast a new formatting context to every grid cell when only invoice text changes', async () => {
  render(<PurchaseWorkflowWorkspace context={{ company: 'test', year: '2026' }} permissions={{ create: true, edit: true, submit: true }} today="2026-10-31" initialDraft={purchaseExample('2026-10-31')} />);
  const before = counts.formattingBroadcasts;
  await userEvent.type(screen.getByLabelText(/Supplier invoice number/), '-A');
  expect(counts.formattingBroadcasts).toBe(before);
});
it('names document/action groups and labels the controls without naming generic anchor spans', () => {
  const { container } = render(<PurchaseWorkflowWorkspace context={{ company: 'test', year: '2026' }} permissions={{ create: true, edit: true, submit: true }} today="2026-10-31" initialDraft={purchaseExample('2026-10-31')} />);
  expect(container.querySelector('span[data-entry-row][aria-label]')).toBeNull();
  expect(screen.getByRole('group', { name: 'Current purchase bill' })).toHaveTextContent('PC-261034');
  expect(screen.getByRole('group', { name: 'Purchase actions' })).toBeInTheDocument();
  expect(screen.getByRole('combobox', { name: 'Item, line 1' })).toBeInTheDocument();
});
