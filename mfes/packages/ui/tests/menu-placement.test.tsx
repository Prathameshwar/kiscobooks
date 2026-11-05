import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { Menu } from '../src/components/Menu';

const originalWidth = window.innerWidth;
const originalHeight = window.innerHeight;
let anchorLeft = 16,
  anchorRight = 100,
  anchorTop = 160,
  panelWidth = 240;
  anchorTop = 160;
  Object.defineProperty(window, 'innerHeight', { configurable: true, value: 1000 });
beforeEach(() => {
  Object.defineProperty(window, 'innerWidth', {
    configurable: true,
    value: 390,
  });
  anchorLeft = 16;
  anchorRight = 100;
  panelWidth = 240;
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(
    function (this: HTMLElement) {
      const menu = this.getAttribute('role') === 'menu';
      const width = menu ? panelWidth : anchorRight - anchorLeft;
      const left = menu
        ? this.style.left
          ? Number.parseFloat(this.style.left)
          : window.innerWidth -
            Number.parseFloat(this.style.right || '0') -
            width
        : anchorLeft;
      return {
        left,
        right: left + width,
        width,
        top: anchorTop,
        bottom: anchorTop + 36,
        height: 36,
        x: left,
        y: 160,
        toJSON: () => ({}),
      };
    },
  );
});
afterEach(() => {
  Object.defineProperty(window, 'innerHeight', { configurable: true, value: originalHeight });
  Object.defineProperty(window, 'innerWidth', {
    configurable: true,
    value: originalWidth,
  });
  vi.restoreAllMocks();
});
const items = [{ id: 'units', label: 'Selling / purchasing units' }];

it('keeps keyboard-opened menus visible when the focused row has not yet scrolled into view', async () => {
  anchorTop = 1150;
  render(<Menu label="Related actions" items={items} onSelect={vi.fn()} />);
  screen.getByRole('button', { name: 'Related actions' }).focus();
  await userEvent.keyboard('{ArrowDown}');
  const menu = screen.getByRole('menu');
  expect(Number.parseFloat(menu.style.bottom)).toBeGreaterThanOrEqual(8);
  expect(Number.parseFloat(menu.style.maxHeight)).toBeLessThanOrEqual(window.innerHeight - 16);
  expect(screen.getByRole('menuitem')).toHaveFocus();
});

it('keeps an end-aligned menu inside a phone viewport when the trigger is near the left edge', async () => {
  render(<Menu label="Related actions" items={items} onSelect={vi.fn()} />);
  await userEvent.click(
    screen.getByRole('button', { name: 'Related actions' }),
  );
  const rect = screen.getByRole('menu').getBoundingClientRect();
  expect(rect.left).toBeGreaterThanOrEqual(8);
  expect(rect.right).toBeLessThanOrEqual(window.innerWidth - 8);
});

it('keeps a start-aligned menu inside the trailing viewport edge', async () => {
  anchorLeft = 300;
  anchorRight = 336;
  render(
    <Menu
      label="Related actions"
      align="start"
      items={items}
      onSelect={vi.fn()}
    />,
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Related actions' }),
  );
  const rect = screen.getByRole('menu').getBoundingClientRect();
  expect(rect.right).toBeLessThanOrEqual(window.innerWidth - 8);
});

it('re-measures menu content and window resizing without losing the active item', async () => {
  anchorLeft = 250;
  anchorRight = 286;
  const view = render(
    <Menu label="Related actions" items={items} onSelect={vi.fn()} />,
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Related actions' }),
  );
  panelWidth = 300;
  view.rerender(
    <Menu
      label="Related actions"
      items={[
        ...items,
        { id: 'family', label: 'Family manufacturer assignments' },
      ]}
      onSelect={vi.fn()}
    />,
  );
  Object.defineProperty(window, 'innerWidth', {
    configurable: true,
    value: 340,
  });
  fireEvent(window, new Event('resize'));
  expect(
    screen.getByRole('menu').getBoundingClientRect().left,
  ).toBeGreaterThanOrEqual(8);
  expect(
    screen.getByRole('menuitem', { name: 'Selling / purchasing units' }),
  ).toHaveFocus();
});
