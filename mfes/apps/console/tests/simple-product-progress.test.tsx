import { render, screen, within } from '@testing-library/react';
import { expect, it } from 'vitest';
import { SimpleProductProgress } from '../app/components/SimpleProductProgress';

const job = { status: 'RUNNING' as const, step: 'CREATE', code: 'TEA123', opening_posted: false };

it('shows a prominent pending panel before the first server response', () => {
  render(<SimpleProductProgress busy />);
  expect(screen.getByRole('region', { name: 'Product creation progress' })).toHaveAttribute('data-variant', 'panel');
  expect(screen.getByRole('progressbar', { name: 'Creating your product' })).not.toHaveAttribute('aria-valuenow');
  expect(screen.getByText('Product details')).toHaveAttribute('aria-current', 'step');
  expect(screen.getByText('Ready to use')).toHaveAttribute('data-state', 'waiting');
});

it.each(['NUMERIC', 'MRP', 'PUBLISH', 'ACTIVATE', 'BATCH', 'BATCH_PRICES', 'SERIAL', 'OPENING', 'SOURCE', 'VOUCHER', 'SUBMIT', 'ISSUE', 'POST', 'FINALIZE'])('uses server stage %s and leaves readiness unconfirmed', step => {
  render(<SimpleProductProgress busy job={{ ...job, step }} tracking opening />);
  const region = screen.getByRole('region', { name: 'Product creation progress' });
  expect(within(region).getByText('Product details')).toHaveAttribute('data-state', 'done');
  expect(within(region).getByText('Ready to use')).toHaveAttribute('data-state', 'waiting');
  expect(region.querySelectorAll('[aria-current="step"]')).toHaveLength(1);
});

it('shows automatic waiting without presenting it as a failure', () => {
  const view = render(<SimpleProductProgress busy job={{ ...job, step: 'POST' }} opening waitingForStock />);
  expect(screen.getByRole('status')).toHaveTextContent('Waiting for stock confirmation');
  expect(screen.getByRole('status')).toHaveTextContent('resume automatically');
  view.rerender(<SimpleProductProgress busy job={{ ...job, step: 'PUBLISH' }} waitingForPricing />);
  expect(screen.getByRole('status')).toHaveTextContent('Refreshing product prices');
});

it('retains completed evidence when paused and offers a clear next action', () => {
  render(<SimpleProductProgress job={{ ...job, step: 'POST' }} opening failed />);
  expect(screen.queryByRole('progressbar')).toBeNull();
  expect(screen.getByRole('status')).toHaveTextContent('Creation needs attention');
  expect(screen.getByRole('status')).toHaveTextContent('Continue creation');
  expect(screen.getByText('Activation')).toHaveAttribute('data-state', 'done');
  expect(screen.getByText('Opening stock')).toHaveAttribute('data-state', 'current');
});

it('does not claim stage completion for an unknown server stage or failed initial request', () => {
  const view = render(<SimpleProductProgress busy job={{ ...job, step: 'FUTURE_STAGE' }} />);
  expect(screen.queryByText('Activation')).toBeNull();
  expect(screen.getByText('Confirming progress')).toHaveAttribute('data-state', 'current');
  view.rerender(<SimpleProductProgress failed />);
  expect(screen.getByRole('status')).toHaveTextContent('Continue creation');
  expect(screen.getByText('Product details')).toHaveAttribute('data-state', 'current');
});

it('announces completion only from server confirmation and omits unused stock stages', () => {
  render(<SimpleProductProgress job={{ ...job, status: 'COMPLETE', step: 'COMPLETE' }} />);
  expect(screen.getByRole('status')).toHaveTextContent('Product TEA123 is active and ready.');
  expect(screen.queryByRole('progressbar')).toBeNull();
  expect(screen.queryByText('Opening stock')).toBeNull();
  expect(screen.queryByText('Batches and serials')).toBeNull();
  expect(screen.getByText('Ready to use')).toHaveAttribute('data-state', 'done');
});

it('reports posted stock only when the server confirms it', () => {
  render(<SimpleProductProgress job={{ ...job, status: 'COMPLETE', step: 'COMPLETE', opening_posted: true }} opening />);
  expect(screen.getByRole('status')).toHaveTextContent('Opening stock has been posted.');
});

it('explains saved recovery and correction without animating inactive work', () => {
  const view = render(<SimpleProductProgress job={{ ...job, last_error: 'Check the product tax setup.' }} />);
  expect(screen.getByRole('status')).toHaveTextContent('Creation is saved');
  expect(screen.getByRole('status')).toHaveTextContent('Check the product tax setup.');
  expect(screen.queryByRole('progressbar')).toBeNull();
  view.rerender(<SimpleProductProgress job={job} editing />);
  expect(screen.getByRole('status')).toHaveTextContent('Save corrected product');
  view.rerender(<SimpleProductProgress job={job} editing busy />);
  expect(screen.getByRole('status')).toHaveTextContent('Creating your product');
});
