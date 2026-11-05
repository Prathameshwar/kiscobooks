'use client';

import { Fragment, useState, type ReactNode } from 'react';
import {
  AppFooter,
  AppShell,
  Avatar,
  CollapseToggle,
  CommandPalette,
  CommandTrigger,
  ContextChip,
  Menu,
  NotificationBell,
  PlusIcon,
  Rail,
  RailFooter,
  RailGroup,
  RailItem,
  RailSection,
  ThemeSwitcher,
  TopBar,
  UserMenu,
  Wordmark,
  currentYear,
  useCommandPaletteShortcut,
  type CommandItem,
} from '@janso/ui';
import { goTo, authActionUrl } from '../lib/navigate';
import { flattenNavigation, navigationFor, settingsNavItem, sidebarCurrentHref, type NavItem } from '../nav';
import { ContextPicker } from './ContextPicker';
import { newVoucherActions, showNewVoucher } from '../lib/new-voucher-actions';
import type { CompanyContext } from '../lib/company-context';
import type { Session } from '../session';
import { useProductMode } from './ProductModeProvider';

/*
 * Build keyboard destinations from the same resolved sections as the rail. Object-level
 * authorization remains with each page/API, regardless of presentation filtering.
 */
function commandItems(session: Session, advanced?: boolean | null): CommandItem[] { return [...navigationFor(session, advanced), { label: 'Support', items: [settingsNavItem] }].flatMap((section) =>
  flattenNavigation(section.items).map((item) => ({
    id: item.href,
    label: item.label,
    icon: item.icon,
    hint: section.label,
    group: 'Go to',
  })),
); }

/**
 * The console's own composition of the shared shell: which nav sections exist, what sits
 * in the top bar, what the footer links to. The shell primitives themselves live in
 * `@janso/ui` because every authenticated MFE will need them; this arrangement is policy
 * and stays in the app.
 *
 * The session is a prop, resolved per request by the page's Server Component. Importing it
 * from module scope would share one user's context across every request the server process
 * handles (see `session.ts`).
 */
export function ConsoleShell({
  children,
  activeHref,
  session,
  context,
}: {
  children: ReactNode;
  activeHref: string;
  session: Session;
  /** The company and financial-year context the rail switches between. */
  context: CompanyContext;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [unread] = useState(3);
  const [paletteOpen, setPaletteOpen] = useState(false);
  useCommandPaletteShortcut(() => setPaletteOpen(true));
  const mode = useProductMode();
  const advanced = mode ? mode.data?.product_family_sku_enabled ?? null : undefined;
  const sections = navigationFor(session, advanced);
  const commands = commandItems(session, advanced);
  const path = activeHref.split('?')[0]!;
  const destination = /^\/companies\/[^/]+\/(?:configuration|years)(?:\/|$)/.test(path) ? '/settings'
      : /^\/companies\/[^/]+(?:\/edit)?$/.test(path) ? '/companies/manage' : path;
  const current = sidebarCurrentHref([...sections.flatMap(section => section.items), settingsNavItem], destination);
  const itemLink = (item: NavItem): ReactNode => item.children?.length ? <RailGroup key={item.href} icon={item.icon} label={item.label} href={item.href} active={current === item.href} containsActive={item.children.some(child => child.href === current)}>
    {item.children.map(child => <RailItem key={child.href} icon={child.icon} label={child.label} href={child.href} active={child.href === current} />)}
  </RailGroup>
    : <RailItem key={item.href} icon={item.icon} label={item.label} href={item.href} active={item.href === current} />;

  const rail = (
    <Rail
      brand={<Wordmark size={28} nameSize="1.0625rem" strapline="Always balances" />}
      switcher={<ContextPicker session={session} context={context} />}
      footer={
        <>
          <RailFooter>
            <RailItem
              {...settingsNavItem}
              active={current === settingsNavItem.href}
            />
          </RailFooter>
          {/*
           * Who you are signed in as, pinned at the foot of the rail. It repeats the top
           * bar's avatar on purpose: in a multi-company product, "which account am I posting
           * as" is worth answering without opening a menu. The menu stays the only
           * interactive copy — this one is a label.
           *
           * It sits *beside* `RailFooter`, not inside it: that element is a list of
           * `RailItem`s, and a `div` is not a list item.
           */}
          <div className="console-rail-user">
            <Avatar name={session.user.name} shape="round" />
            <span className="console-rail-user__text">
              <span className="console-rail-user__name">{session.user.name}</span>
              <span className="console-rail-user__org">{session.user.secondary}</span>
            </span>
          </div>
        </>
      }
    >
      {sections.map((section) => (
        <RailSection key={section.label} label={section.label}>
          {section.items.map(itemLink)}
        </RailSection>
      ))}
    </Rail>
  );

  const topBar = (
    <TopBar
      left={<CollapseToggle collapsed={collapsed} onToggle={() => setCollapsed((v) => !v)} />}
      right={
        <>
          <ContextChip label={session.company.name} tone={session.company.id ? 'success' : 'warn'} />
          {session.permissions.includes('period.read') && context.fiscalYear ? <ContextChip label={context.fiscalYear.code} tone="info" /> : null}
          <ContextChip label={'Account: ' + session.role} />
          <ThemeSwitcher />
          <NotificationBell count={unread} />
          <UserMenu
            name={session.user.name}
            secondary={session.user.secondary}
            items={[
              { id: 'access', label: 'My access' },
              { id: 'password', label: 'Change password' },
              { id: 'signout', label: 'Sign out', separatorBefore: true },
            ]}
            onSelect={(id) => {
              // Auth owns the cookie and confirms its CSRF-protected logout POST.
              if (id === 'signout') goTo(authActionUrl('/logout'));
              if (id === 'password') goTo(authActionUrl('/change-password'));
              if (id === 'access') goTo('/my-access');
            }}
          />
        </>
      }
    >
      <CommandTrigger onOpen={() => setPaletteOpen(true)} />
      {/*
       * The bar's one leading verb, beside the way in to everything else. Items are ordinary
       * links, so middle-click and open-in-new-tab work; `onSelect` is the keyboard path, and
       * each id is its own destination. Shown to every reader with a company open — see the
       * note on `newVoucherActions` for why this one control is not role-gated.
       */}
      {showNewVoucher(session) ? (
        <Menu
          label="New voucher"
          triggerLabel="New"
          triggerVariant="primary"
          icon={<PlusIcon size={14} />}
          items={newVoucherActions}
          align="start"
          onSelect={goTo}
        />
      ) : null}
    </TopBar>
  );

  return (
    <AppShell
      rail={rail}
      topBar={topBar}
      collapsed={collapsed}
      onToggleCollapsed={() => setCollapsed((v) => !v)}
      footer={
        <AppFooter
          links={[]}
          copyright={`KiscoBooks · © ${currentYear()} Khushiyan Enterprise. All rights reserved.`}
        />
      }
    >
      <Fragment key={session.company.id + ':' + (context.fiscalYear?.id ?? '')}>{children}</Fragment>
      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        items={commands}
        onSelect={goTo}
      />
    </AppShell>
  );
}
