/**
 * `ContextSwitcher` — the company and financial-year switcher in the rail.
 *
 * The keyboard and dismissal contract *is* the component, so that is what is asserted here:
 * a switcher that does not cycle with the arrow keys, return focus on Escape and close on an
 * outside press is a worse control than a plain list of links. Elevation and truncation are
 * CSS promises, so they are asserted against the stylesheet rather than against widths jsdom
 * will not compute.
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it, vi } from 'vitest';

import { ContextSwitcher, type ContextOption } from '../src/components/ContextSwitcher';
import { PermissionProvider } from '../src/lib/permissions';
import { CalendarIcon } from '../src/components/icons-console';

const OVERLAY_CSS = readFileSync(join(__dirname, '..', 'src', 'styles', 'overlay.css'), 'utf8');
const SHELL_CSS = readFileSync(join(__dirname, '..', 'src', 'styles', 'shell.css'), 'utf8');

const COMPANIES: ContextOption[] = [
  { id: 'c1', name: 'Acme Manufacturing', code: 'ACME-01', badge: 'Default' },
  { id: 'c2', name: 'Acme Exports', code: 'ACME-02' },
  { id: 'c3', name: 'Northwind Retail', code: 'NW-01', disabledReason: 'Step-up required' },
];

function setup(props: Partial<React.ComponentProps<typeof ContextSwitcher>> = {}) {
  const onSelect = props.onSelect ?? vi.fn();
  const view = render(
    <ContextSwitcher
      label="Switch company"
      overline="ACME-01"
      name="Acme Manufacturing"
      options={COMPANIES}
      selectedId="c1"
      {...props}
      onSelect={onSelect}
    />,
  );
  return { ...view, onSelect };
}

const trigger = () => screen.getByRole('button', { name: /Switch company/ });

describe('ContextSwitcher trigger', () => {
  it('is a labelled button announcing the listbox it owns', () => {
    setup();
    expect(trigger()).toHaveAttribute('aria-haspopup', 'listbox');
    expect(trigger()).toHaveAttribute('aria-expanded', 'false');
    expect(trigger()).toHaveAccessibleName(/ACME-01/);
    expect(trigger()).toHaveAccessibleName(/Acme Manufacturing/);
  });

  it('keeps full company names and codes available when the visible text is shortened', async () => {
    const name = 'Northwind Overseas Trading and Manufacturing Private Limited';
    const code = 'NORTHWIND-OVERSEAS-MANUFACTURING-009';
    setup({ name, overline: code, options: [{ id: 'c9', name, code }], selectedId: 'c9' });
    expect(trigger()).toHaveAttribute('title', `${name} (${code})`);
    expect(within(trigger()).getByText(name)).toHaveAttribute('title', name);
    expect(within(trigger()).getByText(code)).toHaveAttribute('title', code);
    expect(trigger()).toHaveAccessibleName(new RegExp(name));
    await userEvent.click(trigger());
    const option = screen.getByRole('option');
    expect(within(option).getByText(name)).toHaveAttribute('title', name);
    expect(within(option).getByText(code)).toHaveAttribute('title', code);
  });

  it('points aria-controls at the panel only while it is open', async () => {
    const user = userEvent.setup();
    setup();
    expect(trigger()).not.toHaveAttribute('aria-controls');

    await user.click(trigger());
    const panelId = trigger().getAttribute('aria-controls');
    expect(panelId).toBeTruthy();
    expect(document.getElementById(panelId as string)).toBeInTheDocument();
  });

  it('carries the glyph variant and compact density when asked, instead of an avatar', () => {
    const { container } = setup({ icon: <CalendarIcon />, compact: true, overline: 'Financial year', name: 'FY2026-2027' });
    expect(container.querySelector('.janso-org__icon')).toBeInTheDocument();
    expect(container.querySelector('.janso-avatar')).not.toBeInTheDocument();
    expect(trigger()).toHaveAttribute('data-compact', 'true');
    expect(SHELL_CSS).toContain(".janso-org[data-compact='true']");
  });

  it('stops claiming a popup, and is disabled, when there is nothing at all to show', () => {
    setup({ options: [] });
    expect(trigger()).toBeDisabled();
    expect(trigger()).toHaveAttribute('aria-expanded', 'false');
  });

  it('still opens with no options when it has something to say', async () => {
    const user = userEvent.setup();
    setup({ options: [], status: { empty: 'No company has been assigned to you.' } });

    await user.click(trigger());
    expect(screen.getByText('No company has been assigned to you.')).toBeInTheDocument();
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });
});

describe('ContextSwitcher panel', () => {
  it('renders one option per company, marking the selected one', async () => {
    const user = userEvent.setup();
    setup();
    await user.click(trigger());

    const list = screen.getByRole('listbox', { name: 'Switch company' });
    expect(within(list).getAllByRole('option')).toHaveLength(3);
    expect(screen.getByRole('option', { name: /Acme Manufacturing/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('option', { name: /Acme Exports/ })).toHaveAttribute('aria-selected', 'false');
    expect(screen.getByRole('option', { name: /Acme Manufacturing/ })).toHaveTextContent('Default');
  });

  it('reports a selection and closes, returning focus to the trigger', async () => {
    const user = userEvent.setup();
    const { onSelect } = setup();
    await user.click(trigger());
    await user.click(screen.getByRole('option', { name: /Acme Exports/ }));

    expect(onSelect).toHaveBeenCalledWith('c2');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(trigger()).toHaveFocus();
  });

  it('refuses an option that carries a reason, and shows the reason', async () => {
    const user = userEvent.setup();
    const { onSelect } = setup();
    await user.click(trigger());

    const blocked = screen.getByRole('option', { name: /Northwind Retail/ });
    expect(blocked).toHaveAttribute('aria-disabled', 'true');
    expect(blocked).toHaveTextContent('Step-up required');

    await user.click(blocked);
    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.getByRole('listbox')).toBeInTheDocument();
  });

  it('opens on the selected row so the arrow keys start where the user is', async () => {
    const user = userEvent.setup();
    setup({ selectedId: 'c2' });
    await user.click(trigger());

    expect(screen.getByRole('option', { name: /Acme Exports/ })).toHaveFocus();
  });

  it('cycles with the arrow keys and jumps with Home and End', async () => {
    const user = userEvent.setup();
    setup();
    await user.click(trigger());

    await user.keyboard('{ArrowDown}');
    expect(screen.getByRole('option', { name: /Acme Exports/ })).toHaveFocus();
    await user.keyboard('{End}');
    expect(screen.getByRole('option', { name: /Northwind Retail/ })).toHaveFocus();
    // Past the last row, back to the first.
    await user.keyboard('{ArrowDown}');
    expect(screen.getByRole('option', { name: /Acme Manufacturing/ })).toHaveFocus();
    await user.keyboard('{ArrowUp}');
    expect(screen.getByRole('option', { name: /Northwind Retail/ })).toHaveFocus();
    await user.keyboard('{Home}');
    expect(screen.getByRole('option', { name: /Acme Manufacturing/ })).toHaveFocus();
  });

  it('opens on the last row from the trigger with ArrowUp', async () => {
    const user = userEvent.setup();
    setup();
    trigger().focus();
    await user.keyboard('{ArrowUp}');

    expect(screen.getByRole('option', { name: /Northwind Retail/ })).toHaveFocus();
  });

  it('closes on Escape and gives focus back', async () => {
    const user = userEvent.setup();
    setup();
    await user.click(trigger());
    await user.keyboard('{Escape}');

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(trigger()).toHaveFocus();
  });

  it('closes on a press outside, leaving focus to the click target', async () => {
    const user = userEvent.setup();
    render(
      <>
        <ContextSwitcher label="Switch company" overline="ACME-01" name="Acme Manufacturing" options={COMPANIES} selectedId="c1" onSelect={vi.fn()} />
        <button type="button">Elsewhere</button>
      </>,
    );

    await user.click(trigger());
    expect(screen.getByRole('listbox')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Elsewhere' }));
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(trigger()).not.toHaveFocus();
  });

  it('closes on Tab, so the next tab stop is computed from the trigger', async () => {
    const user = userEvent.setup();
    setup();
    await user.click(trigger());
    await user.keyboard('{Tab}');

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });
});

describe('ContextSwitcher filter', () => {
  it('focuses the filter on open and reports what was typed', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    setup({ search: { label: 'Search companies', value: '', onChange } });

    await user.click(trigger());
    const field = screen.getByRole('searchbox', { name: 'Search companies' });
    expect(field).toHaveFocus();

    await user.type(field, 'ex');
    expect(onChange).toHaveBeenCalled();
  });

  it('moves focus from the filter into the list on ArrowDown', async () => {
    const user = userEvent.setup();
    setup({ search: { label: 'Search companies', value: '', onChange: vi.fn() } });

    await user.click(trigger());
    await user.keyboard('{ArrowDown}');
    expect(screen.getByRole('option', { name: /Acme Exports/ })).toHaveFocus();
  });
});

describe('ContextSwitcher footer actions', () => {
  it('renders an action and reports it, closing the panel', async () => {
    const user = userEvent.setup();
    const onAction = vi.fn();
    setup({ actions: [{ id: 'create', label: 'Create company' }], onAction });

    await user.click(trigger());
    await user.click(screen.getByRole('button', { name: 'Create company' }));

    expect(onAction).toHaveBeenCalledWith('create');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('omits an action the actor has no permission for, rather than disabling it', async () => {
    const user = userEvent.setup();
    render(
      <PermissionProvider permissions={['company.read']}>
        <ContextSwitcher
          label="Switch company"
          overline="ACME-01"
          name="Acme Manufacturing"
          options={COMPANIES}
          selectedId="c1"
          onSelect={vi.fn()}
          actions={[
            { id: 'create', label: 'Create company', permission: 'company.create' },
            { id: 'manage', label: 'Manage companies', permission: 'company.read' },
          ]}
        />
      </PermissionProvider>,
    );

    await user.click(trigger());
    expect(screen.queryByRole('button', { name: 'Create company' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Manage companies' })).toBeInTheDocument();
  });
});

describe('ContextSwitcher status', () => {
  it('announces a load in progress', async () => {
    const user = userEvent.setup();
    setup({ options: [], status: { loading: true } });

    await user.click(trigger());
    expect(screen.getByRole('status')).toHaveTextContent('Loading…');
  });

  it('announces a failure as an alert, and keeps the actions reachable', async () => {
    const user = userEvent.setup();
    setup({
      options: [],
      status: { error: 'Companies are unavailable. Try again.' },
      actions: [{ id: 'retry', label: 'Try again' }],
    });

    await user.click(trigger());
    expect(screen.getByRole('alert')).toHaveTextContent('Companies are unavailable. Try again.');
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });
});

describe('ContextSwitcher presentation', () => {
  it('portals its panel so the rail cannot clip it, and elevates it like the menu', async () => {
    const user = userEvent.setup();
    const { container } = setup();
    await user.click(trigger());

    // The panel is in the document but not inside the component's own subtree.
    expect(container.querySelector('.janso-switcher__panel')).toBeNull();
    expect(document.querySelector('.janso-switcher__panel')).toBeInTheDocument();
    expect(OVERLAY_CSS).toMatch(/\.janso-switcher__panel\s*\{[^}]*z-index: var\(--janso-z-popover\)/);
    expect(OVERLAY_CSS).toMatch(/\.janso-switcher__panel\s*\{[^}]*box-shadow: var\(--janso-shadow-popover\)/);
  });

  it('truncates a long trading name instead of widening the panel', async () => {
    const user = userEvent.setup();
    const long = 'Northwind Overseas Trading and Manufacturing Private Limited';
    setup({ options: [{ id: 'c9', name: long, code: 'NW-009' }], selectedId: 'c9' });

    await user.click(trigger());
    expect(screen.getByText(long)).toHaveClass('janso-switcher__option-name');
    expect(OVERLAY_CSS).toMatch(/\.janso-switcher__option-name\s*\{[^}]*text-overflow: ellipsis/);
    expect(OVERLAY_CSS).toMatch(/\.janso-switcher__option-name\s*\{[^}]*white-space: nowrap/);
  });

  it('rings the focused row inside the panel, which clips an outer ring', () => {
    expect(OVERLAY_CSS).toMatch(
      /\.janso-switcher__option:focus-visible\s*\{[^}]*box-shadow: inset 0 0 0 2px var\(--janso-focus\)/,
    );
  });
});
