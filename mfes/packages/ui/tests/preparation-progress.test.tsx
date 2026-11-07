import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { Button } from '../src/components/Button';
import { PreparationProgress } from '../src/components/PreparationProgress';

it('keeps panel milestones outside the progressbar and marks the current stage', () => {
  const view = render(<PreparationProgress variant="panel" label="Creation progress" title="Creating" detail="Saving prices."
    steps={[{ label: 'Details', state: 'done' }, { label: 'Prices', state: 'current' }]} />);
  expect(screen.getByRole('region')).toHaveAttribute('data-variant', 'panel');
  expect(screen.getByText('Prices')).toHaveAttribute('aria-current', 'step');
  expect(screen.getByRole('progressbar')).not.toContainElement(screen.getByRole('list'));
  view.rerender(<PreparationProgress variant="panel" label="Creation progress" title="Created" detail="Ready." complete active={false} />);
  expect(screen.getByRole('region')).toHaveAttribute('data-complete', 'true');
  expect(screen.queryByRole('progressbar')).toBeNull();
});

it('announces current work without claiming a measured percentage', () => {
  render(<PreparationProgress label="Company creation progress" title="Saving your company" detail="Waiting for confirmation." />);
  expect(screen.getByRole('region', { name: 'Company creation progress' })).toBeVisible();
  expect(screen.getByRole('status')).toHaveTextContent('Saving your companyWaiting for confirmation.');
  const progress = screen.getByRole('progressbar', { name: 'Saving your company' });
  expect(progress).toHaveAttribute('aria-valuetext', 'Waiting for confirmation.');
  expect(progress).not.toHaveAttribute('aria-valuenow');
});

it('updates its announcement and retains optional controls and stage evidence', () => {
  const stop = vi.fn();
  const view = render(<PreparationProgress label="Report progress" title="Queued" detail="Waiting for a worker."
    steps={[{ label: 'Accounting data', state: 'done' }, { label: 'In queue', state: 'current' }]}
    action={<Button onClick={stop}>Stop</Button>} />);
  expect(screen.getByText('Accounting data')).toHaveAttribute('data-state', 'done');
  fireEvent.click(screen.getByRole('button', { name: 'Stop' }));
  expect(stop).toHaveBeenCalledOnce();
  view.rerender(<PreparationProgress label="Report progress" title="Report stopped" detail="Run again when ready." active={false} />);
  expect(screen.getByRole('status')).toHaveTextContent('Report stopped');
  expect(screen.queryByRole('progressbar')).toBeNull();
  expect(screen.queryByRole('button')).toBeNull();
});

it('scrolls new work into view when requested without jumping on every status update', () => {
  const view = render(<PreparationProgress label="Company progress" title="Saving" detail="Saving your company." />);
  const scroll = vi.fn();
  screen.getByRole('region').scrollIntoView = scroll;
  view.rerender(<PreparationProgress autoScroll label="Company progress" title="Checking setup" detail="Checking the saved steps." />);
  expect(scroll).toHaveBeenCalledWith({ block: 'nearest' });
  view.rerender(<PreparationProgress autoScroll label="Company progress" title="Preparing books" detail="1 of 8 steps ready." />);
  expect(scroll).toHaveBeenCalledOnce();
});
