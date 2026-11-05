import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it } from 'vitest';
import { RailGroup, RailItem, RailSection } from '../src/components/Rail';

it('opens the current subtree and keeps the working parent link available when collapsed', async () => {
  const user = userEvent.setup();
  render(<RailSection label="Administer"><RailGroup label="Organisation" href="/organisation" icon={<span />} containsActive><RailItem label="Users" href="/users" icon={<span />} active /></RailGroup></RailSection>);
  expect(screen.getByRole('link', { name: 'Users' })).toHaveAttribute('aria-current', 'page');
  await user.click(screen.getByRole('button', { name: 'Collapse Organisation menu' }));
  expect(screen.getByRole('button', { name: 'Expand Organisation menu' })).toHaveAttribute('aria-expanded', 'false');
  expect(screen.getByRole('link', { name: 'Organisation' })).toHaveAttribute('href', '/organisation');
});
it('supports keyboard disclosure without moving focus to a hidden destination', async () => {
  const user = userEvent.setup();
  render(<RailSection label="Administer"><RailGroup label="Platform" href="/platform" icon={<span />}><RailItem label="Tenants" href="/platform/tenants" icon={<span />} /></RailGroup></RailSection>);
  const trigger = screen.getByRole('button', { name: 'Expand Platform menu' }); trigger.focus();
  await user.keyboard('{Enter}'); expect(trigger).toHaveFocus(); expect(trigger).toHaveAttribute('aria-expanded', 'true');
  expect(document.getElementById(trigger.getAttribute('aria-controls')!)).toContainElement(screen.getByRole('link', { name: 'Tenants' }));
});
it('opens newly active descendants after the current destination changes', () => {
  const group = (active: boolean) => <RailSection label="Administer"><RailGroup label="Platform" href="/platform" icon={<span />} containsActive={active}><RailItem label="Tenants" href="/platform/tenants" icon={<span />} active={active} /></RailGroup></RailSection>;
  const view = render(group(false)); view.rerender(group(true));
  expect(screen.getByRole('button', { name: 'Collapse Platform menu' })).toHaveAttribute('aria-expanded', 'true');
  expect(document.querySelector('.janso-rail-group__heading li')).toBeNull();
});
it('opens an active parent hub while leaving its child destinations unmarked', async () => {
  const user = userEvent.setup();
  render(<RailSection label="Administer"><RailGroup label="Platform" href="/platform" icon={<span />} active><RailItem label="Tenants" href="/platform/tenants" icon={<span />} /></RailGroup></RailSection>);
  expect(screen.getByRole('link', { name: 'Platform' })).toHaveAttribute('aria-current', 'page');
  expect(screen.getByRole('link', { name: 'Tenants' })).not.toHaveAttribute('aria-current');
  const trigger = screen.getByRole('button', { name: 'Collapse Platform menu' }); trigger.focus();
  await user.keyboard(' ');
  expect(trigger).toHaveFocus(); expect(trigger).toHaveAttribute('aria-expanded', 'false');
});
