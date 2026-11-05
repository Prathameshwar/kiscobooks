/**
 * CommandPalette, CommandTrigger and the ⌘K / Ctrl+K shortcut (design-system §5.12).
 *
 * The keyboard contract is the component, so most of these drive it with the keyboard alone:
 * focus stays in the combobox, the arrows move `aria-activedescendant`, Enter chooses, Escape
 * closes and restores focus. Permission filtering is asserted as absence, never as a disabled row.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { useState } from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  CommandPalette,
  CommandTrigger,
  useCommandPaletteShortcut,
  type CommandItem,
} from '../src/components/CommandPalette';
import { PermissionProvider } from '../src/lib/permissions';

const OVERLAY_CSS = readFileSync(join(__dirname, '..', 'src', 'styles', 'overlay.css'), 'utf8');

const ITEMS: CommandItem[] = [
  { id: 'home', label: 'Business overview', group: 'Go to' },
  { id: 'invoices', label: 'Invoices', group: 'Go to', keywords: ['bills'], permission: 'invoice.read' },
  { id: 'customers', label: 'Customers', group: 'Go to', hint: 'Operate', permission: 'customer.read' },
  { id: 'audit', label: 'Audit log', group: 'Go to', permission: 'audit.read' },
  { id: 'new-invoice', label: 'New invoice', group: 'Create', permission: 'invoice.create' },
];

function Harness({
  permissions = ['invoice.read', 'customer.read', 'invoice.create'],
  onSelect = vi.fn(),
  initiallyOpen = true,
}: {
  permissions?: string[];
  onSelect?: (id: string) => void;
  initiallyOpen?: boolean;
}) {
  const [open, setOpen] = useState(initiallyOpen);
  useCommandPaletteShortcut(() => setOpen(true));
  return (
    <PermissionProvider permissions={permissions}>
      <CommandTrigger onOpen={() => setOpen(true)} />
      <CommandPalette open={open} onClose={() => setOpen(false)} items={ITEMS} onSelect={onSelect} />
    </PermissionProvider>
  );
}

function options(): HTMLElement[] {
  return screen.queryAllByRole('option');
}

describe('CommandPalette', () => {
  it('opens as a labelled modal dialog with focus in the combobox', () => {
    render(<Harness />);
    const dialog = screen.getByRole('dialog', { name: 'Command palette' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    const input = within(dialog).getByRole('combobox');
    expect(input).toHaveFocus();
    expect(input).toHaveAttribute('aria-controls', screen.getByRole('listbox').id);
  });

  it('renders nothing while closed', () => {
    render(<Harness initiallyOpen={false} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('omits items the actor may not use, rather than disabling them', () => {
    render(<Harness />);
    const labels = options().map((option) => option.textContent);
    expect(labels).toContain('Invoices');
    expect(labels.join(' ')).not.toContain('Audit log');
    expect(options().every((option) => !option.hasAttribute('aria-disabled'))).toBe(true);
  });

  it('lists items under their group headings, as named groups', () => {
    render(<Harness />);
    expect(screen.getByRole('group', { name: 'Go to' })).toBeInTheDocument();
    expect(within(screen.getByRole('group', { name: 'Create' })).getByRole('option')).toHaveTextContent(
      'New invoice',
    );
  });

  it('shows an item hint beside its label', () => {
    render(<Harness />);
    expect(screen.getByRole('option', { name: /Customers/ })).toHaveTextContent('Operate');
  });

  it('highlights the first option and announces it through aria-activedescendant', () => {
    render(<Harness />);
    const input = screen.getByRole('combobox');
    const first = options()[0] as HTMLElement;
    expect(first).toHaveAttribute('aria-selected', 'true');
    expect(input).toHaveAttribute('aria-activedescendant', first.id);
  });

  it('walks the options with the arrows, wrapping at both ends, and jumps with Home/End', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const input = screen.getByRole('combobox');
    const all = options();
    await user.keyboard('{ArrowDown}');
    expect(input).toHaveAttribute('aria-activedescendant', all[1]?.id);
    await user.keyboard('{ArrowUp}{ArrowUp}');
    expect(input).toHaveAttribute('aria-activedescendant', all[all.length - 1]?.id);
    await user.keyboard('{ArrowDown}');
    expect(input).toHaveAttribute('aria-activedescendant', all[0]?.id);
    await user.keyboard('{End}');
    expect(input).toHaveAttribute('aria-activedescendant', all[all.length - 1]?.id);
    await user.keyboard('{Home}');
    expect(input).toHaveAttribute('aria-activedescendant', all[0]?.id);
    expect(input).toHaveFocus();
  });

  it('ranks label prefix, then word prefix, then anywhere — within each group, groups in given order', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.type(screen.getByRole('combobox'), 'in');
    // In "Go to", "Invoices" starts with it and "Business" only contains it; "New invoice" is in
    // "Create", which follows. One heading per group, never repeated.
    expect(options().map((option) => option.textContent)).toEqual([
      'Invoices',
      'Business overview',
      'New invoice',
    ]);
    expect(screen.getAllByRole('group')).toHaveLength(2);
    await user.clear(screen.getByRole('combobox'));
    await user.type(screen.getByRole('combobox'), 'bills');
    expect(options().map((option) => option.textContent)).toEqual(['Invoices']);
  });

  it('resets the highlight to the top match on every new query', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const input = screen.getByRole('combobox');
    await user.keyboard('{ArrowDown}{ArrowDown}');
    await user.type(input, 'c');
    expect(input).toHaveAttribute('aria-activedescendant', options()[0]?.id);
  });

  it('chooses the highlighted option on Enter and closes first', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<Harness onSelect={onSelect} />);
    await user.type(screen.getByRole('combobox'), 'cust{Enter}');
    expect(onSelect).toHaveBeenCalledWith('customers');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('chooses an option on click, without stealing focus from the input first', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<Harness onSelect={onSelect} />);
    await user.click(screen.getByRole('option', { name: 'New invoice' }));
    expect(onSelect).toHaveBeenCalledWith('new-invoice');
  });

  it('says so when nothing matches, and Enter then does nothing', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<Harness onSelect={onSelect} />);
    const input = screen.getByRole('combobox');
    await user.type(input, 'zzz');
    expect(screen.getByRole('status')).toHaveTextContent('Nothing matches “zzz”.');
    expect(input).toHaveAttribute('aria-expanded', 'false');
    expect(input).not.toHaveAttribute('aria-activedescendant');
    await user.keyboard('{Enter}');
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('closes on Escape and returns focus to the trigger that opened it', async () => {
    const user = userEvent.setup();
    render(<Harness initiallyOpen={false} />);
    const trigger = screen.getByRole('button', { name: /Search or jump to/ });
    await user.click(trigger);
    expect(screen.getByRole('combobox')).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('closes when the scrim is pressed', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const scrim = document.querySelector('.janso-command__scrim') as HTMLElement;
    await user.pointer({ keys: '[MouseLeft>]', target: scrim });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('starts empty each time it opens', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.type(screen.getByRole('combobox'), 'aud');
    await user.keyboard('{Escape}');
    await user.keyboard('{Control>}k{/Control}');
    expect(screen.getByRole('combobox')).toHaveValue('');
  });

  it('marks the highlight with a shape as well as a tint', () => {
    expect(OVERLAY_CSS).toMatch(
      /\.janso-command__option\[aria-selected='true'\]\s*\{[^}]*box-shadow: inset 2px 0 0 0 var\(--janso-focus\)/,
    );
  });
});

describe('useCommandPaletteShortcut', () => {
  it.each([
    ['Ctrl+K', '{Control>}k{/Control}'],
    ['⌘K', '{Meta>}k{/Meta}'],
  ])('opens the palette on %s', async (_name, keys) => {
    const user = userEvent.setup();
    render(<Harness initiallyOpen={false} />);
    await user.keyboard(keys);
    expect(screen.getByRole('dialog', { name: 'Command palette' })).toBeInTheDocument();
  });

  it('ignores a plain k and an Alt-modified one', async () => {
    const user = userEvent.setup();
    render(<Harness initiallyOpen={false} />);
    await user.keyboard('k{Control>}{Alt>}k{/Alt}{/Control}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('removes its listener on unmount', async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    function Probe() {
      useCommandPaletteShortcut(onOpen);
      return null;
    }
    const { unmount } = render(<Probe />);
    unmount();
    await user.keyboard('{Control>}k{/Control}');
    expect(onOpen).not.toHaveBeenCalled();
  });
});

describe('CommandTrigger', () => {
  it('is a button that declares the dialog it opens and its shortcut', () => {
    render(<CommandTrigger onOpen={() => {}} />);
    const trigger = screen.getByRole('button', { name: /Search or jump to/ });
    expect(trigger).toHaveAttribute('aria-haspopup', 'dialog');
    expect(trigger).toHaveAttribute('aria-keyshortcuts', 'Control+K Meta+K');
  });

  it('shows the shortcut the caller names', () => {
    render(<CommandTrigger onOpen={() => {}} shortcut="⌘ K" />);
    expect(screen.getByText('⌘ K')).toBeInTheDocument();
  });
});

describe('CommandTrigger key cap', () => {
  const original = Object.getOwnPropertyDescriptor(window.navigator, 'platform');
  function setPlatform(value: string) {
    Object.defineProperty(window.navigator, 'platform', { value, configurable: true });
  }
  afterEach(() => {
    if (original) Object.defineProperty(window.navigator, 'platform', original);
    else Reflect.deleteProperty(window.navigator, 'platform');
  });

  it('names Ctrl K off Apple platforms', () => {
    setPlatform('Win32');
    render(<CommandTrigger onOpen={() => {}} />);
    expect(screen.getByText('Ctrl K')).toBeInTheDocument();
  });

  it('names ⌘ K on a Mac, resolved after mount', () => {
    setPlatform('MacIntel');
    render(<CommandTrigger onOpen={() => {}} />);
    expect(screen.getByText('⌘ K')).toBeInTheDocument();
  });

  it('lets the caller override the resolved cap', () => {
    setPlatform('MacIntel');
    render(<CommandTrigger onOpen={() => {}} shortcut="Alt K" />);
    expect(screen.getByText('Alt K')).toBeInTheDocument();
  });
});
