import type { ReactNode } from 'react';
import {
  AuditIcon,
  BookIcon,
  CustomersIcon,
  DashboardIcon,
  PaymentsIcon,
  ReportsIcon,
  RolesIcon,
  SettingsIcon,
} from '@janso/ui';
import { BoxIcon, DocumentIcon, ReceiptIcon, StoreIcon } from '@janso/ui';
import type { Session } from './session';
import { accessReviewPermissions } from './lib/access-permissions';
import {
  organisationPermissions,
  platformNavigationPermissions,
} from './lib/session-authority';
import { companyPermission } from './lib/company-permissions';
import { accessContext } from './lib/access-context';
import { hasPeopleAccess } from './lib/access-permissions';
import {
  departmentDirectoryAccess,
  organisationPermission,
} from './lib/organisation-contract';
import { organisationNavigationAvailable } from './lib/organisation-navigation';
import {
  notificationAccess,
  notificationRoot,
  notificationSections,
} from './lib/notification-navigation';
import {
  notificationPermission,
  type NotificationOwner,
} from './lib/notification-ownership';
import { companyMasterPath, companyMastersFor } from './lib/company-masters';
import { reportCategories } from './lib/report-cards';
import { bookEntries } from './lib/book-cards';
import { logsAndActivitiesAccess, logsAndActivitiesPath } from './lib/logs-navigation';

export type NavItem = {
  label: string;
  href: string;
  icon: ReactNode;
  /**
   * The permission navigationFor checks for both the rail and command search.
   * Hiding a link is a courtesy; the route and its API enforce access independently.
   */
  permission?: string;
  companyRequired?: boolean;
  permissions?: readonly string[];
  children?: NavItem[];
};

export type NavSection = { label: string; items: NavItem[] };

/** Settings lives in the pinned rail footer and remains available to keyboard navigation. */
export const settingsNavItem: NavItem = {
  label: 'Company settings',
  href: '/settings',
  icon: <SettingsIcon />,
};

function notificationNav(owner: NotificationOwner): NavItem {
  const root = notificationRoot(owner);
  return {
    label:
      owner === 'platform'
        ? 'Platform notifications'
        : 'Notifications',
    href: root,
    icon: <SettingsIcon />,
    companyRequired: false,
    children: notificationSections
      .filter((item) => item.family)
      .map((item) => ({
        label: item.label,
        href: root + '/' + item.key,
        icon: <SettingsIcon />,
        permission: notificationPermission(
          owner,
          item.family,
          'action' in item ? item.action : 'read',
        ),
        companyRequired: false,
      })),
  };
}

/**
 * Grouped by what the user is doing, not by which service owns the data — a person
 * raising an invoice does not care that catalog and billing are separate deployments.
 */
