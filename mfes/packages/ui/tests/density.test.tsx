/**
 * The density and labelling mechanisms behind the re-skin (design-system decisions 71–74), each
 * asserted where it lives: `TextField` / `TableSearch` label hiding, the `IconButton` / `Menu`
 * small size, the busy button keeping its fill, the column's tight list-control rhythm, and the
 * one shared chart-geometry module.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { TextField } from '../src/components/TextField';
import { TableSearch } from '../src/components/TableSearch';
import { IconButton } from '../src/components/IconButton';
import { Menu } from '../src/components/Menu';
import { coord, toMagnitude } from '../src/lib/chart-geometry';

const STYLES = join(__dirname, '..', 'src', 'styles');
const UI_CSS = readFileSync(join(STYLES, 'janso-ui.css'), 'utf8');
const DATA_CSS = readFileSync(join(STYLES, 'data.css'), 'utf8');
const TABLE_CSS = readFileSync(join(STYLES, 'table.css'), 'utf8');

describe('TextField hideLabel', () => {
  it('keeps the label as the accessible name while clipping it from the paint', () => {
    render(<TextField label="Search customers" hideLabel />);
    const input = screen.getByRole('textbox', { name: 'Search customers' });
    expect(input).toBeInTheDocument();
    expect(screen.getByText('Search customers')).toHaveClass('janso-label', 'janso-visually-hidden');
  });

  it('drops the empty label row, but keeps it when it still holds an action', () => {
    const { container, rerender } = render(<TextField label="Code" hideLabel />);
    expect(container.querySelector('.janso-field__row')).toBeNull();
    rerender(<TextField label="Code" hideLabel action={<a href="#help">Help</a>} />);
    const row = container.querySelector('.janso-field__row');
    expect(row).toContainElement(screen.getByRole('link', { name: 'Help' }));
    expect(row?.querySelector('label')).toBeNull();
  });

  it('shows the label in its row by default', () => {
    const { container } = render(<TextField label="Legal name" />);
    const label = container.querySelector('.janso-field__row label');
    expect(label).toHaveTextContent('Legal name');
    expect(label).not.toHaveClass('janso-visually-hidden');
  });
});

describe('TableSearch label', () => {
  it('hides its label by default, keeping the accessible name', () => {
    render(<TableSearch value="" onChange={() => {}} label="Search customers" />);
    expect(screen.getByRole('searchbox', { name: 'Search customers' })).toBeInTheDocument();
    expect(screen.getByText('Search customers')).toHaveClass('janso-visually-hidden');
  });

  it('shows it on request', () => {
    render(<TableSearch value="" onChange={() => {}} label="Search customers" showLabel />);
    expect(screen.getByText('Search customers')).not.toHaveClass('janso-visually-hidden');
  });
});

describe('IconButton and Menu size', () => {
  it('is the default size unless asked for the small one', () => {
    const { rerender } = render(<IconButton label="Refresh" icon={<span />} />);
    expect(screen.getByRole('button', { name: 'Refresh' })).not.toHaveClass('janso-btn--icon-sm');
    rerender(<IconButton label="Refresh" icon={<span />} size="sm" />);
    expect(screen.getByRole('button', { name: 'Refresh' })).toHaveClass('janso-btn--icon-sm');
    expect(UI_CSS).toMatch(/\.janso-btn--icon-sm \{ width: 1\.75rem; height: 1\.75rem; \}/);
  });

  it('passes the size through to a menu’s icon trigger', () => {
    render(<Menu label="Actions for Aditya Solar" items={[{ id: 'a', label: 'Open' }]} onSelect={() => {}} size="sm" />);
    expect(screen.getByRole('button', { name: 'Actions for Aditya Solar' })).toHaveClass('janso-btn--icon-sm');
  });

  it('leaves no container-specific icon-button override behind in the table sheet', () => {
    expect(TABLE_CSS).not.toMatch(/td \.janso-btn--icon\s*\{/);
  });
});

describe('busy buttons', () => {
  it('skip the grey disabled fill, so a busy button keeps its variant', () => {
    expect(UI_CSS).toMatch(/\.janso-btn--primary:disabled:not\(\[aria-busy='true'\]\)\s*\{/);
    expect(UI_CSS).toMatch(/\.janso-btn--danger:disabled:not\(\[aria-busy='true'\]\)\s*\{/);
    expect(UI_CSS).toMatch(/\.janso-btn\[aria-busy='true'\]\s*\{[^}]*cursor: progress/);
  });
});

describe('list-control rhythm', () => {
  it('resets stacked-field margins and gives card list controls consistent side gutters', () => {
    expect(TABLE_CSS).toMatch(/\.janso-filter-bar__controls > \.janso-field \+ \.janso-field\s*\{[^}]*margin-top: 0/);
    expect(TABLE_CSS).toMatch(/\.janso-card > \.janso-filter-bar\s*\{[^}]*padding: var\(--janso-space-4\) var\(--janso-space-5\)/);
    expect(TABLE_CSS).toMatch(/\.janso-card > \.janso-pager\s*\{[^}]*padding: var\(--janso-space-3\) var\(--janso-space-5\)/);
  });
  it('sets whatever follows a filter or bulk bar at the small step, owned by the column', () => {
    // The selector list also covers a bar wrapped in its own GET form (see `content-layout`), so
    // the two class forms are asserted individually rather than as an exact adjacent pair.
    expect(DATA_CSS).toMatch(
      /\.janso-page > :is\(\.janso-filter-bar, \.janso-bulk-bar\) \+ \*,\s*\.janso-flow > :is\(\.janso-filter-bar, \.janso-bulk-bar\) \+ \*,/,
    );
    expect(DATA_CSS).toMatch(/\.janso-flow > form:has\(> \.janso-filter-bar\) \+ \*\s*\{[^}]*margin-top: var\(--janso-space-3\)/);
    // The bars carry no outer margin of their own, so there is one spacing regime, not two.
    expect(TABLE_CSS).not.toMatch(/\.janso-filter-bar\s*\{[^}]*margin-bottom/);
    expect(TABLE_CSS).not.toMatch(/\.janso-bulk-bar\s*\{[^}]*margin-bottom/);
  });
});

describe('chart geometry', () => {
  it('turns a decimal string into a magnitude for placement, zero when unparseable', () => {
    expect(toMagnitude('1234.5600')).toBe(1234.56);
    expect(toMagnitude('-12')).toBe(-12);
    expect(toMagnitude('n/a')).toBe(0);
    expect(toMagnitude('Infinity')).toBe(0);
  });

  it('rounds coordinates to two places', () => {
    expect(coord(1 / 3)).toBe('0.33');
    expect(coord(10)).toBe('10');
  });
});
