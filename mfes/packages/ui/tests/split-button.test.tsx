import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { SplitButton } from '../src/components/SplitButton';
import { PermissionProvider } from '../src/lib/permissions';

const primary = {
  id: 'edit',
  label: 'Edit product',
  href: '/products/one/edit',
};
const items = [
  { id: 'barcodes', label: 'Barcodes' },
  { id: 'family', label: 'Family', href: '/families/one' },
];

it('retains ordinary primary links and keyboard navigation in the portalled menu', async () => {
  const user = userEvent.setup(),
    onSelect = vi.fn();
  const { container } = render(
    <SplitButton
      label="Related actions"
      primary={primary}
      items={items}
      onSelect={onSelect}
    />,
  );
  expect(screen.getByRole('link', { name: 'Edit product' })).toHaveAttribute(
    'href',
    primary.href,
  );
  const trigger = screen.getByRole('button', { name: 'Related actions' });
  trigger.focus();
  await user.keyboard('{ArrowDown}');
  expect(screen.getByRole('menuitem', { name: 'Barcodes' })).toHaveFocus();
  expect(container).not.toContainElement(screen.getByRole('menu'));
  await user.keyboard('{ArrowUp}');
  expect(screen.getByRole('menuitem', { name: 'Family' })).toHaveFocus();
  await user.keyboard('{Escape}');
  expect(trigger).toHaveFocus();
  await user.click(trigger);
  await user.click(screen.getByRole('menuitem', { name: 'Barcodes' }));
  expect(onSelect).toHaveBeenCalledTimes(1);
  expect(onSelect).toHaveBeenCalledWith('barcodes');
  expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
});

it('calls commands from the primary button without submitting an enclosing form', async () => {
  const onSelect = vi.fn(),
    submit = vi.fn();
  render(
    <form onSubmit={submit}>
      <SplitButton
        label="Actions"
        primary={{ id: 'save', label: 'Save' }}
        items={[]}
        onSelect={onSelect}
      />
    </form>,
  );
  await userEvent.click(screen.getByRole('button', { name: 'Save' }));
  expect(onSelect).toHaveBeenCalledTimes(1);
  expect(onSelect).toHaveBeenCalledWith('save');
  expect(submit).not.toHaveBeenCalled();
  expect(
    screen.queryByRole('button', { name: 'Actions' }),
  ).not.toBeInTheDocument();
});

it('guards both primary and supplementary navigation while preserving their link destinations', async () => {
  const onNavigate = vi.fn((event) => event.preventDefault()),
    onSelect = vi.fn();
  render(
    <SplitButton
      label="Actions"
      primary={primary}
      items={items}
      onSelect={onSelect}
      onNavigate={onNavigate}
    />,
  );
  await userEvent.click(screen.getByRole('link', { name: 'Edit product' }));
  await userEvent.click(screen.getByRole('button', { name: 'Actions' }));
  await userEvent.click(screen.getByRole('menuitem', { name: 'Family' }));
  expect(onNavigate).toHaveBeenCalledTimes(2);
  expect(onSelect).not.toHaveBeenCalled();
});

it('explains and blocks every action while a draft needs attention', async () => {
  const onSelect = vi.fn();
  render(
    <SplitButton
      label="Actions"
      primary={primary}
      items={items}
      disabledReason="Save your draft first"
      onSelect={onSelect}
    />,
  );
  expect(screen.getByRole('button', { name: 'Edit product' })).toBeDisabled();
  expect(
    screen.queryByRole('link', { name: 'Edit product' }),
  ).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Actions' }));
  for (const item of screen.getAllByRole('menuitem')) {
    expect(item).toHaveAttribute('aria-disabled', 'true');
    expect(item).not.toHaveAttribute('href');
    await userEvent.click(item);
  }
  expect(onSelect).not.toHaveBeenCalled();
  expect(screen.getAllByText('Save your draft first')).toHaveLength(2);
});

it('disables both halves while a request is pending', () => {
  render(
    <SplitButton
      label="Actions"
      primary={primary}
      items={items}
      loading
      loadingLabel="Saving"
      onSelect={vi.fn()}
    />,
  );
  expect(screen.getByRole('button', { name: 'Saving' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Actions' })).toBeDisabled();
  expect(screen.queryByRole('link')).not.toBeInTheDocument();
});

it('exposes the face state so the caret is styled to match it', () => {
  const props = { label: 'Actions', primary, items, onSelect: vi.fn() };
  const { rerender } = render(<SplitButton {...props} />);
  const group = screen.getByRole('group', { name: 'Actions' });
  expect(group).not.toHaveAttribute('data-state');
  rerender(<SplitButton {...props} disabledReason="Wait" />);
  expect(group).toHaveAttribute('data-state', 'blocked');
  expect(screen.getByRole('button', { name: 'Actions' })).toBeEnabled();
  rerender(<SplitButton {...props} disabledReason="Wait" loading />);
  expect(group).toHaveAttribute('data-state', 'busy');
});

it('filters denied and unsafe actions and omits empty menus and duplicate primary actions', async () => {
  const { rerender } = render(
    <PermissionProvider permissions={[]}>
      <SplitButton
        label="Actions"
        primary={primary}
        items={[
          primary,
          { id: 'deny', label: 'Denied', permission: 'item.update' },
          { id: 'unsafe', label: 'Unsafe', href: 'javascript:alert(1)' },
        ]}
        onSelect={vi.fn()}
      />
    </PermissionProvider>,
  );
  expect(
    screen.queryByRole('button', { name: 'Actions' }),
  ).not.toBeInTheDocument();
  rerender(
    <SplitButton
      label="Actions"
      primary={{ ...primary, permission: 'item.update' }}
      items={items}
      onSelect={vi.fn()}
    />,
  );
  expect(
    screen.queryByRole('link', { name: 'Edit product' }),
  ).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: /Actions/ }));
  expect(screen.getAllByRole('menuitem')).toHaveLength(2);
  rerender(
    <SplitButton
      label="Actions"
      primary={{ ...primary, href: '//outside.invalid' }}
      items={[]}
      onSelect={vi.fn()}
    />,
  );
  expect(screen.queryByRole('group')).not.toBeInTheDocument();
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
});
