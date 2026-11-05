/**
 * Rail, RailSection, RailItem, RailFooter and OrgSwitcher.
 *
 * The rail is a layout component: it must render what it is handed, name its groups, and
 * know nothing about permissions (design-system §5.2). Truncation is a CSS promise, so it
 * is asserted against the stylesheet rather than against a width jsdom will not compute.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it, vi } from 'vitest';

import { OrgSwitcher } from '../src/components/OrgSwitcher';
import { Rail, RailFooter, RailItem, RailSection } from '../src/components/Rail';
import {
  BookIcon,
  DashboardIcon,
  DocumentIcon,
  HelpIcon,
  ReportsIcon,
} from '../src/components/icons-console';

const SHELL_CSS = readFileSync(
  join(__dirname, '..', 'src', 'styles', 'shell.css'),
  'utf8',
);

describe('Rail', () => {
  it('renders the brand, switcher, navigation and pinned footer bands', () => {
    const { container } = render(
      <Rail
        brand={<span>JANSO</span>}
        switcher={<OrgSwitcher name="Acme Corp" code="ACME-01" />}
        footer={<RailFooter>user card</RailFooter>}
      >
        <RailSection label="Ledger">
          <RailItem icon={<BookIcon />} label="Journals" href="/journals" />
        </RailSection>
      </Rail>,
    );

    expect(container.querySelector('.janso-rail__brand')).toHaveTextContent('JANSO');
    expect(container.querySelector('.janso-rail__switcher')).toBeInTheDocument();
    expect(container.querySelector('.janso-rail__nav')).toBeInTheDocument();
    expect(container.querySelector('.janso-rail__foot')).toHaveTextContent('user card');
    expect(screen.getByRole('link', { name: 'Journals' })).toBeInTheDocument();
  });

  it('omits the switcher and footer bands when nothing is passed for them', () => {
    const { container } = render(
      <Rail brand={<span>JANSO</span>}>
        <RailSection label="Ledger">
          <RailItem icon={<BookIcon />} label="Journals" href="/journals" />
        </RailSection>
      </Rail>,
    );

    expect(container.querySelector('.janso-rail__switcher')).not.toBeInTheDocument();
    expect(container.querySelector('.janso-rail__foot')).not.toBeInTheDocument();
  });

  it('gives the navigation its own scroll region so the lockup and footer stay put', () => {
    expect(SHELL_CSS).toMatch(/\.janso-rail__nav\s*\{[^}]*overflow-y: auto/);
    expect(SHELL_CSS).toContain('grid-template-rows: auto auto 1fr auto');
  });

  it('separates the pinned footer with a hairline rule', () => {
    expect(SHELL_CSS).toMatch(
      /\.janso-rail-footer\s*\{[^}]*border-top: 1px solid var\(--janso-line\)/,
    );
  });
});

describe('RailSection', () => {
  it('names its group with the overline, as a real navigation landmark', () => {
    render(
      <RailSection label="Receivables">
        <RailItem icon={<DocumentIcon />} label="Invoices" href="/invoices" />
        <RailItem icon={<ReportsIcon />} label="Ageing" href="/ageing" />
      </RailSection>,
    );

    const group = screen.getByRole('navigation', { name: 'Receivables' });
    expect(group).toBeInTheDocument();

    // A real grouping, not two loose anchors: one list, two list items.
    const list = screen.getByRole('list');
    expect(group).toContainElement(list);
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
  });

  it('renders the label as a quiet sentence-case group name', () => {
    render(
      <RailSection label="Receivables">
        <RailItem icon={<DocumentIcon />} label="Invoices" href="/invoices" />
      </RailSection>,
    );

    expect(screen.getByText('Receivables')).toHaveClass('janso-rail-section__label');
    expect(SHELL_CSS).toMatch(
      /\.janso-rail-section__label\s*\{[^}]*font-size: var\(--janso-text-xs\)/,
    );
    expect(SHELL_CSS).toMatch(/\.janso-rail-section__label\s*\{[^}]*letter-spacing/);
    expect(SHELL_CSS).not.toMatch(/\.janso-rail-section__label\s*\{[^}]*text-transform: uppercase/);
  });

  it('names two sections independently rather than sharing one generated id', () => {
    render(
      <>
        <RailSection label="Ledger">
          <RailItem icon={<BookIcon />} label="Journals" href="/journals" />
        </RailSection>
        <RailSection label="Reports">
          <RailItem icon={<ReportsIcon />} label="Trial balance" href="/tb" />
        </RailSection>
      </>,
    );

    expect(screen.getByRole('navigation', { name: 'Ledger' })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Reports' })).toBeInTheDocument();
  });
});

describe('RailItem', () => {
  it('renders an anchor with its icon and its label', () => {
    render(
      <RailSection label="Overview">
        <RailItem icon={<DashboardIcon />} label="Dashboard" href="/dashboard" />
      </RailSection>,
    );

    const link = screen.getByRole('link', { name: 'Dashboard' });
    expect(link).toHaveAttribute('href', '/dashboard');
    expect(link.querySelector('svg')).toBeInTheDocument();
    expect(screen.getByText('Dashboard')).toHaveClass('janso-rail-item__label');
  });

  it('marks the active destination and only that one', () => {
    render(
      <RailSection label="Overview">
        <RailItem icon={<DashboardIcon />} label="Dashboard" href="/dashboard" active />
        <RailItem icon={<DocumentIcon />} label="Invoices" href="/invoices" />
      </RailSection>,
    );

    const active = screen.getByRole('link', { name: 'Dashboard' });
    expect(active).toHaveAttribute('aria-current', 'page');
    expect(active).toHaveAttribute('data-active', 'true');

    const inactive = screen.getByRole('link', { name: 'Invoices' });
    expect(inactive).not.toHaveAttribute('aria-current');
    expect(inactive).not.toHaveAttribute('data-active');
  });

  it('keeps the label as the accessible name independently of the visible text', () => {
    render(
      <RailSection label="Overview">
        <RailItem icon={<HelpIcon />} label="Help centre" href="/help" />
      </RailSection>,
    );

    const link = screen.getByRole('link', { name: 'Help centre' });
    expect(link).toHaveAttribute('aria-label', 'Help centre');
    expect(link).toHaveAttribute('title', 'Help centre');
  });

  it('raises the selected item on a surface with a brand marker, not colour alone', () => {
    expect(SHELL_CSS).toMatch(
      /\.janso-rail-item\[data-active='true'\]\s*\{[^}]*background: var\(--janso-surface\)/,
    );
    expect(SHELL_CSS).toMatch(
      /\.janso-rail-item\[data-active='true'\]\s*\{[^}]*box-shadow: var\(--janso-shadow-card\)/,
    );
    expect(SHELL_CSS).toMatch(
      /\.janso-rail-item\[data-active='true'\] \.janso-rail-item__icon\s*\{[^}]*color: var\(--janso-brand\)/,
    );
    expect(SHELL_CSS).toContain(".janso-rail-item[data-active='true']::before");
  });
});

describe('OrgSwitcher', () => {
  it('is a labelled button that announces the listbox it opens', () => {
    render(<OrgSwitcher name="Acme Manufacturing" code="ACME-01" />);

    const button = screen.getByRole('button', { name: /Switch organisation/ });
    expect(button).toHaveAttribute('aria-haspopup', 'listbox');
    expect(button).toHaveAttribute('aria-expanded', 'false');
    expect(button).toHaveAccessibleName(/ACME-01/);
    expect(button).toHaveAccessibleName(/Acme Manufacturing/);
  });

  it('reflects the open state the caller owns', () => {
    render(<OrgSwitcher name="Acme Manufacturing" code="ACME-01" open />);
    expect(screen.getByRole('button', { name: /Switch organisation/ })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
  });

  it('calls onOpen when activated', async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    render(<OrgSwitcher name="Acme Manufacturing" code="ACME-01" onOpen={onOpen} />);

    await user.click(screen.getByRole('button', { name: /Switch organisation/ }));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it('truncates a long trading name instead of widening the rail', () => {
    const long = 'Northwind Overseas Trading and Manufacturing Private Limited';
    render(<OrgSwitcher name={long} code="NW-002" />);

    expect(screen.getByText(long)).toHaveClass('janso-org__name');
    expect(SHELL_CSS).toMatch(/\.janso-org__name\s*\{[^}]*text-overflow: ellipsis/);
    expect(SHELL_CSS).toMatch(/\.janso-org__name\s*\{[^}]*white-space: nowrap/);
  });

  it('carries a square avatar for an organisation and a chevron affordance', () => {
    const { container } = render(<OrgSwitcher name="Acme Manufacturing" code="ACME-01" />);

    expect(container.querySelector('.janso-avatar')).toHaveClass('janso-avatar--square');
    expect(container.querySelector('.janso-org__chevron')).toBeInTheDocument();
  });
});
