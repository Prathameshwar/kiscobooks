/**
 * The new-template form, and what a caller may ask of it.
 *
 * `onCreated` is the one seam: a caller (Voucher print) wants to do something *with* the template
 * the moment it exists. What this file guards is the part the form owns — that a follow-up which
 * cannot be done leaves the person with the template they just made rather than a form that would
 * create a second one, that a throw is the same as a refusal, and that nothing changes for the
 * callers that ask for nothing.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { serviceCall } from '../app/lib/service-call';
import { goTo } from '../app/lib/navigate';

vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/sign-in' }));

import { NewTemplateDialog } from '../app/(editor)/invoice-designer/NewTemplateDialog';

const COMPANY = '01990000-0000-7000-8000-00000000000c';
const FRESH = '01990000-0000-7000-8000-000000000007';

const writes = () => vi.mocked(serviceCall).mock.calls.filter(([, request]) => (request.method ?? 'GET') !== 'GET');

async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>) {
  const dialog = await screen.findByRole('dialog');
  await user.type(within(dialog).getByRole('textbox', { name: /Name/ }), 'Sales challan');
  await user.type(within(dialog).getByRole('textbox', { name: /Code/ }), 'sales-challan');
  await user.click(within(dialog).getByRole('button', { name: /Create and open/ }));
  return dialog;
}

function mount(props: Partial<React.ComponentProps<typeof NewTemplateDialog>> = {}) {
  const onClose = vi.fn();
  render(<NewTemplateDialog company={COMPANY} open onClose={onClose} {...props} />);
  return { onClose };
}

beforeEach(() => {
  vi.mocked(serviceCall).mockReset();
  vi.mocked(goTo).mockReset();
  vi.mocked(serviceCall).mockResolvedValue({ id: FRESH, company_id: COMPANY } as never);
});

describe('asked for nothing more', () => {
  it('is titled New template and goes straight into the designer', async () => {
    const user = userEvent.setup();
    mount();

    expect(await screen.findByRole('dialog', { name: 'New template' })).toBeInTheDocument();
    await fillAndSubmit(user);

    await waitFor(() => expect(goTo).toHaveBeenCalledWith('/invoice-designer/' + FRESH));
    expect(writes()).toHaveLength(1);
  });

  it('takes the title its caller gives it', async () => {
    mount({ title: 'Customize layout' });

    expect(await screen.findByRole('dialog', { name: 'Customize layout' })).toBeInTheDocument();
  });
});

describe('with a follow-up', () => {
  it('runs it with the new template, and opens the designer once it says all is well', async () => {
    const onCreated = vi.fn().mockResolvedValue(null);
    const user = userEvent.setup();
    mount({ onCreated });

    await fillAndSubmit(user);

    await waitFor(() => expect(goTo).toHaveBeenCalledWith('/invoice-designer/' + FRESH));
    expect(onCreated).toHaveBeenCalledTimes(1);
    expect(onCreated).toHaveBeenCalledWith(expect.objectContaining({ id: FRESH }));
  });

  it('keeps the template and says what failed, in the caller’s words, instead of opening the designer', async () => {
    const onCreated = vi.fn().mockResolvedValue('It could not be made the layout for sales.');
    const user = userEvent.setup();
    mount({ onCreated });

    const dialog = await fillAndSubmit(user);

    expect(await within(dialog).findByText('The template was created. It could not be made the layout for sales.')).toBeInTheDocument();
    expect(goTo).not.toHaveBeenCalled();
  });

  it('treats a follow-up that throws as a follow-up that failed, never as a reason to lose the template', async () => {
    const onCreated = vi.fn().mockRejectedValue(new Error('network down'));
    const user = userEvent.setup();
    mount({ onCreated });

    const dialog = await fillAndSubmit(user);

    expect(await within(dialog).findByText('The template was created. The next step could not be completed.')).toBeInTheDocument();
    expect(goTo).not.toHaveBeenCalled();
    // Nothing in the message of the thrown error reaches the page.
    expect(screen.queryByText(/network down/)).not.toBeInTheDocument();
  });

  it('offers the template it kept, and makes no second one', async () => {
    const onCreated = vi.fn().mockResolvedValue('It could not be made the layout for sales.');
    const user = userEvent.setup();
    mount({ onCreated });

    const dialog = await fillAndSubmit(user);
    await user.click(await within(dialog).findByRole('button', { name: 'Open the template' }));

    expect(goTo).toHaveBeenCalledWith('/invoice-designer/' + FRESH);
    expect(within(dialog).queryByRole('button', { name: /Create and open/ })).not.toBeInTheDocument();
    expect(writes()).toHaveLength(1);
    expect(onCreated).toHaveBeenCalledTimes(1);
  });

  it('can be put off, which closes it and opens nothing', async () => {
    const onCreated = vi.fn().mockResolvedValue('It could not be made the layout for sales.');
    const user = userEvent.setup();
    const { onClose } = mount({ onCreated });

    const dialog = await fillAndSubmit(user);
    await user.click(await within(dialog).findByRole('button', { name: 'Not now' }));

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(goTo).not.toHaveBeenCalled();
  });

  it('is not asked to follow up when the template itself was refused', async () => {
    vi.mocked(serviceCall).mockRejectedValue({ status: 409, message: "template code 'sales-challan' is already in use" });
    const onCreated = vi.fn().mockResolvedValue(null);
    const user = userEvent.setup();
    mount({ onCreated });

    const dialog = await fillAndSubmit(user);

    expect(await within(dialog).findByText("template code 'sales-challan' is already in use")).toBeInTheDocument();
    expect(onCreated).not.toHaveBeenCalled();
    expect(goTo).not.toHaveBeenCalled();
  });
});

describe('while a follow-up is running', () => {
  it('cannot be cancelled — it would vanish, and the follow-up would still land', async () => {
    const onCreated = vi.fn(() => new Promise<string | null>(() => undefined));
    const user = userEvent.setup();
    const { onClose } = mount({ onCreated });

    const dialog = await fillAndSubmit(user);
    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));

    const cancel = within(dialog).getByRole('button', { name: 'Cancel' });
    expect(cancel).toBeDisabled();
    await user.click(cancel);
    expect(onClose).not.toHaveBeenCalled();
    expect(within(dialog).getByRole('button', { name: 'Creating…' })).toBeDisabled();
  });
});

describe('after a kept template is put off', () => {
  it('is a blank form again, since the template it made already exists and its code would only collide', async () => {
    const onCreated = vi.fn().mockResolvedValue('It could not be made the layout for sales.');
    const user = userEvent.setup();
    mount({ onCreated });

    const dialog = await fillAndSubmit(user);
    await user.click(await within(dialog).findByRole('button', { name: 'Not now' }));

    // The harness keeps the dialog open (its `onClose` is a mock), which is the point: what is shown is the form.
    expect(await within(dialog).findByRole('textbox', { name: /Name/ })).toHaveValue('');
    expect(within(dialog).getByRole('textbox', { name: /Code/ })).toHaveValue('');
    expect(within(dialog).queryByText(/The template was created/)).not.toBeInTheDocument();
  });

  it('keeps what was typed when the dialog is cancelled before anything was made', async () => {
    const user = userEvent.setup();
    mount();

    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByRole('textbox', { name: /Name/ }), 'Sales challan');
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));

    expect(within(dialog).getByRole('textbox', { name: /Name/ })).toHaveValue('Sales challan');
  });
});
