import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { CompanyGstRegistration } from '../app/components/CompanyGstRegistration';
import { CompanyGstOutwardProfile } from '../app/components/CompanyGstOutwardProfile';
import { companyCall } from '../app/lib/company-api';

vi.mock('../app/lib/company-api', () => ({ companyCall: vi.fn(), companyFailure: (value: unknown) => value }));
const company = '01990000-0000-7000-8000-000000000001';
const registration = { id: company, number: '27ABCDE1234F1Z5', regime: 'regular' };
const forms = [
  { kind: 'registration', title: 'Add GST registration', field: 'GSTIN', value: registration.number, discard: 'Discard unsaved GST registration?', save: 'Save GST registration' },
  { kind: 'profile', title: 'Add outward reporting profile', field: 'Reporting profile evidence reference', value: 'Registration certificate', discard: 'Discard unsaved outward reporting profile?', save: 'Save outward reporting profile' },
] as const;
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(companyCall).mockImplementation(async (_service, path) => {
    if (path.endsWith('/gst-registration-setup')) return { country_code: 'IN', default_tax_system: 'gst_in', can_manage: true, states: [{ code: 'MH', name: 'Maharashtra' }], regimes: { regular: 'Regular taxpayer' }, create_schema: { properties: {} } } as never;
    if (path.endsWith('/gst-outward-profile-setup')) return { can_manage: true, create_schema: { properties: {} } } as never;
    return { items: [], page: { next_cursor: null } } as never;
  });
});
async function mount(form: typeof forms[number]) {
  const view = render(form.kind === 'registration' ? <CompanyGstRegistration company={company} /> : <CompanyGstOutwardProfile company={company} registrations={[registration]} />);
  const trigger = await screen.findByRole('button', { name: form.title });
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  trigger.focus(); fireEvent.click(trigger);
  return { ...view, trigger, drawer: screen.getByRole('dialog', { name: form.title }) };
}
it.each(forms)('opens $kind in a portalled drawer with a connected, pinned save action', async form => {
  const { container, drawer } = await mount(form);
  expect(container.contains(drawer)).toBe(false);
  expect(drawer).toHaveClass('janso-drawer__panel');
  expect(drawer).toHaveAttribute('aria-modal', 'true');
  expect(within(drawer).getByRole('form', { name: form.title }).closest('.janso-card')).toBeNull();
  const save = within(drawer).getByRole('button', { name: form.save });
  expect(save.closest('.janso-overlay-foot')).not.toBeNull();
  expect(save).toHaveAttribute('form', within(drawer).getByRole('form', { name: form.title }).id);
  expect(save).toBeDisabled();
});
it.each(forms)('confirms dismissal of a dirty $kind and restores the draft or discards it', async form => {
  const originalOverflow = document.body.style.overflow;
  const { trigger, drawer } = await mount(form);
  fireEvent.change(within(drawer).getByLabelText(form.field), { target: { value: form.value } });
  for (const dismiss of [
    () => fireEvent.click(within(drawer).getByRole('button', { name: 'Close' })),
    () => fireEvent.click(within(drawer).getByRole('button', { name: 'Cancel' })),
    () => fireEvent.keyDown(drawer, { key: 'Escape' }),
    () => fireEvent.mouseDown(document.querySelector('.janso-drawer__scrim')!),
  ]) {
    dismiss();
    const confirmation = screen.getByRole('dialog', { name: form.discard });
    fireEvent.click(within(confirmation).getByRole('button', { name: 'Keep editing' }));
    expect(within(drawer).getByLabelText(form.field)).toHaveValue(form.value);
    expect(document.body.style.overflow).toBe('hidden');
  }
  fireEvent.click(within(drawer).getByRole('button', { name: 'Cancel' }));
  fireEvent.click(within(screen.getByRole('dialog', { name: form.discard })).getByRole('button', { name: 'Discard' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  expect(document.body.style.overflow).toBe(originalOverflow);
  expect(trigger).toHaveFocus();
  fireEvent.click(trigger);
  expect(screen.getByLabelText(form.field)).toHaveValue('');
});
it.each(forms)('dismisses an untouched $kind without confirmation and traps keyboard focus', async form => {
  const user = userEvent.setup();
  const { drawer, trigger } = await mount(form);
  const cancel = within(drawer).getByRole('button', { name: 'Cancel' });
  cancel.focus(); await user.tab();
  expect(within(drawer).getByRole('button', { name: 'Close' })).toHaveFocus();
  await user.tab({ shift: true }); expect(cancel).toHaveFocus();
  await user.keyboard('{Escape}');
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
});
it.each(forms)('blocks every dismissal of a pending $kind, then shows failure in its drawer', async form => {
  const answer = vi.mocked(companyCall).getMockImplementation()!;
  let reject!: (value: unknown) => void;
  vi.mocked(companyCall).mockImplementation((service, path, request) => request?.method === 'POST' ? new Promise((_resolve, fail) => { reject = fail; }) : answer(service, path, request));
  const { drawer } = await mount(form);
  // Submitting the form directly exercises the request guard independently of browser required-field checks.
  if (form.kind === 'profile') fireEvent.change(within(drawer).getByLabelText('Previous GST financial-year aggregate turnover (INR)'), { target: { value: '40000000.0000' } });
  fireEvent.submit(within(drawer).getByRole('form', { name: form.title }));
  expect(within(drawer).getByRole('button', { name: 'Close' })).toBeDisabled();
  expect(within(drawer).getByRole('button', { name: 'Cancel' })).toBeDisabled();
  expect(within(drawer).getByLabelText(form.field)).toBeDisabled();
  fireEvent.keyDown(drawer, { key: 'Escape' });
  fireEvent.mouseDown(document.querySelector('.janso-drawer__scrim')!);
  expect(screen.getAllByRole('dialog')).toHaveLength(1);
  await act(async () => reject({ status: 503, message: 'The save could not be completed.' }));
  expect(within(drawer).getByText('The save could not be completed.')).toBeVisible();
  expect(within(drawer).getByRole('button', { name: 'Close' })).toBeEnabled();
});
