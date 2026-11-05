/**
 * TopBar, ContextChip, RoleChip, NotificationBell, CollapseToggle and UserMenu.
 *
 * The menu's keyboard contract is the substance of these tests: a `role="menu"` that does
 * not cycle, does not return focus on Escape and does not close on Tab is a worse control
 * than a plain list, so each of those is asserted rather than assumed.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it, vi } from 'vitest';

import { CollapseToggle } from '../src/components/CollapseToggle';
import { ContextChip, RoleChip } from '../src/components/Chips';
import { NotificationBell } from '../src/components/NotificationBell';
import { TopBar } from '../src/components/TopBar';
import { UserMenu, type UserMenuItem } from '../src/components/UserMenu';
import { LogoutIcon, SettingsIcon } from '../src/components/icons-console';
import { UserIcon } from '../src/components/icons';

const SHELL_CSS = readFileSync(
  join(__dirname, '..', 'src', 'styles', 'shell.css'),
  'utf8',
);

describe('TopBar', () => {
  it('lets the account cluster shrink without clipping its menu at tablet widths', () => {
    expect(SHELL_CSS).toMatch(/\.janso-topbar__right\s*\{[^}]*min-width:\s*0/);
    expect(SHELL_CSS).toMatch(/\.janso-usermenu\s*\{[^}]*min-width:\s*0/);
  });
  it('renders the left and right clusters as a banner', () => {
    const { container } = render(
      <TopBar left={<span>collapse</span>} right={<span>cluster</span>}>
        <span>middle</span>
      </TopBar>,
    );

    expect(screen.getByRole('banner')).toHaveClass('janso-topbar');
    expect(container.querySelector('.janso-topbar__left')).toHaveTextContent('collapse');
    expect(container.querySelector('.janso-topbar__mid')).toHaveTextContent('middle');
    expect(container.querySelector('.janso-topbar__right')).toHaveTextContent('cluster');
  });

  it('renders no empty slot wrappers', () => {
    const { container, unmount } = render(<TopBar right={<span>cluster</span>} />);

    expect(container.querySelector('.janso-topbar__left')).not.toBeInTheDocument();
    expect(container.querySelector('.janso-topbar__mid')).not.toBeInTheDocument();
    expect(container.querySelector('.janso-topbar__right')).toBeInTheDocument();
    unmount();

    const leftOnly = render(<TopBar left={<span>collapse</span>} />);
    expect(leftOnly.container.querySelector('.janso-topbar__left')).toBeInTheDocument();
    expect(leftOnly.container.querySelector('.janso-topbar__right')).not.toBeInTheDocument();
  });

  it('sticks at the documented stacking order with a hairline bottom border', () => {
    expect(SHELL_CSS).toMatch(/\.janso-shell__topbar\s*\{[^}]*position: sticky/);
    expect(SHELL_CSS).toMatch(/\.janso-shell__topbar\s*\{[^}]*z-index: var\(--janso-z-topbar\)/);
    expect(SHELL_CSS).toMatch(
      /\.janso-shell__topbar\s*\{[^}]*border-bottom: 1px solid var\(--janso-line\)/,
    );
  });
});

describe('ContextChip', () => {
  it('renders the label with a decorative dot', () => {
    const { container } = render(<ContextChip label="FY 2026-27" />);

    expect(screen.getByText('FY 2026-27')).toHaveClass('janso-chip__label');
    expect(container.querySelector('.janso-chip__dot')).toHaveAttribute('aria-hidden', 'true');
    expect(container.querySelector('.janso-chip')).toHaveAttribute('data-tone', 'neutral');
  });

  it.each([
    ['neutral', 'no status'],
    ['brand', 'active'],
    ['success', 'healthy'],
    ['warn', 'needs attention'],
    ['danger', 'critical'],
    ['info', 'for information'],
  ] as const)('states the %s tone in words, never colour alone', (tone, description) => {
    const { container } = render(<ContextChip label="Period" tone={tone} />);
    const chip = container.querySelector('.janso-chip');

    expect(chip).toHaveAttribute('data-tone', tone);
    expect(chip).toHaveTextContent(`Period (${description})`);
  });

  it('carries each tone on the border and the accent, not as a tinted fill', () => {
    for (const tone of ['brand', 'success', 'warn', 'danger', 'info']) {
      expect(SHELL_CSS).toContain(`.janso-chip[data-tone='${tone}']`);
      expect(SHELL_CSS).toContain(`border-color: var(--janso-${tone}-line)`);
      expect(SHELL_CSS).toContain(`--janso-chip-accent: var(--janso-${tone}-ink)`);
    }
    // The pill itself stays a quiet surface: a chip states context, and two saturated pills
    // side by side in the top bar read as two alerts instead.
    expect(SHELL_CSS).toMatch(/\.janso-chip \{[^}]*background: var\(--janso-surface\)/);
    expect(SHELL_CSS).toMatch(/\.janso-chip__dot \{[^}]*background: var\(--janso-chip-accent\)/);
  });
});

describe('RoleChip', () => {
  it('renders the role behind a default shield', () => {
    const { container } = render(<RoleChip label="Accountant" />);

    expect(screen.getByText('Accountant')).toHaveClass('janso-chip__label');
    const icon = container.querySelector('.janso-chip__icon');
    expect(icon).toHaveAttribute('aria-hidden', 'true');
    expect(icon?.querySelector('svg')).toBeInTheDocument();
  });

  it('accepts a caller icon', () => {
    const { container } = render(<RoleChip label="Owner" icon={<UserIcon size={14} />} />);
    expect(container.querySelectorAll('.janso-chip__icon svg')).toHaveLength(1);
  });
});

describe('NotificationBell', () => {
  it('puts the unread count in the accessible name and shows the dot', () => {
    const { container } = render(<NotificationBell count={3} />);

    expect(screen.getByRole('button', { name: 'Notifications, 3 unread' })).toBeInTheDocument();
    expect(container.querySelector('.janso-btn__dot')).toBeInTheDocument();
  });

  it('renders no dot and a plain name at zero', () => {
    const { container } = render(<NotificationBell count={0} />);

    expect(screen.getByRole('button', { name: 'Notifications' })).toBeInTheDocument();
    expect(container.querySelector('.janso-btn__dot')).not.toBeInTheDocument();
  });

  it('calls onOpen when activated', async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    render(<NotificationBell count={1} onOpen={onOpen} />);

    await user.click(screen.getByRole('button', { name: 'Notifications, 1 unread' }));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });
});

describe('CollapseToggle', () => {
  it('names the action and carries the state on an expanded rail', () => {
    render(<CollapseToggle collapsed={false} onToggle={() => undefined} />);

    const button = screen.getByRole('button', { name: 'Collapse sidebar' });
    expect(button).toHaveAttribute('aria-expanded', 'true');
    expect(button).toHaveAttribute('title', 'Collapse sidebar');
  });

  it('flips the name and the state when collapsed', () => {
    render(<CollapseToggle collapsed onToggle={() => undefined} />);

    const button = screen.getByRole('button', { name: 'Expand sidebar' });
    expect(button).toHaveAttribute('aria-expanded', 'false');
    expect(button).toHaveClass('janso-collapse--collapsed');
  });

  it('calls onToggle when activated', async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    render(<CollapseToggle collapsed={false} onToggle={onToggle} />);

    await user.click(screen.getByRole('button', { name: 'Collapse sidebar' }));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });
});

const MENU_ITEMS: UserMenuItem[] = [
  { id: 'profile', label: 'Your profile', icon: <UserIcon size={16} /> },
  { id: 'settings', label: 'Preferences', icon: <SettingsIcon size={16} /> },
  { id: 'signout', label: 'Sign out', icon: <LogoutIcon size={16} /> },
];

function renderMenu(onSelect?: (id: string) => void) {
  return render(
    <UserMenu
      name="Priya Sharma"
      secondary="Finance manager"
      items={MENU_ITEMS}
      onSelect={onSelect}
    />,
  );
}

describe('UserMenu', () => {
  it('keeps separators outside the keyboard item sequence and restores focus', async () => {
    const user = userEvent.setup();
    render(<UserMenu name="Account" items={[{ id:'password',label:'Change password' }, { id:'signout',label:'Sign out',separatorBefore:true }]} />);
    const trigger = screen.getByRole('button', {name:/Account/}); await user.click(trigger);
    expect(screen.getByRole('separator')).not.toHaveAttribute('tabindex');
    expect(screen.getByRole('menuitem', {name:'Change password'})).toHaveFocus();
    await user.keyboard('{ArrowDown}'); expect(screen.getByRole('menuitem', {name:'Sign out'})).toHaveFocus();
    await user.keyboard('{Escape}'); expect(trigger).toHaveFocus();
  });
  it('renders a closed trigger showing the name and the secondary line', () => {
    renderMenu();

    const trigger = screen.getByRole('button', { name: /Priya Sharma/ });
    expect(trigger).toHaveAttribute('aria-haspopup', 'menu');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(trigger).not.toHaveAttribute('aria-controls');
    expect(screen.getByText('Finance manager')).toBeInTheDocument();
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('opens on click, focusing the first item', async () => {
    const user = userEvent.setup();
    renderMenu();

    const trigger = screen.getByRole('button', { name: /Priya Sharma/ });
    await user.click(trigger);

    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(trigger).toHaveAttribute('aria-controls', screen.getByRole('menu').id);

    const items = screen.getAllByRole('menuitem');
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveFocus();
    // One tab stop for the whole menu; the arrows move within it.
    expect(items[1]).toHaveAttribute('tabindex', '-1');
  });

  it('opens with ArrowDown on the first item and with ArrowUp on the last', async () => {
    const user = userEvent.setup();
    renderMenu();

    const trigger = screen.getByRole('button', { name: /Priya Sharma/ });
    trigger.focus();
    await user.keyboard('{ArrowDown}');
    expect(screen.getAllByRole('menuitem')[0]).toHaveFocus();

    await user.keyboard('{Escape}');
    trigger.focus();
    await user.keyboard('{ArrowUp}');
    expect(screen.getAllByRole('menuitem')[2]).toHaveFocus();
  });

  it('cycles with the arrow keys in both directions', async () => {
    const user = userEvent.setup();
    renderMenu();

    await user.click(screen.getByRole('button', { name: /Priya Sharma/ }));

    await user.keyboard('{ArrowDown}');
    expect(screen.getAllByRole('menuitem')[1]).toHaveFocus();
    await user.keyboard('{ArrowDown}');
    expect(screen.getAllByRole('menuitem')[2]).toHaveFocus();
    // past the end, back to the top
    await user.keyboard('{ArrowDown}');
    expect(screen.getAllByRole('menuitem')[0]).toHaveFocus();
    // and off the top, round to the end
    await user.keyboard('{ArrowUp}');
    expect(screen.getAllByRole('menuitem')[2]).toHaveFocus();

    await user.keyboard('{Home}');
    expect(screen.getAllByRole('menuitem')[0]).toHaveFocus();
    await user.keyboard('{End}');
    expect(screen.getAllByRole('menuitem')[2]).toHaveFocus();
    // and step back through the middle, not just around the ends
    await user.keyboard('{ArrowUp}');
    expect(screen.getAllByRole('menuitem')[1]).toHaveFocus();
  });

  it('ignores a key it does not own, leaving the menu open on the same item', async () => {
    const user = userEvent.setup();
    renderMenu();

    await user.click(screen.getByRole('button', { name: /Priya Sharma/ }));
    await user.keyboard('x');

    expect(screen.getByRole('menu')).toBeInTheDocument();
    expect(screen.getAllByRole('menuitem')[0]).toHaveFocus();
  });

  it('closes on Escape and returns focus to the trigger', async () => {
    const user = userEvent.setup();
    renderMenu();

    const trigger = screen.getByRole('button', { name: /Priya Sharma/ });
    await user.click(trigger);
    await user.keyboard('{Escape}');

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('closes on Tab, because a menu is not a dialog', async () => {
    const user = userEvent.setup();
    renderMenu();

    await user.click(screen.getByRole('button', { name: /Priya Sharma/ }));
    await user.tab();

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('closes on an outside click without stealing focus back', async () => {
    const user = userEvent.setup();
    renderMenu();

    const trigger = screen.getByRole('button', { name: /Priya Sharma/ });
    await user.click(trigger);
    await user.click(document.body);

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(trigger).not.toHaveFocus();
  });

  it('closes again when the trigger is clicked a second time', async () => {
    const user = userEvent.setup();
    renderMenu();

    const trigger = screen.getByRole('button', { name: /Priya Sharma/ });
    await user.click(trigger);
    await user.click(trigger);

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('reports the chosen item once and closes back onto the trigger', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    renderMenu(onSelect);

    const trigger = screen.getByRole('button', { name: /Priya Sharma/ });
    await user.click(trigger);
    await user.click(screen.getByRole('menuitem', { name: 'Sign out' }));

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith('signout');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('does not read a decorative item icon as part of the item name', async () => {
    const user = userEvent.setup();
    renderMenu();

    await user.click(screen.getByRole('button', { name: /Priya Sharma/ }));
    const item = screen.getByRole('menuitem', { name: 'Preferences' });
    expect(item.querySelector('.janso-usermenu__item-icon')).toHaveAttribute(
      'aria-hidden',
      'true',
    );
  });

  it('renders the popup on the overlay surface at the popover layer', () => {
    expect(SHELL_CSS).toMatch(
      /\.janso-usermenu__menu\s*\{[^}]*z-index: var\(--janso-z-popover\)/,
    );
    expect(SHELL_CSS).toMatch(/\.janso-usermenu__menu\s*\{[^}]*background: var\(--janso-overlay\)/);
    expect(SHELL_CSS).toMatch(
      /\.janso-usermenu__menu\s*\{[^}]*box-shadow: var\(--janso-shadow-popover\)/,
    );
    expect(SHELL_CSS).toMatch(
      /\.janso-usermenu__menu\s*\{[^}]*border-radius: var\(--janso-radius-md\)/,
    );
  });

  it('renders without a secondary line when none is given', () => {
    render(<UserMenu name="Priya Sharma" items={MENU_ITEMS} />);
    expect(screen.queryByText('Finance manager')).not.toBeInTheDocument();
  });

  it('never opens an empty menu', async () => {
    const user = userEvent.setup();
    render(<UserMenu name="Priya Sharma" items={[]} />);

    const trigger = screen.getByRole('button', { name: /Priya Sharma/ });
    // `items.length - 1` is -1 with no items: the menu opened empty, with nothing focusable
    // and an active index pointing outside the list.
    expect(trigger).not.toHaveAttribute('aria-haspopup');
    expect(trigger).not.toHaveAttribute('aria-expanded');

    await user.click(trigger);
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();

    trigger.focus();
    await user.keyboard('{ArrowUp}');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    await user.keyboard('{ArrowDown}');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('renders items without icons', async () => {
    const user = userEvent.setup();
    render(<UserMenu name="Priya Sharma" items={[{ id: 'only', label: 'Only item' }]} />);

    await user.click(screen.getByRole('button', { name: /Priya Sharma/ }));
    const item = screen.getByRole('menuitem', { name: 'Only item' });
    expect(item.querySelector('.janso-usermenu__item-icon')).not.toBeInTheDocument();

    // A single item still cycles — onto itself.
    await user.keyboard('{ArrowDown}');
    expect(item).toHaveFocus();
  });
});

describe('the top bar as a popover host', () => {
  /*
   * The bar contains the one popover in the shell, and it opens *below* the 60px band. That
   * makes "does the bar clip its own children" a real contract, not a styling detail: an
   * `overflow` other than `visible` turns the bar into a scroll container, which clips
   * descendants and shows the menu as a sliver with a scrollbar instead of a popover.
   *
   * This is asserted against the stylesheet because jsdom computes no layout and would report
   * the menu as perfectly visible either way — which is exactly why the bug shipped.
   */
  it('never becomes a scroll container, or it would clip the menu it hosts', () => {
    const bar = SHELL_CSS.slice(SHELL_CSS.indexOf('.janso-topbar {'));
    const rule = bar.slice(0, bar.indexOf('}'));

    expect(rule).not.toMatch(/overflow/);
  });

  it('sheds content as it narrows instead of scrolling', () => {
    // Reflow to 320px without a scrollbar (WCAG 1.4.10) has to come from dropping controls:
    // the collapse toggle, then the chips, then the user's name — leaving the avatar.
    expect(SHELL_CSS).toMatch(/@media \(max-width: 960px\)[\s\S]*?\.janso-topbar__left \{\n    display: none/);
    expect(SHELL_CSS).toMatch(/@media \(max-width: 720px\)[\s\S]*?\.janso-topbar__mid/);
    expect(SHELL_CSS).toMatch(/@media \(max-width: 720px\)[\s\S]*?\.janso-topbar__right > \.janso-chip\s*\{\s*display: none/);
    expect(SHELL_CSS).toMatch(/@media \(max-width: 640px\)[\s\S]*?\.janso-usermenu__text/);
    // The search keycap rides the collapse-toggle step rather than a breakpoint of its own.
    expect(SHELL_CSS).toMatch(
      /@media \(max-width: 960px\)[\s\S]*?\.janso-topbar__mid \.janso-command__kbd \{\n    display: none/,
    );
  });

  /*
   * Between the breakpoints the bar has to *shrink*, not just shed, and that is a different
   * contract from the one above — the one the ladder quietly depended on and never asserted.
   *
   * The regression it guards: `.janso-topbar__mid` was `flex: 1`, i.e. a `0%` basis. Shrinking
   * is apportioned by `flex-shrink × flex-basis`, so a zero basis gave that slot a scaled shrink
   * factor of zero and pushed **all** of it onto the right cluster — whose chips are `nowrap` and
   * cannot shrink either. The cluster then overflowed a band that cannot scroll, and the avatar
   * and theme switcher left the page. It was invisible while the middle slot held one control
   * with slack either side; a second one ("New") brought it into laptop widths.
   *
   * jsdom computes no layout, so these are stylesheet assertions — which is precisely why the
   * original bug shipped past a green suite.
   */
  describe('the bar between its breakpoints', () => {
    /*
     * Anchored at a line start on purpose: a plain `indexOf('.janso-chip {')` also matches the
     * tail of `.janso-topbar__right > .janso-chip {`, so the descendant rule was being read as
     * the base one and this helper quietly asserted against the wrong block.
     */
    const rule = (selector: string) => {
      const start = SHELL_CSS.search(
        new RegExp('^' + selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ' \\{', 'm'),
      );
      expect(start, `${selector} is not a top-level rule in shell.css`).toBeGreaterThan(-1);
      return SHELL_CSS.slice(start, SHELL_CSS.indexOf('}', start));
    };

    it('gives the middle slot a content basis, so it is not exempt from shrinking', () => {
      expect(rule('.janso-topbar__mid')).toMatch(/flex:\s*1\s+1\s+auto/);
      // `flex: 1` / `flex: 1 1 0` here is the bug. Spelled out so the diff reads as a decision.
      expect(rule('.janso-topbar__mid')).not.toMatch(/flex:\s*1\s*;|flex:\s*1\s+1\s+0/);
    });

    it('lets the right cluster give way as well as park itself at the end', () => {
      expect(rule('.janso-topbar__right')).toMatch(/flex:\s*0\s+1\s+auto/);
      expect(rule('.janso-topbar__right')).toMatch(/min-width:\s*0/);
      expect(rule('.janso-topbar__right')).toMatch(/margin-inline-start:\s*auto/);
    });

    it('spends the search before the primary action, which holds its size', () => {
      expect(rule('.janso-topbar__mid > .janso-command-trigger')).toMatch(/min-width:\s*7rem/);
      expect(rule('.janso-topbar__mid > .janso-menu')).toMatch(/flex:\s*none/);
    });

    it('lets a chip shrink to a floor instead of shoving the cluster off the bar', () => {
      expect(rule('.janso-topbar__right > .janso-chip')).toMatch(/min-width:\s*4\.5rem/);
    });

    it('lets a long company name ellipsize inside its own pill', () => {
      // Without `min-width: 0` the label's automatic minimum size is its min-content width, so
      // the ellipsis beside it never fires and the text overflows the chip's border.
      const label = rule('.janso-chip__label');
      expect(label).toMatch(/min-width:\s*0/);
      expect(label).toMatch(/text-overflow:\s*ellipsis/);
      expect(rule('.janso-chip')).toMatch(/max-width:\s*22ch/);
    });
  });

  it('names the trigger independently of the text it may hide', () => {
    // Two places hide `.janso-usermenu__text`: a collapsed rail and a narrow bar. Before the
    // `aria-label`, the control lost its accessible name along with its label in both.
    render(
      <UserMenu name="Priya Sharma" secondary="Sharma Traders" items={MENU_ITEMS} />,
    );

    const trigger = screen.getByRole('button', { name: 'Priya Sharma' });
    expect(trigger).toHaveAttribute('aria-label', 'Priya Sharma');
    // `secondary` is context, not identity, so it stays out of the name.
    expect(trigger.getAttribute('aria-label')).not.toContain('Sharma Traders');
  });
});
