/**
 * Reaching the designer.
 *
 * It was reachable only by typing its URL — eight phases of editor and a service behind it,
 * with no way in. The rail entry is the fix, and what is worth testing is the gating: the two
 * capabilities have separate permission keys on purpose, because being allowed to see a layout
 * and being allowed to see which document prints on it are different grants.
 */
import { describe, expect, it, vi } from 'vitest';
import { screen, within } from '@testing-library/react';

vi.mock('../app/lib/navigate', () => ({
  signInUrl: () => 'http://localhost:4310/login',
  authActionUrl: (path: string) => 'http://localhost:4310' + path,
  goTo: vi.fn(),
}));

import { ConsoleShell } from '../app/components/ConsoleShell';
import { flattenNavigation, navigationFor } from '../app/nav';
import type { Session } from '../app/session';
import { companyContextFor, renderWithProviders, sessionFor } from './helpers';

const COMPANY = '01990000-0000-7000-8000-000000000001';

function shellFor(permissions: string[], { noCompany = false }: { noCompany?: boolean } = {}) {
  return (session: Session) => (
    <ConsoleShell
      session={{
        ...session,
        company: { ...session.company, id: noCompany ? undefined : COMPANY },
        grants: [
          {
            scope_type: 'tenant',
            scope_id: null,
            permissions,
            valid_from: '2000-01-01',
            valid_to: null,
          },
        ],
      }}
      context={companyContextFor()}
      activeHref="/documents/routing"
    >
      <p>Content</p>
    </ConsoleShell>
  );
}

const READER = ['design.template.read', 'company.read'];
const ROUTER = [...READER, 'design.assignment.read'];

