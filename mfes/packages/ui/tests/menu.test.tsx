/**
 * `Menu` — the row kebab and the toolbar overflow.
 *
 * Three things here are load-bearing and each has a test that would fail loudly if it regressed:
 * the keyboard contract (a `role="menu"` that does not cycle or return focus is worse than a
 * plain list), the portal (an in-flow panel is clipped by the table's horizontal scroller), and
 * permission filtering (a menu is where a row's conditional verbs live).
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it, vi } from 'vitest';

import { Menu, type MenuItem } from '../src/components/Menu';
import { PermissionProvider } from '../src/lib/permissions';
import { ColumnsIcon, EditIcon, TrashIcon } from '../src/components/icons-table';

const OVERLAY_CSS = readFileSync(join(__dirname, '..', 'src', 'styles', 'overlay.css'), 'utf8');

const ITEMS: readonly MenuItem[] = [
  { id: 'view', label: 'View' },
  { id: 'edit', label: 'Edit', icon: <EditIcon size={16} /> },
  { id: 'delete', label: 'Delete', icon: <TrashIcon size={16} />, destructive: true },
];

function open(items: readonly MenuItem[] = ITEMS, extra: Partial<Parameters<typeof Menu>[0]> = {}) {
  const onSelect = vi.fn();
  const view = render(<Menu label="Row actions" items={items} onSelect={onSelect} {...extra} />);
  return { ...view, onSelect, trigger: screen.getByRole('button', { name: 'Row actions' }) };
}

const items = () => screen.getAllByRole('menuitem');

it('loads contextual actions only when opened, including keyboard opening', async () => {
  const onOpen = vi.fn();
  const { trigger } = open(ITEMS, { onOpen });
  expect(onOpen).not.toHaveBeenCalled();
  await userEvent.click(trigger);
  expect(onOpen).toHaveBeenCalledTimes(1);
  await userEvent.keyboard('{Escape}');
  expect(onOpen).toHaveBeenCalledTimes(1);
  trigger.focus();
  await userEvent.keyboard('{ArrowDown}');
  expect(onOpen).toHaveBeenCalledTimes(2);
  expect(screen.getByRole('menuitem', { name: 'View' })).toHaveFocus();
});

it('renders safe navigation as actual links and excludes unsafe destinations', async () => {
  const user = userEvent.setup(); const { trigger, onSelect } = open([
    { id: 'years', label: 'Manage years', href: '/companies/company-a/years' },
    { id: 'bad', label: 'Unsafe', href: 'javascript:alert(1)' },
  ]);
  await user.click(trigger);
  const link = screen.getByRole('menuitem', { name: 'Manage years' });
  expect(link.tagName).toBe('A'); expect(link).toHaveAttribute('href', '/companies/company-a/years');
  expect(link).toHaveFocus(); expect(screen.queryByText('Unsafe')).not.toBeInTheDocument();
  expect(onSelect).not.toHaveBeenCalled();
});
it('prevents disabled navigation while retaining its reason and focus', async () => {
  const user = userEvent.setup(); const { trigger, onSelect } = open([{ id: 'year', label: 'Year', href: '/years', disabledReason: 'Unavailable' }]);
  await user.click(trigger); await user.click(screen.getByRole('menuitem'));
  expect(screen.getByRole('menuitem')).toHaveAttribute('aria-disabled', 'true');
  expect(screen.getByRole('menuitem')).not.toHaveAttribute('href');
  expect(screen.getByRole('menu')).toBeVisible(); expect(onSelect).not.toHaveBeenCalled();
});

describe('Menu trigger', () => {
  it('is a named icon button that advertises its popup', () => {
    const { trigger } = open();
    expect(trigger).toHaveAttribute('aria-haspopup', 'menu');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('opens on click with focus on the first item', async () => {
    const user = userEvent.setup();
    const { trigger } = open();

    await user.click(trigger);

    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('menu', { name: 'Row actions' })).toBeInTheDocument();
    expect(items()[0]).toHaveFocus();
  });

  it('opens on ArrowDown at the first item and on ArrowUp at the last', async () => {
    const user = userEvent.setup();
    const { trigger } = open();

    trigger.focus();
    await user.keyboard('{ArrowDown}');
    expect(items()[0]).toHaveFocus();

    await user.keyboard('{Escape}');
    await user.keyboard('{ArrowUp}');
    expect(items()[2]).toHaveFocus();
  });

  it('closes again when clicked while open', async () => {
    const user = userEvent.setup();
    const { trigger } = open();

    await user.click(trigger);
    await user.click(trigger);

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('renders a labelled trigger with a caret when given trigger text', async () => {
    const user = userEvent.setup();
    render(
      <Menu
        label="Choose columns"
        triggerLabel="Columns"
        icon={<ColumnsIcon size={16} />}
        items={ITEMS}
        onSelect={vi.fn()}
      />,
    );

    const trigger = screen.getByRole('button', { name: /Columns/ });
    expect(trigger).toHaveClass('janso-menu__trigger');
    await user.click(trigger);
    expect(screen.getByRole('menu', { name: 'Choose columns' })).toBeInTheDocument();
  });
});

describe('Menu keyboard model', () => {
  it('keeps one tab stop — only the active item is reachable by Tab', async () => {
    const user = userEvent.setup();
    const { trigger } = open();
    await user.click(trigger);

    expect(items().map((item) => item.getAttribute('tabindex'))).toEqual(['0', '-1', '-1']);
  });

  it('cycles with the arrow keys in both directions', async () => {
    const user = userEvent.setup();
    const { trigger } = open();
    await user.click(trigger);

    await user.keyboard('{ArrowDown}');
    expect(items()[1]).toHaveFocus();
    await user.keyboard('{ArrowDown}{ArrowDown}');
    expect(items()[0]).toHaveFocus();
    await user.keyboard('{ArrowUp}');
    expect(items()[2]).toHaveFocus();
  });

  it('jumps to the ends with Home and End', async () => {
    const user = userEvent.setup();
    const { trigger } = open();
    await user.click(trigger);

    await user.keyboard('{End}');
    expect(items()[2]).toHaveFocus();
    await user.keyboard('{Home}');
    expect(items()[0]).toHaveFocus();
  });

  it('closes on Escape and returns focus to the trigger', async () => {
    const user = userEvent.setup();
    const { trigger } = open();
    await user.click(trigger);

    await user.keyboard('{Escape}');

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('closes on Tab and hands focus back to the trigger, not to the end of the body', async () => {
    const user = userEvent.setup();
    render(
      <>
        <Menu label="Row actions" items={ITEMS} onSelect={vi.fn()} />
        <button type="button">After</button>
      </>,
    );
    const trigger = screen.getByRole('button', { name: 'Row actions' });
    await user.click(trigger);

    await user.tab();

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    // The panel is portalled to the end of the body; without the synchronous focus restore the
    // next tab stop would have been computed from there and this would be `body`.
    expect(screen.getByRole('button', { name: 'After' })).toHaveFocus();
  });

  it('closes on an outside press without stealing focus back', async () => {
    const user = userEvent.setup();
    render(
      <>
        <Menu label="Row actions" items={ITEMS} onSelect={vi.fn()} />
        <button type="button">Elsewhere</button>
      </>,
    );
    const trigger = screen.getByRole('button', { name: 'Row actions' });
    await user.click(trigger);

    await user.click(screen.getByRole('button', { name: 'Elsewhere' }));

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(trigger).not.toHaveFocus();
  });

  it('does not close when its own item is pressed down on', async () => {
    const user = userEvent.setup();
    const { trigger, onSelect } = open();
    await user.click(trigger);

    // The panel is outside the trigger in the DOM, so the outside-press guard has to test it too.
    await user.click(screen.getByRole('menuitem', { name: 'Edit' }));

    expect(onSelect).toHaveBeenCalledWith('edit');
  });
});

describe('Menu selection', () => {
  it('reports the chosen id, closes, and restores focus', async () => {
    const user = userEvent.setup();
    const { trigger, onSelect } = open();
    await user.click(trigger);

    await user.click(screen.getByRole('menuitem', { name: 'View' }));

    expect(onSelect).toHaveBeenCalledWith('view');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('activates by keyboard as well as by pointer', async () => {
    const user = userEvent.setup();
    const { trigger, onSelect } = open();
    await user.click(trigger);

    await user.keyboard('{ArrowDown}{Enter}');

    expect(onSelect).toHaveBeenCalledWith('edit');
  });
});

describe('Menu checkbox items', () => {
  const toggles: readonly MenuItem[] = [
    { id: 'number', label: 'Number', checked: true },
    { id: 'customer', label: 'Customer', checked: false },
    { id: 'reset', label: 'Reset columns' },
  ];

  it('is a menuitemcheckbox carrying its own state', async () => {
    const user = userEvent.setup();
    const { trigger } = open(toggles);
    await user.click(trigger);

    expect(screen.getByRole('menuitemcheckbox', { name: 'Number' })).toBeChecked();
    expect(screen.getByRole('menuitemcheckbox', { name: 'Customer' })).not.toBeChecked();
    // A verb in the same menu stays a verb.
    expect(screen.getByRole('menuitem', { name: 'Reset columns' })).toBeInTheDocument();
  });

  it('stays open when one is chosen, because the reader is setting a set', async () => {
    const user = userEvent.setup();
    const { trigger, onSelect } = open(toggles);
    await user.click(trigger);

    await user.click(screen.getByRole('menuitemcheckbox', { name: 'Customer' }));

    expect(onSelect).toHaveBeenCalledWith('customer');
    expect(screen.getByRole('menu')).toBeInTheDocument();

    // …and a second one can be set without reopening the panel.
    await user.click(screen.getByRole('menuitemcheckbox', { name: 'Number' }));
    expect(onSelect).toHaveBeenCalledWith('number');
    expect(screen.getByRole('menu')).toBeInTheDocument();
  });

  it('closes on a verb in the same menu', async () => {
    const user = userEvent.setup();
    const { trigger } = open(toggles);
    await user.click(trigger);

    await user.click(screen.getByRole('menuitem', { name: 'Reset columns' }));

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('shows the state, so it is not `aria-checked` alone', async () => {
    const user = userEvent.setup();
    const { trigger } = open(toggles);
    await user.click(trigger);

    const on = screen.getByRole('menuitemcheckbox', { name: 'Number' });
    const off = screen.getByRole('menuitemcheckbox', { name: 'Customer' });

    expect(on.querySelector('.janso-menu__item-check svg')).toBeInTheDocument();
    // The slot stays, empty, so the labels of a toggle list do not shift as they are set.
    expect(off.querySelector('.janso-menu__item-check')).toBeInTheDocument();
    expect(off.querySelector('.janso-menu__item-check svg')).toBeNull();
  });

  it('reserves the same width for a checked and an unchecked item', () => {
    expect(OVERLAY_CSS).toMatch(/\.janso-menu__item-check\s*\{[^}]*width: 1\.15rem/);
  });
});

describe('Menu disabled items', () => {
  const withReason: readonly MenuItem[] = [
    { id: 'edit', label: 'Edit', disabledReason: 'Posted documents cannot be edited' },
    { id: 'view', label: 'View' },
  ];

  it('shows the reason and marks the item aria-disabled rather than removing it', async () => {
    const user = userEvent.setup();
    const { trigger } = open(withReason);
    await user.click(trigger);

    const edit = screen.getByRole('menuitem', { name: /Edit/ });
    expect(edit).toHaveAttribute('aria-disabled', 'true');
    expect(edit).not.toBeDisabled();
    expect(within(edit).getByText('Posted documents cannot be edited')).toBeInTheDocument();
  });

  it('keeps the disabled item in the roving order so its reason is discoverable', async () => {
    const user = userEvent.setup();
    const { trigger } = open(withReason);
    await user.click(trigger);

    expect(screen.getByRole('menuitem', { name: /Edit/ })).toHaveFocus();
  });

  it('ignores activation of a disabled item and stays open', async () => {
    const user = userEvent.setup();
    const { trigger, onSelect } = open(withReason);
    await user.click(trigger);

    await user.click(screen.getByRole('menuitem', { name: /Edit/ }));

    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.getByRole('menu')).toBeInTheDocument();
  });
});

describe('Menu permission gating', () => {
  const gated: readonly MenuItem[] = [
    { id: 'view', label: 'View', permission: 'invoice.read' },
    { id: 'post', label: 'Post', permission: 'invoice.post' },
    { id: 'note', label: 'Add note' },
  ];

  const withPermissions = (permissions: readonly string[]) =>
    render(
      <PermissionProvider permissions={permissions}>
        <Menu label="Row actions" items={gated} onSelect={vi.fn()} />
      </PermissionProvider>,
    );

  it('omits an item the actor cannot use — absent, not disabled', async () => {
    const user = userEvent.setup();
    withPermissions(['invoice.read']);

    await user.click(screen.getByRole('button', { name: 'Row actions' }));

    expect(items().map((item) => item.textContent)).toEqual(['View', 'Add note']);
  });

  it('rejects wildcard authority and retains ungated items', async () => {
    const user = userEvent.setup();
    withPermissions(['invoice.*']);

    await user.click(screen.getByRole('button', { name: 'Row actions' }));

    expect(items()).toHaveLength(1);
  });

  it('keeps an ungated item, which the server still authorizes', async () => {
    const user = userEvent.setup();
    withPermissions([]);

    await user.click(screen.getByRole('button', { name: 'Row actions' }));

    expect(items().map((item) => item.textContent)).toEqual(['Add note']);
  });

  it('stops claiming a popup, and does not open, when nothing survives filtering', async () => {
    const user = userEvent.setup();
    render(
      <PermissionProvider permissions={[]}>
        <Menu
          label="Row actions"
          items={[{ id: 'post', label: 'Post', permission: 'invoice.post' }]}
          onSelect={vi.fn()}
        />
      </PermissionProvider>,
    );

    const trigger = screen.getByRole('button', { name: 'Row actions' });
    expect(trigger).not.toHaveAttribute('aria-haspopup');
    expect(trigger).not.toHaveAttribute('aria-expanded');

    await user.click(trigger);
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('does not open when disabled', async () => {
    const user = userEvent.setup();
    const { trigger } = open(ITEMS, { disabled: true });

    await user.click(trigger);

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });
});

describe('Menu structure', () => {
  it('separates the destructive verbs from the ordinary ones', async () => {
    const user = userEvent.setup();
    const { trigger } = open();
    await user.click(trigger);

    const separators = screen.getAllByRole('separator');
    expect(separators).toHaveLength(1);
    expect(screen.getByRole('menuitem', { name: 'Delete' })).toHaveAttribute('data-tone', 'danger');
  });

  it('renders no separator when the destructive item is the only one', async () => {
    const user = userEvent.setup();
    const { trigger } = open([{ id: 'delete', label: 'Delete', destructive: true }]);
    await user.click(trigger);

    expect(screen.queryByRole('separator')).not.toBeInTheDocument();
  });

  it('rules off a band the caller asked for, and ignores one on the first item', async () => {
    const user = userEvent.setup();
    const { trigger } = open([
      { id: 'sales', label: 'Sales', separatorBefore: true },
      { id: 'receipt', label: 'Receipt' },
      { id: 'purchase', label: 'Purchase', separatorBefore: true },
    ]);
    await user.click(trigger);

    expect(screen.getAllByRole('separator')).toHaveLength(1);
    // The rule belongs above "Purchase", so the two sales verbs read as one band.
    const panel = screen.getByRole('menu');
    const order = [...panel.children].map((node) => node.getAttribute('role') ?? node.textContent);
    expect(order).toEqual(['menuitem', 'menuitem', 'separator', 'menuitem']);
  });

  it('does not double a rule when a band starts at the destructive verb', async () => {
    const user = userEvent.setup();
    const { trigger } = open([
      { id: 'edit', label: 'Edit' },
      { id: 'delete', label: 'Delete', destructive: true, separatorBefore: true },
    ]);
    await user.click(trigger);

    expect(screen.getAllByRole('separator')).toHaveLength(1);
  });

  it('hides a band rule when the item that asked for it is filtered out', async () => {
    const user = userEvent.setup();
    render(
      <PermissionProvider permissions={['voucher.read']}>
        <Menu
          label="New"
          items={[
            { id: 'sales', label: 'Sales', permission: 'voucher.read' },
            { id: 'purchase', label: 'Purchase', permission: 'voucher.create', separatorBefore: true },
          ]}
          onSelect={vi.fn()}
        />
      </PermissionProvider>,
    );
    await user.click(screen.getByRole('button', { name: 'New' }));

    expect(screen.queryByRole('separator')).not.toBeInTheDocument();
    expect(items()).toHaveLength(1);
  });

  it('portals the panel to the body, out of any clipping ancestor', async () => {
    const user = userEvent.setup();
    const { container } = render(
      <div style={{ overflowX: 'auto' }}>
        <Menu label="Row actions" items={ITEMS} onSelect={vi.fn()} />
      </div>,
    );

    await user.click(screen.getByRole('button', { name: 'Row actions' }));

    const panel = screen.getByRole('menu');
    expect(container.contains(panel)).toBe(false);
    expect(panel.parentElement).toBe(document.body);
    // Fixed positioning is what makes the portal correct — an absolute panel would scroll away.
    expect(panel).toHaveStyle({ position: 'fixed' });
  });

  it('links the trigger to the panel it controls', async () => {
    const user = userEvent.setup();
    const { trigger } = open();
    await user.click(trigger);

    expect(trigger.getAttribute('aria-controls')).toBe(screen.getByRole('menu').id);
  });

  it('sits at the documented popover stacking level, above the dialog', () => {
    expect(OVERLAY_CSS).toMatch(
      /\.janso-menu__panel\s*\{[^}]*z-index: var\(--janso-z-popover\)/,
    );
  });

  it('lets a disabled item wrap its reason rather than truncating it', () => {
    expect(OVERLAY_CSS).toMatch(/\.janso-menu__item-note\s*\{[^}]*white-space: normal/);
  });
});

/**
 * The bar's leading verb — "New". It is one button with one job: the label and the caret open the
 * same menu, so the split is presentation. What is worth testing is that it keeps the primary fill
 * and the menu contract, that no existing caller gains that fill by default, and that its colour
 * comes from the theme rather than a literal.
 */