export const navSections: NavSection[] = [
  {
    label: 'Operate',
    items: [
      { label: 'Business overview', href: '/', icon: <DashboardIcon /> },
      { label: 'Income', href: '/operate/income', icon: <ReceiptIcon />, permission: 'vouchers.read', companyRequired: true },
      { label: 'Expense', href: '/operate/expense', icon: <PaymentsIcon />, permission: 'vouchers.read', companyRequired: true },
      { label: 'Inventory', href: '/operate/inventory', icon: <BoxIcon />, permission: 'vouchers.read', companyRequired: true },
      {
        label: 'Voucher drafts',
        href: '/vouchers',
        icon: <ReceiptIcon />,
        permission: 'vouchers.read',
      },
    ],
  },
  {
    label: 'Books and Reports',
    items: [
      { label: 'Books', href: '/books', icon: <BookIcon />, permission: 'report.read', companyRequired: true, children: bookEntries.map(book => ({ label: book.title, href: '/books/' + book.key, icon: <BookIcon />, permission: 'report.read', companyRequired: true })) },
      { label: 'Reports', href: '/reports', icon: <ReportsIcon />, permission: 'report.read',
        children: reportCategories.map(category => ({ label: category.title, href: '/reports/' + category.key, icon: <ReportsIcon />, permission: 'report.read', companyRequired: true })),
      },
    ],
  },
  {
    label: 'Administer',
    items: [
      { label: 'Masters', href: '/masters', icon: <BoxIcon />, companyRequired: true },
      {
        /*
         * The designer was reachable only by typing its URL. It is a company-scoped
         * administrative capability like masters, so it belongs here — and the full-bleed
         * editor route group was always meant to be *navigated* to rather than reached by
         * changing origin (see `(editor)/layout.tsx`).
         */
        label: 'Print templates',
        href: '/invoice-designer',
        icon: <DocumentIcon />,
        permission: 'design.template.read',
        companyRequired: true,
        children: [
          {
            // A card for every kind of voucher: what it prints on (the standard layout unless
            // someone customized it), a way to customize it, and the voucher type it belongs to.
            // Gated like the gallery it sits under — being allowed to see layouts is what it
            // takes to see what a voucher prints on.
            label: 'Voucher print',
            href: '/documents/vouchers',
            icon: <ReceiptIcon />,
            permission: 'design.template.read',
            companyRequired: true,
          },
          {
            // Marked advanced in the rail itself: nobody needs it to print. Voucher print
            // customizes a voucher in one step; this is for conditions (currency, tax category).
            label: 'Document routing (advanced)',
            href: '/documents/routing',
            icon: <ReceiptIcon />,
            // Its own key: a reader may be allowed to see layouts without being allowed to
            // see, or change, which document prints on which one.
            permission: 'design.assignment.read',
            companyRequired: true,
          },
        ],
      },
      {
        label: 'Platform administration',
        href: '/platform',
        icon: <SettingsIcon />,
        children: [
          {
            label: 'Users, roles and permissions',
            href: '/platform/access',
            icon: <RolesIcon />,
            permission: 'platform.tenant_access.read',
            companyRequired: false,
            children: [
              {
                label: 'Tenant administrators',
                href: '/platform/access/administrators',
                icon: <CustomersIcon />,
                permission: 'platform.tenant_access.read',
                companyRequired: false,
              },
              {
                label: 'Tenant administrator role',
                href: '/platform/access/role',
                icon: <RolesIcon />,
                permission: 'platform.tenant_access.read',
                companyRequired: false,
              },
              {
                label: 'Administrator permissions',
                href: '/platform/access/permissions',
                icon: <SettingsIcon />,
                permission: 'platform.tenant_access.read',
                companyRequired: false,
              },
            ],
          },
          {
            label: 'Tenants / Workspaces',
            href: '/platform/tenants',
            icon: <StoreIcon />,
            permission: 'platform.tenant.read',
            companyRequired: false,
          },
          {
            label: 'Account approvals',
            href: '/platform/accounts',
            icon: <CustomersIcon />,
            permission: 'platform.account.read',
            companyRequired: false,
          },
          {
            label: 'Reference data',
            href: '/platform/references',
            icon: <BookIcon />,
            permission: 'platform.config.manage',
            companyRequired: false,
            children: [
              'countries',
              'states',
              'currencies',
              'languages',
              'timezones',
            ].map((kind) => ({
              label: kind[0].toUpperCase() + kind.slice(1),
              href: '/platform/references/' + kind,
              icon: <BookIcon />,
              permission: 'platform.config.manage',
              companyRequired: false,
            })),
          },
          notificationNav('platform'),
          {
            label: 'Platform details',
            href: '/platform/details',
            icon: <SettingsIcon />,
            permission: 'platform.config.manage',
            companyRequired: false,
          },
          {
            label: 'Fees and pricing',
            href: '/platform/pricing',
            icon: <PaymentsIcon />,
            permission: 'platform.config.manage',
            companyRequired: false,
          },
          {
            label: 'Platform history',
            href: '/platform/history',
            icon: <AuditIcon />,
            permissions: platformNavigationPermissions,
            companyRequired: false,
          },
        ],
      },
      {
        label: 'Administration',
        href: '/organisation',
        icon: <StoreIcon />,
        children: [
          {
            label: 'Manage companies',
            href: '/companies/manage',
            icon: <StoreIcon />,
          },
          {
            label: 'Roles & access',
            href: '/organisation/access',
            icon: <RolesIcon />,
            permission: 'role.read',
            companyRequired: false,
            children: [
              {
                label: 'Roles',
                href: '/roles',
                icon: <RolesIcon />,
                permission: 'role.read',
                companyRequired: false,
              },
              {
                label: 'Role assignments',
                href: '/assignments',
                icon: <RolesIcon />,
                permission: 'role.read',
                companyRequired: false,
              },
              {
                label: 'Permissions',
                href: '/permissions',
                icon: <RolesIcon />,
                permission: 'role.read',
                companyRequired: false,
              },
            ],
          },
          {
            label: 'Users',
            href: '/users',
            icon: <CustomersIcon />,
            permission: 'user.read',
            companyRequired: false,
          },
          {
            label: 'User groups',
            href: '/user-groups',
            icon: <CustomersIcon />,
            companyRequired: false,
          },
          {
            label: 'Departments',
            href: '/departments',
            icon: <StoreIcon />,
            companyRequired: true,
          },
          notificationNav('tenant'),
        ],
      },
      {
        label: 'Logs and activities',
        href: logsAndActivitiesPath,
        icon: <AuditIcon />,
        permissions: ['audit.read', 'activity.read'],
      },
    ],
  },
  {
    label: 'Your account',
    items: [
      {
        label: 'My access',
        href: '/my-access',
        icon: <RolesIcon />,
        companyRequired: false,
      },
    ],
  },
];

