import { render, screen, within } from '@testing-library/react';
import { expect, it } from 'vitest';
import type { components } from '@janso/api-client/catalog';
import { AdvancedCreationFeedback, advancedReadinessMessage } from '../app/components/AdvancedCreationFeedback';

type Status = components['schemas']['AdvancedDefinitionStatus'];
const skus = [{ sku: 'TEA-SMALL', name: 'Small pack' }, { sku: 'TEA-LARGE', name: 'Large pack' }];
const status = (first = {}, second = {}, complete = false) => ({ id: 'creation', company_id: 'company', family_id: 'family', row_version: 1, step: 'SETUP', status: complete ? 'COMPLETE' : 'SETUP', sku_ids: ['one', 'two'], sku_progress: [
  { item_id: 'one', setup_done: true, price_draft_ids: ['price'], published_price_ids: [], activated: false, opening_state: 'NOT_REQUESTED', ...first },
  { item_id: 'two', setup_done: false, price_draft_ids: [], published_price_ids: [], activated: false, opening_state: 'NOT_REQUESTED', ...second },
] }) as Status;

it('shows partial setup without advancing to prices or readiness', () => {
  render(<AdvancedCreationFeedback skus={skus} status={status()} busy message="Saving setup for SKU 2…" />);
  expect(screen.getByRole('region', { name: 'Product creation progress' })).toHaveAttribute('data-variant', 'panel');
  expect(screen.getByText('SKU setup')).toHaveAttribute('aria-current', 'step');
  expect(screen.getByText('Prices')).toHaveAttribute('data-state', 'waiting');
  expect(screen.getByText('1 of 2 SKUs have setup saved.')).toBeVisible();
  const item = screen.getByRole('region', { name: 'TEA-SMALL status' });
  expect(within(item).getByText('Prices awaiting confirmation')).toBeVisible();
});

it.each([
  [{ setup_done: true }, 'Prices'],
  [{ setup_done: true, published_price_ids: ['price'] }, 'Activation'],
  [{ setup_done: true, published_price_ids: ['price'], activated: true }, 'Opening stock'],
])('uses complete receipts before marking the next phase current', (facts, phase) => {
  render(<AdvancedCreationFeedback skus={skus} status={status(facts, facts)} busy message="Working…" />);
  expect(within(screen.getByRole('region', { name: 'Product creation progress' })).getByText(phase)).toHaveAttribute('aria-current', 'step');
  expect(screen.getByText('Ready to use')).toHaveAttribute('data-state', 'waiting');
});

it.each([
  ['profile', 'profile.group_id', 'primary_group', 'Choose the product group.'],
  ['skus', 'skus.1.attributes', 'attribute:private-id', 'Check the required attributes'],
  ['business', 'business.skus.0.tax', 'hsn_required', 'Check the tax classification'],
  ['business', 'business.skus.0.prices', 'required_sale_price', 'Check the required selling prices'],
  ['business', 'business.skus.0', 'future_code', 'Review this setup'],
] as const)('explains %s blockers without exposing raw paths and identifiers', (step, path, code, hint) => {
  const message = advancedReadinessMessage({ step, path, code }, skus);
  expect(message).toContain(hint);
  expect(message).not.toContain(path);
  expect(message).not.toContain(code);
});

it('does not infer setup or prices from missing or mismatched SKU receipts', () => {
  render(<AdvancedCreationFeedback skus={skus} status={{ ...status(), sku_progress: [{ ...status().sku_progress![0]!, item_id: 'wrong' }] }} busy message="Checking…" />);
  expect(screen.getByText('SKU setup')).toHaveAttribute('data-state', 'current');
  expect(screen.getByText('0 of 2 SKUs have setup saved.')).toBeVisible();
});

it('shows readable stock states and pauses animation on failure', () => {
  render(<AdvancedCreationFeedback skus={skus} status={status({ activated: true, opening_state: 'IN_PROGRESS' }, { opening_state: 'SKIPPED' })} failed message="Stock confirmation is delayed." />);
  expect(screen.getByRole('status')).toHaveTextContent('Creation needs attention');
  expect(screen.queryByRole('progressbar')).toBeNull();
  expect(screen.getByText('Stock posting in progress')).toBeVisible();
  expect(screen.getByText('No opening stock requested')).toBeVisible();
});

it('holds readiness until native completion, then confirms success', () => {
  const facts = { setup_done: true, published_price_ids: ['price'], activated: true, opening_state: 'POSTED' };
  const view = render(<AdvancedCreationFeedback skus={skus} status={status(facts, facts)} busy message="Confirming…" />);
  expect(screen.getByText('Ready to use')).toHaveAttribute('data-state', 'current');
  view.rerender(<AdvancedCreationFeedback skus={skus} status={status(facts, facts, true)} message="Product Profile and all requested SKUs are complete." />);
  expect(screen.getByRole('status')).toHaveTextContent('Product created successfully');
  expect(screen.getByText('Ready to use')).toHaveAttribute('data-state', 'done');
  expect(screen.queryByRole('progressbar')).toBeNull();
  expect(screen.getAllByText('Opening stock posted')).toHaveLength(2);
});
