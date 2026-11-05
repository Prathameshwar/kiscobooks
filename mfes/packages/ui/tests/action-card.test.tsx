import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { ActionCard, SettingsIcon } from '../src';

it('offers a separate setup link while keeping the unavailable action disabled',()=>{
  render(<ActionCard title="Tax report" description="Prepare a return." icon={<SettingsIcon/>} disabledReason="Setup required" actionLabel="Unavailable" unavailableAction={{href:'/companies/example/gst-settings',label:'Set up GST'}}/>);
  expect(screen.getByRole('button',{name:'Unavailable'})).toBeDisabled();
  expect(screen.getByRole('link',{name:'Set up GST'})).toHaveAttribute('href','/companies/example/gst-settings');
  expect(screen.getByRole('article')).toContainElement(screen.getByRole('link'));
});

it('provides a single named link with an icon and card heading', () => {
  render(<ActionCard title="Edit platform details" description="Name and public URL." icon={<SettingsIcon />} href="/platform/details" actionLabel="Edit details" />);
  expect(screen.getByRole('link', { name: 'Edit platform details' })).toHaveAttribute('href', '/platform/details');
  expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent('Edit platform details');
  expect(screen.getAllByRole('link')).toHaveLength(1);
});
it('keeps unavailable actions visible and noninteractive', () => {
  render(<ActionCard title="Fees and pricing" description="Manage platform fees." icon={<SettingsIcon />} disabledReason="Coming soon" actionLabel="Manage pricing" />);
  expect(screen.queryByRole('link')).not.toBeInTheDocument();
  expect(screen.getByText('Coming soon')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Manage pricing' })).toBeDisabled();
});

it('shows a state chip on a live card without making it part of the link name', () => {
  render(<ActionCard title="Sales" description="Invoice, cash or credit sale." icon={<SettingsIcon />} href="/documents/vouchers/sales" actionLabel="Design print" status={{ label: '2 templates', tone: 'success' }} />);
  const link = screen.getByRole('link', { name: 'Sales' });
  expect(screen.getByText('2 templates')).toHaveAttribute('data-tone', 'success');
  // The name stays the title in every state; the chip is what the link is *described* by.
  expect(link).toHaveAccessibleDescription('Invoice, cash or credit sale. 2 templates');
});
it('defaults a chip to the neutral tone', () => {
  render(<ActionCard title="Journal" description="Accrual or correction." icon={<SettingsIcon />} href="/documents/vouchers/journal" actionLabel="Design print" status={{ label: 'None yet' }} />);
  expect(screen.getByText('None yet')).toHaveAttribute('data-tone', 'neutral');
});
it('describes a card without a chip by its description alone', () => {
  render(<ActionCard title="Edit platform details" description="Name and public URL." icon={<SettingsIcon />} href="/platform/details" actionLabel="Edit details" />);
  expect(screen.getByRole('link', { name: 'Edit platform details' })).toHaveAccessibleDescription('Name and public URL.');
  expect(document.querySelector('.janso-badge')).toBeNull();
});
it('lets an unavailable reason take the chip place over a status', () => {
  render(<ActionCard title="Fees" description="Platform fees." icon={<SettingsIcon />} disabledReason="Coming soon" status={{ label: '2 templates', tone: 'success' }} actionLabel="Manage pricing" />);
  expect(screen.getByText('Coming soon')).toHaveAttribute('data-tone', 'neutral');
  // One chip, and it is the reason — a status beside it would say the card is both unavailable and fine.
  expect(screen.queryByText('2 templates')).not.toBeInTheDocument();
  expect(document.querySelectorAll('.janso-badge')).toHaveLength(1);
});