describe('Menu primary trigger', () => {
  it('wears the primary fill and the split treatment, and still opens its menu', async () => {
    const user = userEvent.setup();
    render(
      <Menu
        label="New voucher"
        triggerLabel="New"
        triggerVariant="primary"
        icon={<ColumnsIcon size={14} />}
        items={ITEMS}
        onSelect={vi.fn()}
      />,
    );
    const trigger = screen.getByRole('button', { name: /New/ });

    expect(trigger).toHaveClass('janso-btn--primary');
    expect(trigger).toHaveClass('janso-menu__trigger--primary');
    expect(trigger).toHaveAttribute('aria-haspopup', 'menu');
    await user.click(trigger);
    expect(screen.getByRole('menu', { name: 'New voucher' })).toBeInTheDocument();
  });

  it('defaults to the quiet trigger, so no existing caller gains a primary fill', () => {
    render(<Menu label="Columns" triggerLabel="Columns" items={ITEMS} onSelect={vi.fn()} />);
    const trigger = screen.getByRole('button', { name: /Columns/ });

    expect(trigger).toHaveClass('janso-btn--ghost');
    expect(trigger).not.toHaveClass('janso-menu__trigger--primary');
  });

  it('keys its colour off the theme rather than naming one, and rules the caret off', () => {
    // This suite runs with `css: false`, so the rule is asserted in the stylesheet. A literal hex
    // or rgba() here is exactly how a control stops following the three themes (CLAUDE.md §4).
    const start = OVERLAY_CSS.indexOf('.janso-menu__trigger--primary');
    const block = OVERLAY_CSS.slice(start, OVERLAY_CSS.indexOf('.janso-switcher__panel', start));

    expect(start).toBeGreaterThan(-1);
    expect(block).toContain('--janso-ink-invert');
    expect(block).toContain('--janso-grad-action-press');
    expect(block).toMatch(/border-inline-start:\s*1px solid var\(--janso-brand-bright\)/);
    expect(block).not.toMatch(/#[0-9a-f]{3,8}\b|rgba?\(/i);
  });
});