describe('the rail', () => {
  it('offers the designer to someone who may read templates', async () => {
    await renderWithProviders(shellFor(READER), { permissions: READER });

    const link = screen.getByRole('link', { name: /Print templates/ });
    expect(link).toHaveAttribute('href', '/invoice-designer');
  });

  it('offers Voucher print under it, to anyone who may read templates', async () => {
    await renderWithProviders(shellFor(READER), { permissions: READER });

    // A card for every kind of voucher: it needs the layouts, not the routing rules.
    expect(screen.getByRole('link', { name: /Voucher print/ })).toHaveAttribute(
      'href',
      '/documents/vouchers',
    );
  });

  it('offers routing with its own permission', async () => {
    await renderWithProviders(shellFor(ROUTER), { permissions: ROUTER });

    expect(screen.getByRole('link', { name: /Document routing/ })).toHaveAttribute(
      'href',
      '/documents/routing',
    );
  });

  it('marks routing as advanced in the rail, since nobody needs it to print', async () => {
    await renderWithProviders(shellFor(ROUTER), { permissions: ROUTER });

    // Voucher print customizes a voucher in one step; routing is for conditions. The rail says
    // which is which, so nobody reads a second entry as a second thing they must set up.
    expect(screen.getByRole('link', { name: 'Document routing (advanced)' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Voucher print' })).toBeInTheDocument();
  });

  it('withholds routing from someone who may only read layouts', async () => {
    // Seeing layouts is not seeing which document prints on which one. Its own test, not a
    // second render in the first one — two renders share a document and the first one's link
    // is still there.
    await renderWithProviders(shellFor(READER), { permissions: READER });

    expect(screen.getByRole('link', { name: /Print templates/ })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Document routing/ })).not.toBeInTheDocument();
  });

  it('is absent entirely without template read access', async () => {
    await renderWithProviders(shellFor(['company.read']), { permissions: ['company.read'] });

    expect(screen.queryByRole('link', { name: /Print templates/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Document routing/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Voucher print/ })).not.toBeInTheDocument();
  });

  it('is absent with no company open, because a template belongs to one', async () => {
    await renderWithProviders(shellFor(ROUTER, { noCompany: true }), { permissions: ROUTER });

    expect(screen.queryByRole('link', { name: /Print templates/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Voucher print/ })).not.toBeInTheDocument();
  });

  it('marks routing as the open page', async () => {
    await renderWithProviders(shellFor(ROUTER), { permissions: ROUTER });

    expect(screen.getByRole('link', { name: /Document routing/ })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('marks a voucher kind page as inside Voucher print', async () => {
    await renderWithProviders(
      (session) => (
        <ConsoleShell
          session={{
            ...session,
            company: { ...session.company, id: COMPANY },
            grants: [
              {
                scope_type: 'tenant',
                scope_id: null,
                permissions: ROUTER,
                valid_from: '2000-01-01',
                valid_to: null,
              },
            ],
          }}
          context={companyContextFor()}
          activeHref="/documents/vouchers"
        >
          <p>Content</p>
        </ConsoleShell>
      ),
      { permissions: ROUTER },
    );

    expect(screen.getByRole('link', { name: /Voucher print/ })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: /Document routing/ })).not.toHaveAttribute('aria-current');
  });

  it('files all three under Administer, where company-scoped configuration lives', async () => {
    await renderWithProviders(shellFor(ROUTER), { permissions: ROUTER });

    const administer = screen.getByRole('navigation', { name: 'Administer' });
    expect(within(administer).getByRole('link', { name: /Print templates/ })).toBeInTheDocument();
    expect(within(administer).getByRole('link', { name: /Voucher print/ })).toBeInTheDocument();
    expect(within(administer).getByRole('link', { name: /Document routing/ })).toBeInTheDocument();
  });

  it('needs a grant for the open company, not merely the key somewhere', async () => {
    // The gate is `companyPermission`, so a grant scoped to another company does not light
    // the link up for this one — the same rule masters and tax navigation already follow.
    const elsewhere = '01990000-0000-7000-8000-00000000000b';
    await renderWithProviders(
      (session) => (
        <ConsoleShell
          session={{
            ...session,
            company: { ...session.company, id: COMPANY },
            grants: [
              {
                scope_type: 'company',
                scope_id: elsewhere,
                permissions: ROUTER,
                valid_from: '2000-01-01',
                valid_to: null,
              },
            ],
          }}
          context={companyContextFor()}
          activeHref="/documents/routing"
        >
          <p>Content</p>
        </ConsoleShell>
      ),
      { permissions: ROUTER },
    );

    expect(screen.queryByRole('link', { name: /Print templates/ })).not.toBeInTheDocument();
  });
});

describe('the command palette', () => {
  it('reaches every destination, because it is built from the same tree', async () => {
    // One permission-filtered tree feeds the rail and the keyboard path, so a destination
    // cannot be navigable by one and invisible to the other.
    const session = await sessionFor({ permissions: ROUTER });
    const scoped: Session = {
      ...session,
      company: { ...session.company, id: COMPANY },
      grants: [
        {
          scope_type: 'tenant',
          scope_id: null,
          permissions: ROUTER,
          valid_from: '2000-01-01',
          valid_to: null,
        },
      ],
    };
    const hrefs = navigationFor(scoped).flatMap((section) =>
      flattenNavigation(section.items).map((item) => item.href),
    );

    expect(hrefs).toContain('/invoice-designer');
    expect(hrefs).toContain('/documents/vouchers');
    expect(hrefs).toContain('/documents/routing');
  });

  it('omits what the actor may not reach', async () => {
    const session = await sessionFor({ permissions: ['company.read'] });
    const scoped: Session = {
      ...session,
      company: { ...session.company, id: COMPANY },
      grants: [
        {
          scope_type: 'tenant',
          scope_id: null,
          permissions: ['company.read'],
          valid_from: '2000-01-01',
          valid_to: null,
        },
      ],
    };
    const hrefs = navigationFor(scoped).flatMap((section) =>
      flattenNavigation(section.items).map((item) => item.href),
    );

    expect(hrefs).not.toContain('/invoice-designer');
    expect(hrefs).not.toContain('/documents/vouchers');
    expect(hrefs).not.toContain('/documents/routing');
  });
});