/** One resolved tree for rail and keyboard search. APIs independently authorize requests. */
export function navigationFor(session: Session, advanced?: boolean | null): NavSection[] {
  const allowed = (item: NavItem) => {
    if (item.href === logsAndActivitiesPath) {
      const access = logsAndActivitiesAccess(session);
      return access.audit || access.activities;
    }
    if (item.href === '/platform')
      return platformNavigationPermissions.some((key) =>
        session.permissions.includes(key),
      );
    if (item.href === '/organisation')
      return organisationNavigationAvailable(session);
    if (item.href === '/masters') return companyMastersFor(session).length > 0;
    if (item.href === '/vouchers' || item.href.startsWith('/operate/')) return !!session.company.id && companyPermission(session, 'vouchers.read', session.company.id);
    if (item.href === '/books' || item.href.startsWith('/books/') || item.href === '/reports' || item.href.startsWith('/reports/')) return !!session.company.id && companyPermission(session, 'report.read', session.company.id);
    for (const owner of ['platform', 'tenant'] as const) {
      const root = notificationRoot(owner);
      if (item.href === root || item.href.startsWith(root + '/')) {
        const keys =
          owner === 'platform'
            ? session.permissions
            : organisationPermissions(session);
        return item.permission
          ? keys.includes(item.permission)
          : notificationAccess(owner, keys);
      }
    }
    if (item.href === '/companies/manage')
      return (
        companyPermission(session, 'company.read') ||
        companyPermission(session, 'company.create')
      );
    if (['/organisation/access', '/roles', '/assignments', '/permissions'].includes(item.href))
      return accessReviewPermissions(session).includes('role.read');
    if (item.href === '/users') return hasPeopleAccess(accessContext(session));
    if (item.href === '/user-groups')
      return (
        organisationPermission(accessContext(session), 'user-groups', 'read') ||
        organisationPermission(accessContext(session), 'user-groups', 'manage')
      );
    if (item.href === '/departments')
      return (
        departmentDirectoryAccess(accessContext(session)) ||
        organisationPermission(accessContext(session), 'departments', 'manage')
      );
    const companyRequired =
      item.companyRequired ??
      !['/', '/platform', '/organisation', '/roles'].includes(item.href);
    if (companyRequired && !session.company.id) return false;
    if (item.href.startsWith('/accounting'))
      return (
        !!session.company.id &&
        (item.permission
          ? companyPermission(session, item.permission, session.company.id)
          : (item.permissions ?? []).some((key) =>
              companyPermission(session, key, session.company.id),
            ))
      );
    if (
      item.href.startsWith('/masters/') ||
      item.href.startsWith('/products/') ||
      item.href === '/tax' ||
      item.href.startsWith('/tax/') ||
      // A document template belongs to a company, so the grant that opens it has to be
      // company-scoped too. The generic branch below tests the flat permission set, which
      // would let a grant for company A light up the link while company B is open.
      item.href === '/invoice-designer' ||
      item.href === '/activity' ||
      item.href === '/audit' ||
      item.href.startsWith('/documents/')
    )
      return (
        !!item.permission &&
        companyPermission(session, item.permission, session.company.id)
      );
    return (
      (!item.permission || session.permissions.includes(item.permission)) &&
      (!item.permissions ||
        item.permissions.some((key) => session.permissions.includes(key)))
    );
  };
  const resolve = (items: NavItem[]): NavItem[] =>
    items.filter(item => advanced === undefined || advanced === true || item.href !== '/masters/product-families').filter(allowed).map((item) => ({
      ...item,
      ...(item.href === '/masters/items' && advanced !== undefined && advanced !== true ? { label: 'Products' } : {}),
      ...(item.children ? { children: resolve(item.children) } : {}),
    }));
  return navSections
    .map((section) => ({ ...section, items: resolve(section.items) }))
    .filter((section) => section.items.length > 0);
}

export function flattenNavigation(items: NavItem[]): NavItem[] {
  return items.flatMap((item) => [
    item,
    ...flattenNavigation(item.children ?? []),
  ]);
}

/** Deeper pages belong to their nearest visible link in the two-level sidebar. */
export function sidebarCurrentHref(items: NavItem[], destination: string): string | undefined {
  if (['/audit', '/activity'].includes(destination) && flattenNavigation(items).some(item => item.href === logsAndActivitiesPath)) return logsAndActivitiesPath;
  if (companyMasterPath(destination) && flattenNavigation(items).some(item => item.href === '/masters')) return '/masters';
  const current = flattenNavigation(items)
    .filter(item => destination === item.href || item.href !== '/' && destination.startsWith(item.href + '/'))
    .sort((left, right) => right.href.length - left.href.length)[0]?.href;
  if (!current) return undefined;
  for (const item of items) {
    if (item.href === current) return current;
    const owner = item.children?.find(child => flattenNavigation([child]).some(descendant => descendant.href === current));
    if (owner) return owner.href;
  }
  return undefined;
}
