import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { VoucherTypeRulesEditor } from '../app/components/VoucherTypeRulesEditor';
import { serviceCall } from '../app/lib/service-call';
import { COMPANY, RETAIL, detail, fullPolicy, service, writes } from './voucher-type-fixtures';
vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn() }));
beforeEach(() => { vi.mocked(serviceCall).mockReset(); });
it('enables missing invoice rules through a versioned save and retains the other policy', async () => {
  vi.mocked(serviceCall).mockImplementation(service({one:detail({kind:'PURCHASE',policy:fullPolicy})}));
  render(<VoucherTypeRulesEditor company={COMPANY} id={RETAIL} />);
  fireEvent.click(await screen.findByRole('checkbox',{name:'Enable purchase invoice entry'}));
  fireEvent.click(screen.getByRole('button',{name:'Save as revision 3'}));
  await waitFor(()=>expect(writes()).toHaveLength(1));
  expect(writes()[0]![1].body).toMatchObject({expected_version:3,policy:{...fullPolicy,invoice:{allowed_supply_kinds:['ACCOUNT','GOODS','SERVICE']}}});
});
it('restores Goods on a Product Purchase type without resetting invoice limits', async () => {
  vi.mocked(serviceCall).mockImplementation(service({one:detail({kind:'PURCHASE',policy:{...fullPolicy,allowed_modes:['ITEMS'],default_mode:'ITEMS',invoice:{allowed_supply_kinds:['SERVICE'],max_components:7}}})}));
  render(<VoucherTypeRulesEditor company={COMPANY} id={RETAIL} />);
  const box = await screen.findByRole('checkbox',{name:'Allow goods purchase lines'});
  expect(box).not.toBeChecked();
  fireEvent.click(box);
  fireEvent.click(screen.getByRole('button',{name:'Save as revision 3'}));
  await waitFor(()=>expect(writes()).toHaveLength(1));
  expect(writes()[0]![1].body).toMatchObject({policy:{invoice:{allowed_supply_kinds:['SERVICE','GOODS'],max_components:7}}});
});
it('allows account supplies without losing authored invoice limits', async () => {
  vi.mocked(serviceCall).mockImplementation(service({one:detail({kind:'PURCHASE',policy:{...fullPolicy,invoice:{allowed_supply_kinds:['SERVICE'],max_components:7}}})}));
  render(<VoucherTypeRulesEditor company={COMPANY} id={RETAIL} />);
  fireEvent.click(await screen.findByRole('checkbox',{name:'Allow account purchase lines'}));
  fireEvent.click(screen.getByRole('button',{name:'Save as revision 3'}));
  await waitFor(()=>expect(writes()).toHaveLength(1));
  expect(writes()[0]![1].body).toMatchObject({policy:{invoice:{allowed_supply_kinds:['SERVICE','ACCOUNT'],max_components:7}}});
});
it('allows service supplies, which a bill with GST is recorded on, without losing the account lines or authored limits', async () => {
  vi.mocked(serviceCall).mockImplementation(service({one:detail({kind:'PURCHASE',policy:{...fullPolicy,invoice:{allowed_supply_kinds:['ACCOUNT'],max_components:7}}})}));
  render(<VoucherTypeRulesEditor company={COMPANY} id={RETAIL} />);
  const box = await screen.findByRole('checkbox',{name:'Allow service purchase lines'});
  expect(box).not.toBeChecked();
  expect(box).toHaveAccessibleDescription(/Taxed account and service lines need Service enabled/);
  fireEvent.click(box);
  fireEvent.click(screen.getByRole('button',{name:'Save as revision 3'}));
  await waitFor(()=>expect(writes()).toHaveLength(1));
  expect(writes()[0]![1].body).toMatchObject({policy:{invoice:{allowed_supply_kinds:['ACCOUNT','SERVICE'],max_components:7}}});
});
it('stops allowing service supplies without touching the account lines', async () => {
  vi.mocked(serviceCall).mockImplementation(service({one:detail({kind:'PURCHASE',policy:{...fullPolicy,invoice:{allowed_supply_kinds:['ACCOUNT','SERVICE']}}})}));
  render(<VoucherTypeRulesEditor company={COMPANY} id={RETAIL} />);
  const box = await screen.findByRole('checkbox',{name:'Allow service purchase lines'});
  expect(box).toBeChecked();
  fireEvent.click(box);
  fireEvent.click(screen.getByRole('button',{name:'Save as revision 3'}));
  await waitFor(()=>expect(writes()).toHaveLength(1));
  expect(writes()[0]![1].body).toMatchObject({policy:{invoice:{allowed_supply_kinds:['ACCOUNT']}}});
});
it('treats a type that names no supply kinds as allowing all of them, and offers the service box only with invoice entry on', async () => {
  vi.mocked(serviceCall).mockImplementation(service({one:detail({kind:'PURCHASE',policy:{...fullPolicy,invoice:{}}})}));
  const { unmount } = render(<VoucherTypeRulesEditor company={COMPANY} id={RETAIL} />);
  expect(await screen.findByRole('checkbox',{name:'Allow service purchase lines'})).toBeChecked();
  unmount();
  vi.mocked(serviceCall).mockImplementation(service({one:detail({kind:'PURCHASE',policy:fullPolicy})}));
  render(<VoucherTypeRulesEditor company={COMPANY} id={RETAIL} />);
  expect(await screen.findByRole('checkbox',{name:'Allow service purchase lines'})).toBeDisabled();
  expect(screen.getByRole('checkbox',{name:'Allow service purchase lines'})).not.toBeChecked();
});
