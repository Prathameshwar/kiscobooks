import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { Button } from '../src/components/Button';
import { FormActions, FormLayout } from '../src/components/FormLayout';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

it('places the form beside a context card when an aside is supplied', () => {
  const { container } = render(
    <FormLayout aside={<p>Changes are audited.</p>}>
      <form aria-label="Edit tenant" />
    </FormLayout>,
  );
  expect(container.firstElementChild).toHaveClass('janso-grid', 'janso-grid--split', 'janso-grid--start');
  expect(screen.getByRole('form', { name: 'Edit tenant' })).toBeInTheDocument();
  expect(screen.getByText('Changes are audited.')).toBeInTheDocument();
  expect(container.querySelector('.janso-card')).toBeInTheDocument();
});

it('keeps a single column and renders no empty card without an aside', () => {
  const { container } = render(
    <FormLayout>
      <form aria-label="Edit tenant" />
    </FormLayout>,
  );
  expect(container.firstElementChild).toHaveClass('janso-form-layout');
  expect(container.firstElementChild).not.toHaveClass('janso-grid--split');
  expect(container.querySelector('.janso-card')).not.toBeInTheDocument();
});

it('renders a cancel link beside the committing action and defaults its label', () => {
  render(
    <FormActions cancel={{ href: '/platform/tenants' }}>
      <Button type="submit">Save changes</Button>
    </FormActions>,
  );
  expect(screen.getByRole('link', { name: 'Cancel' })).toHaveAttribute('href', '/platform/tenants');
  expect(screen.getByRole('button', { name: 'Save changes' })).toBeInTheDocument();
});

it('uses the supplied cancel label and reports the click so an editor can confirm a discard', async () => {
  const onClick = vi.fn();
  render(<FormActions cancel={{ href: '/platform/tenants', label: 'Back to tenants', onClick }} />);
  await userEvent.click(screen.getByRole('link', { name: 'Back to tenants' }));
  expect(onClick).toHaveBeenCalledTimes(1);
});

it('refuses an unsafe cancel destination rather than rendering a dead link', () => {
  render(
    <FormActions cancel={{ href: 'javascript:alert(1)', label: 'Cancel' }}>
      <Button type="submit">Save</Button>
    </FormActions>,
  );
  expect(screen.queryByRole('link')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument();
});

it('right-aligns the actions when there is nothing to cancel to', () => {
  const { container } = render(
    <FormActions>
      <Button type="submit">Save</Button>
    </FormActions>,
  );
  expect(container.querySelector('.janso-form-actions')).toBeInTheDocument();
  expect(container.querySelector('.janso-card__footer')?.firstElementChild).toHaveClass('janso-form-actions');
});

it('supports a non-navigating inline cancel button and disables it while saving', async () => {
  const onCancel = vi.fn();
  const view = render(<FormActions cancel={{ onCancel, label: 'Cancel edits' }}><Button type="submit">Save</Button></FormActions>);
  const cancel = screen.getByRole('button', { name: 'Cancel edits' });
  expect(cancel).toHaveAttribute('type', 'button');
  await userEvent.click(cancel);
  expect(onCancel).toHaveBeenCalledTimes(1);
  view.rerender(<FormActions cancel={{ onCancel, label: 'Cancel edits', disabled: true }} />);
  expect(screen.getByRole('button', { name: 'Cancel edits' })).toBeDisabled();
});

it('allows a form footer to wrap Cancel and a long submit action within a narrow card', () => {
  const styles = readFileSync(join(__dirname, '..', 'src', 'styles', 'janso-ui.css'), 'utf8');
  expect(styles).toMatch(/\.janso-card__footer:has\(> \.janso-form-actions\)\s*\{[^}]*flex-wrap:\s*wrap/s);
});
