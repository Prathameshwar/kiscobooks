/**
 * Creating, copying, changing and retiring a voucher type.
 *
 * The risks are the writes: a request that carries something the person did not choose (a policy
 * that lost its typed sub-policies, a code in the wrong case), an action offered on a type the
 * service will refuse (a retired one), a failure that vanishes instead of landing where it can be
 * read, and a retry after a lost response that is not the *same* request. Each screen is tested
 * against a double of the service that answers exactly as the real one's shapes do.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { serviceCall } from '../app/lib/service-call';
import { goTo } from '../app/lib/navigate';
import { COMPANY, NEW_TYPE, REVISION, RETAIL, detail, fullPolicy, service, writes, reads, calls } from './voucher-type-fixtures';

vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/sign-in' }));

import { VoucherTypeDetail } from '../app/components/VoucherTypeDetail';
import { VoucherTypeEditor } from '../app/components/VoucherTypeEditor';
import { VoucherTypeRulesEditor } from '../app/components/VoucherTypeRulesEditor';

beforeEach(() => {
  // Braces matter: a function returned from a hook is run as its cleanup, and `mockReset()` returns the mock.
  vi.mocked(serviceCall).mockReset();
  vi.mocked(goTo).mockReset();
});

describe('starting a voucher type', () => {
  const mount = (from?: string) => render(<VoucherTypeEditor company={COMPANY} from={from} />);
  const fill = async (user: ReturnType<typeof userEvent.setup>, code = 'retail', name = '  Retail sales ') => {
    await user.type(await screen.findByRole('textbox', { name: /^Name/ }), name);
    await user.type(screen.getByRole('textbox', { name: /^Code/ }), code);
  };

  it('asks for a name and a code, a kind and a profile — and for nothing about the rules', async () => {
    vi.mocked(serviceCall).mockImplementation(service());
    mount();

    expect(await screen.findByRole('textbox', { name: /^Name/ })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /^Code/ })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Kind' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Profile' })).toBeDisabled();
    expect(screen.queryByText('Entry modes')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'New voucher type' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Cancel' })).toHaveAttribute('href', '/masters/voucher-types');
  });

  it('offers the profiles of the chosen kind, as the service defines them, starting on Standard', async () => {
    vi.mocked(serviceCall).mockImplementation(service());
    const user = userEvent.setup();
    mount();
    await screen.findByRole('combobox', { name: 'Kind' });

    await user.selectOptions(screen.getByRole('combobox', { name: 'Kind' }), 'SALES');

    const profile = screen.getByRole('combobox', { name: 'Profile' });
    expect(profile).toHaveValue('STANDARD');
    expect(within(profile).getAllByRole('option').map((option) => option.textContent)).toEqual(['Choose a profile', 'Standard', 'Pro forma']);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Kind' }), 'RECEIPT');
    expect(within(profile).getByRole('option', { name: 'Advance' })).toBeInTheDocument();
    expect(within(profile).queryByRole('option', { name: 'Pro forma' })).not.toBeInTheDocument();
  });

  it('says what the chosen kind is', async () => {
    vi.mocked(serviceCall).mockImplementation(service());
    const user = userEvent.setup();
    mount();
    await user.selectOptions(await screen.findByRole('combobox', { name: 'Kind' }), 'SALES');

    expect(screen.getByText('Invoice, cash or credit sale.')).toBeInTheDocument();
  });

  it('tells each empty field what is missing, and sends nothing', async () => {
    vi.mocked(serviceCall).mockImplementation(service());
    const user = userEvent.setup();
    mount();

    await user.click(await screen.findByRole('button', { name: 'Create voucher type' }));

    expect(await screen.findByText('Enter a name.')).toBeInTheDocument();
    expect(screen.getByText('Enter a code.')).toBeInTheDocument();
    expect(screen.getByText('Choose the kind of voucher this type is for.')).toBeInTheDocument();
    expect(writes()).toHaveLength(0);
  });

  it('corrects a field as it is edited, once a save has been tried', async () => {
    vi.mocked(serviceCall).mockImplementation(service());
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByRole('button', { name: 'Create voucher type' }));
    await screen.findByText('Enter a name.');

    await user.type(screen.getByRole('textbox', { name: /^Name/ }), 'Retail');

    expect(screen.queryByText('Enter a name.')).not.toBeInTheDocument();
    expect(screen.getByText('Enter a code.')).toBeInTheDocument();
  });

  it('does not scold before the first attempt', async () => {
    vi.mocked(serviceCall).mockImplementation(service());
    const user = userEvent.setup();
    mount();

    await user.type(await screen.findByRole('textbox', { name: /^Code/ }), '9');

    expect(screen.queryByText(/Start with a letter/)).not.toBeInTheDocument();
  });

  it('creates the type with the code in capitals and the name trimmed, then goes to its page', async () => {
    vi.mocked(serviceCall).mockImplementation(service());
    const user = userEvent.setup();
    mount();
    await fill(user);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Kind' }), 'SALES');

    await user.click(screen.getByRole('button', { name: 'Create voucher type' }));

    await waitFor(() => expect(writes()).toHaveLength(1));
    const [[, request]] = writes();
    expect(request.service).toBe('vouchers');
    expect(request.method).toBe('POST');
    expect(request.path).toBe(`/v1/companies/${COMPANY}/voucher-types`);
    expect(request.body).toEqual({ code: 'RETAIL', name: 'Retail sales', kind: 'SALES', profile: 'STANDARD' });
    // A new type starts on the service's defaults: no policy is sent.
    expect(request.body).not.toHaveProperty('policy');
    expect(request.key).toBeTruthy();
    await waitFor(() => expect(goTo).toHaveBeenCalledWith(`/masters/voucher-types/${NEW_TYPE}?saved=created`));
  });

  it('says a conflict is probably the code — the service reports a taken code only as a unique-value conflict', async () => {
    // `IntegrityError` is answered `409 voucher reference or unique value conflicts`, with no field named.
    vi.mocked(serviceCall).mockImplementation(
      service({ writeFailure: { status: 409, message: 'voucher reference or unique value conflicts' } }),
    );
    const user = userEvent.setup();
    mount();
    await fill(user);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Kind' }), 'SALES');
    await user.click(screen.getByRole('button', { name: 'Create voucher type' }));

    expect(await screen.findByText('voucher reference or unique value conflicts')).toBeInTheDocument();
    expect(screen.getByText('This code may already be in use — codes are unique within a company.')).toBeInTheDocument();
    expect(goTo).not.toHaveBeenCalled();
  });

  it('shows any other refusal in words, and keeps what was typed', async () => {
    vi.mocked(serviceCall).mockImplementation(service({ writeFailure: { status: 422, message: 'request validation failed' } }));
    const user = userEvent.setup();
    mount();
    await fill(user);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Kind' }), 'SALES');
    await user.click(screen.getByRole('button', { name: 'Create voucher type' }));

    expect(await screen.findByText('request validation failed')).toBeInTheDocument();
    // Not a conflict, so the code is not blamed.
    expect(screen.queryByText(/may already be in use/)).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /^Name/ })).toHaveValue('  Retail sales ');
    expect(screen.getByRole('button', { name: 'Create voucher type' })).toBeEnabled();
  });

  it('keeps the request when the answer is lost, and retries exactly that request', async () => {
    let attempts = 0;
    vi.mocked(serviceCall).mockImplementation(async (endpoint, request) => {
      if ((request.method ?? 'GET') === 'POST' && attempts++ === 0) throw { status: 503, message: 'The voucher service did not answer.' };
      return (await service()(endpoint, request)) as never;
    });
    const user = userEvent.setup();
    mount();
    await fill(user);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Kind' }), 'SALES');
    await user.click(screen.getByRole('button', { name: 'Create voucher type' }));

    expect(await screen.findByText(/The result of the last attempt is not known/)).toBeInTheDocument();
    // The fields are held, so the retry cannot become a different request under the same key.
    expect(screen.getByRole('textbox', { name: /^Code/ })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Try again' }));

    await waitFor(() => expect(writes()).toHaveLength(2));
    const [[, first], [, second]] = writes();
    expect(second.key).toBe(first.key);
    expect(second.body).toEqual(first.body);
    await waitFor(() => expect(goTo).toHaveBeenCalled());
  });

  it('does not trust a creation that comes back for another company — it holds the request for a retry instead', async () => {
    vi.mocked(serviceCall).mockImplementation(service({ written: detail({ id: NEW_TYPE, company_id: '01990000-0000-7000-8000-00000000000d' }) }));
    const user = userEvent.setup();
    mount();
    await fill(user);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Kind' }), 'SALES');
    await user.click(screen.getByRole('button', { name: 'Create voucher type' }));

    // A reply that cannot be verified is an unknown outcome, so the same request may be replayed.
    expect(await screen.findByText(/The result of the last attempt is not known/)).toBeInTheDocument();
    expect(goTo).not.toHaveBeenCalled();
  });

  it('shows why the form cannot open when the kinds cannot be read', async () => {
    vi.mocked(serviceCall).mockRejectedValue({ status: 403, message: 'You may not read voucher kinds here.' });
    mount();

    expect(await screen.findByText('You may not read voucher kinds here.')).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: /^Name/ })).not.toBeInTheDocument();
  });

  describe('as a copy', () => {
    it('fixes the kind and profile to the original’s, and sends the revision and the rules it was copied from', async () => {
      // Left out, the service intersects the original with the *default* policy: approval, starting mode and narration reset.
      const policy = { ...fullPolicy, approval_required: false, self_approval_allowed: true, default_mode: 'MIXED', default_narration: 'Goods as per order' };
      vi.mocked(serviceCall).mockImplementation(service({ one: detail({ policy }) }));
      const user = userEvent.setup();
      mount(RETAIL);

      expect(await screen.findByText(/Copying/)).toBeInTheDocument();
      expect(screen.getByRole('heading', { level: 1, name: 'Duplicate voucher type' })).toBeInTheDocument();
      expect(screen.getByRole('combobox', { name: 'Kind' })).toBeDisabled();
      expect(screen.getByRole('combobox', { name: 'Kind' })).toHaveValue('SALES');
      expect(screen.getByRole('combobox', { name: 'Profile' })).toBeDisabled();
      await user.type(screen.getByRole('textbox', { name: /^Name/ }), 'Retail copy');
      await user.type(screen.getByRole('textbox', { name: /^Code/ }), 'retail-2');
      await user.click(screen.getByRole('button', { name: 'Create copy' }));

      await waitFor(() => expect(writes()).toHaveLength(1));
      expect(writes()[0]![1].body).toEqual({
        code: 'RETAIL-2',
        name: 'Retail copy',
        kind: 'SALES',
        profile: 'STANDARD',
        derived_from_revision_id: REVISION,
        policy,
      });
      await waitFor(() => expect(goTo).toHaveBeenCalledWith(`/masters/voucher-types/${NEW_TYPE}?saved=copied`));
    });

    it('does not offer to copy a retired type', async () => {
      vi.mocked(serviceCall).mockImplementation(service({ one: detail({ status: 'RETIRED' }) }));
      mount(RETAIL);

      expect(await screen.findByText(/is retired, so it cannot be copied/)).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Create copy' })).not.toBeInTheDocument();
    });

    it('will not copy what it cannot identify the revision of', async () => {
      vi.mocked(serviceCall).mockImplementation(service({ one: detail({ revision_id: null }) }));
      const user = userEvent.setup();
      mount(RETAIL);
      await user.type(await screen.findByRole('textbox', { name: /^Name/ }), 'Copy');
      await user.type(screen.getByRole('textbox', { name: /^Code/ }), 'copy');

      expect(screen.getByText(/revision and rules could not be read/)).toBeInTheDocument();
      await user.click(screen.getByRole('button', { name: 'Create copy' }));
      expect(writes()).toHaveLength(0);
    });

    it('will not copy what it cannot read the rules of — a copy without them would come back on the defaults', async () => {
      vi.mocked(serviceCall).mockImplementation(service({ one: detail({ policy: null }) }));
      const user = userEvent.setup();
      mount(RETAIL);
      await user.type(await screen.findByRole('textbox', { name: /^Name/ }), 'Copy');
      await user.type(screen.getByRole('textbox', { name: /^Code/ }), 'copy');
      await user.click(screen.getByRole('button', { name: 'Create copy' }));

      expect(screen.getByText(/revision and rules could not be read/)).toBeInTheDocument();
      expect(writes()).toHaveLength(0);
    });

    it('says so when the original cannot be read', async () => {
      vi.mocked(serviceCall).mockImplementation(async (endpoint, request) => {
        if (request.path.includes(`/voucher-types/${RETAIL}`)) throw { status: 404, message: 'Voucher type not found.' };
        return (await service()(endpoint, request)) as never;
      });
      mount(RETAIL);

      expect(await screen.findByText('Voucher type not found.')).toBeInTheDocument();
      expect(screen.queryByRole('textbox', { name: /^Name/ })).not.toBeInTheDocument();
    });
  });
});

describe('one voucher type', () => {
  const mount = (props: { canManage?: boolean; saved?: string } = {}) =>
    render(<VoucherTypeDetail company={COMPANY} id={RETAIL} canManage={props.canManage ?? true} saved={props.saved} />);

  it('shows what the type is and the rules in force', async () => {
    vi.mocked(serviceCall).mockImplementation(service());
    mount();

    expect(await screen.findByRole('heading', { level: 1, name: 'Retail sales' })).toBeInTheDocument();
    expect(screen.getByText('Sales — invoice, cash or credit sale.')).toBeInTheDocument();
    expect(screen.getByText('RETAIL')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
    expect(screen.getByText('Entry modes')).toBeInTheDocument();
    expect(screen.getAllByText('All').length).toBeGreaterThan(0);
    expect(screen.getByText('Required')).toBeInTheDocument();
    expect(screen.getByText('3650')).toBeInTheDocument();
  });

  it('offers a manager the three things that can be done to an active type', async () => {
    vi.mocked(serviceCall).mockImplementation(service());
    mount();

    expect(await screen.findByRole('link', { name: 'Edit rules' })).toHaveAttribute('href', `/masters/voucher-types/${RETAIL}/edit`);
    expect(screen.getByRole('link', { name: 'Duplicate' })).toHaveAttribute('href', `/masters/voucher-types/new?from=${RETAIL}`);
    expect(screen.getByRole('button', { name: 'Retire' })).toBeInTheDocument();
  });

  it('offers a reader the record and nothing to change', async () => {
    vi.mocked(serviceCall).mockImplementation(service());
    mount({ canManage: false });

    await screen.findByRole('heading', { level: 1, name: 'Retail sales' });
    expect(screen.queryByRole('link', { name: 'Edit rules' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Retire' })).not.toBeInTheDocument();
    expect(screen.getByText(/Read-only access/)).toBeInTheDocument();
  });

  it('offers nothing to change on a retired type, and says what retired means', async () => {
    vi.mocked(serviceCall).mockImplementation(service({ one: detail({ status: 'RETIRED' }) }));
    mount();

    expect(await screen.findByText(/This voucher type is retired/)).toBeInTheDocument();
    expect(screen.getByText('Retired')).toBeInTheDocument();
    for (const name of ['Edit rules', 'Duplicate']) expect(screen.queryByRole('link', { name })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Retire' })).not.toBeInTheDocument();
  });

  it.each([
    ['created', /Voucher type created\. Its entry rules start on the defaults/, false],
    ['copied', /created as a copy\. It has the original’s entry rules/, false],
    ['revised', /saved as a new revision/, false],
    ['retired', /Voucher type retired/, true],
  ])('confirms what was just done (%s)', async (saved, words, retired) => {
    vi.mocked(serviceCall).mockImplementation(service({ one: detail({ status: retired ? 'RETIRED' : 'ACTIVE' }) }));
    mount({ saved });

    expect(await screen.findByText(words)).toBeInTheDocument();
  });

  it.each(['<b>hacked</b>', '__proto__', 'constructor', 'toString', 'hasOwnProperty'])('ignores a ?saved= it does not know (%s), rather than printing or choking on it', async (saved) => {
    vi.mocked(serviceCall).mockImplementation(service());
    mount({ saved });

    await screen.findByRole('heading', { level: 1, name: 'Retail sales' });
    expect(screen.queryByText(/hacked/)).not.toBeInTheDocument();
    expect(document.querySelector('.janso-notice[data-tone="success"]')).toBeNull();
  });

  it('does not claim a live type was retired because the address says so', async () => {
    vi.mocked(serviceCall).mockImplementation(service());
    mount({ saved: 'retired' });

    await screen.findByRole('heading', { level: 1, name: 'Retail sales' });
    expect(screen.queryByText(/Voucher type retired/)).not.toBeInTheDocument();
  });

  it('names the typed controls it keeps but does not edit', async () => {
    vi.mocked(serviceCall).mockImplementation(service({ one: detail({ policy: { ...fullPolicy, schema_version: 2, stock: { reserve: true }, invoice: {} } }) }));
    mount();

    expect(await screen.findByText(/also carries stock, invoice controls/)).toBeInTheDocument();
  });

  it('describes approval in words, including self-approval', async () => {
    vi.mocked(serviceCall).mockImplementation(service({ one: detail({ policy: { ...fullPolicy, self_approval_allowed: true } }) }));
    mount();

    expect(await screen.findByText('Required; the person who raised it may approve it')).toBeInTheDocument();
  });

  it.each([
    [403, 'You may not read this voucher type.'],
    [404, 'Voucher type not found.'],
  ])('shows a %s as itself, not as a blank page', async (status, message) => {
    vi.mocked(serviceCall).mockRejectedValue({ status, message });
    mount();

    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Edit rules' })).not.toBeInTheDocument();
  });

  it('refuses a type that comes back for another company', async () => {
    vi.mocked(serviceCall).mockImplementation(service({ one: detail({ company_id: '01990000-0000-7000-8000-00000000000d' }) }));
    mount();

    expect(await screen.findByText(/did not match this company/)).toBeInTheDocument();
  });

  describe('retiring', () => {
    it('asks first, says it cannot be undone, and holds the button until the word is typed', async () => {
      vi.mocked(serviceCall).mockImplementation(service());
      const user = userEvent.setup();
      mount();

      await user.click(await screen.findByRole('button', { name: 'Retire' }));

      const dialog = await screen.findByRole('dialog', { name: 'Retire Retail sales?' });
      expect(within(dialog).getByText(/cannot be reinstated/)).toBeInTheDocument();
      const confirm = within(dialog).getByRole('button', { name: 'Retire voucher type' });
      expect(confirm).toBeDisabled();
      await user.type(within(dialog).getByRole('textbox', { name: /Type/i }), 'retire');
      expect(confirm).toBeEnabled();
      expect(writes()).toHaveLength(0);
    });

    it('retires at the version it was read at, and shows the result', async () => {
      vi.mocked(serviceCall).mockImplementation(service({ written: detail({ status: 'RETIRED', row_version: 4 }) }));
      const user = userEvent.setup();
      mount();
      await user.click(await screen.findByRole('button', { name: 'Retire' }));
      const dialog = await screen.findByRole('dialog');
      // The service accepts a reason and keeps it nowhere, so the dialog does not ask for one.
      expect(within(dialog).queryByRole('textbox', { name: /Reason/ })).not.toBeInTheDocument();
      await user.type(within(dialog).getByRole('textbox', { name: /Type/i }), 'retire');

      await user.click(within(dialog).getByRole('button', { name: 'Retire voucher type' }));

      await waitFor(() => expect(writes()).toHaveLength(1));
      const [[, request]] = writes();
      expect(request.path).toBe(`/v1/companies/${COMPANY}/voucher-types/${RETAIL}/retire`);
      expect(request.method).toBe('POST');
      expect(request.body).toEqual({ expected_version: 3 });
      await waitFor(() => expect(goTo).toHaveBeenCalledWith(`/masters/voucher-types/${RETAIL}?saved=retired`));
    });

    it('keeps the dialog open and says why when the service refuses', async () => {
      vi.mocked(serviceCall).mockImplementation(
        service({ writeFailure: { status: 409, message: 'This voucher type was changed by someone else. Reload and try again.' } }),
      );
      const user = userEvent.setup();
      mount();
      await user.click(await screen.findByRole('button', { name: 'Retire' }));
      const dialog = await screen.findByRole('dialog');
      await user.type(within(dialog).getByRole('textbox', { name: /Type/i }), 'retire');
      await user.click(within(dialog).getByRole('button', { name: 'Retire voucher type' }));

      expect(await within(dialog).findByText(/This voucher type was changed by someone else\. Reload and try again\. Close this window to reload the type/)).toBeInTheDocument();
      expect(goTo).not.toHaveBeenCalled();
    });

    it('reloads the type when a conflict is dismissed, so the next try is not stale too', async () => {
      let version = 3;
      vi.mocked(serviceCall).mockImplementation(async (endpoint, request) => {
        if ((request.method ?? 'GET') === 'POST') throw { status: 409, message: 'stale version' };
        return (await service({ one: detail({ row_version: version }) })(endpoint, request)) as never;
      });
      const user = userEvent.setup();
      mount();
      await user.click(await screen.findByRole('button', { name: 'Retire' }));
      let dialog = await screen.findByRole('dialog');
      await user.type(within(dialog).getByRole('textbox', { name: /Type/i }), 'retire');
      await user.click(within(dialog).getByRole('button', { name: 'Retire voucher type' }));
      await within(dialog).findByText(/stale version/);
      const before = reads(`/voucher-types/${RETAIL}`).length;

      version = 5;
      await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));

      await waitFor(() => expect(reads(`/voucher-types/${RETAIL}`).length).toBe(before + 1));
      await user.click(await screen.findByRole('button', { name: 'Retire' }));
      dialog = await screen.findByRole('dialog');
      await user.type(within(dialog).getByRole('textbox', { name: /Type/i }), 'retire');
      await user.click(within(dialog).getByRole('button', { name: 'Retire voucher type' }));
      await waitFor(() => expect(writes()).toHaveLength(2));
      expect(writes()[1]![1].body).toEqual({ expected_version: 5 });
    });

    it('keeps the request when the answer is lost, and retries exactly that request', async () => {
      let attempts = 0;
      vi.mocked(serviceCall).mockImplementation(async (endpoint, request) => {
        if ((request.method ?? 'GET') === 'POST' && attempts++ === 0) throw { status: 502, message: 'The voucher service did not answer.' };
        return (await service({ written: detail({ status: 'RETIRED', row_version: 4 }) })(endpoint, request)) as never;
      });
      const user = userEvent.setup();
      mount();
      await user.click(await screen.findByRole('button', { name: 'Retire' }));
      const dialog = await screen.findByRole('dialog');
      await user.type(within(dialog).getByRole('textbox', { name: /Type/i }), 'retire');
      await user.click(within(dialog).getByRole('button', { name: 'Retire voucher type' }));
      expect(await within(dialog).findByText(/it will not retire anything twice/)).toBeInTheDocument();

      await user.click(within(dialog).getByRole('button', { name: 'Retire voucher type' }));

      await waitFor(() => expect(writes()).toHaveLength(2));
      expect(writes()[1]![1].key).toBe(writes()[0]![1].key);
      expect(writes()[1]![1].body).toEqual(writes()[0]![1].body);
      await waitFor(() => expect(goTo).toHaveBeenCalledWith(`/masters/voucher-types/${RETAIL}?saved=retired`));
    });

    it('closes without writing anything on Cancel', async () => {
      vi.mocked(serviceCall).mockImplementation(service());
      const user = userEvent.setup();
      mount();
      await user.click(await screen.findByRole('button', { name: 'Retire' }));

      await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancel' }));

      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
      expect(writes()).toHaveLength(0);
    });
  });
});

describe('changing the entry rules', () => {
  const mount = () => render(<VoucherTypeRulesEditor company={COMPANY} id={RETAIL} />);
  // "Accounts" and "Items" are both an entry mode and a section, so a box is found through its group.
  const group = (title: string) => within(screen.getByRole('group', { name: title }));
  const stocked = () => detail({ policy: { ...fullPolicy, schema_version: 2, stock: { reserve: true } } });

  it('starts from the rules in force, with nothing to save', async () => {
    vi.mocked(serviceCall).mockImplementation(service());
    mount();

    expect(await screen.findByRole('heading', { level: 1, name: 'Edit rules — Retail sales' })).toBeInTheDocument();
    expect(group('Entry modes').getByRole('checkbox', { name: 'Accounts' })).toBeChecked();
    expect(screen.getByRole('textbox', { name: /Most lines/ })).toHaveValue('200');
    expect(screen.getByRole('checkbox', { name: 'Approval required' })).toBeChecked();
    expect(screen.getByRole('button', { name: 'Save as revision 3' })).toBeDisabled();
    expect(screen.getByRole('link', { name: 'Cancel' })).toHaveAttribute('href', `/masters/voucher-types/${RETAIL}`);
  });

  it('saves a change as a new revision, keeping every control it does not show', async () => {
    vi.mocked(serviceCall).mockImplementation(service({ one: stocked() }));
    const user = userEvent.setup();
    mount();
    const lines = await screen.findByRole('textbox', { name: /Most lines/ });
    await user.clear(lines);
    await user.type(lines, '50');
    await user.click(screen.getByRole('checkbox', { name: 'Narration' }));

    await user.click(screen.getByRole('button', { name: 'Save as revision 3' }));

    await waitFor(() => expect(writes()).toHaveLength(1));
    const [[, request]] = writes();
    expect(request.path).toBe(`/v1/companies/${COMPANY}/voucher-types/${RETAIL}/revisions`);
    expect(request.method).toBe('POST');
    expect(request.key).toBeTruthy();
    const body = request.body as { expected_version: number; policy: Record<string, unknown> };
    expect(body.expected_version).toBe(3);
    // No reason: the service would take one and keep it nowhere.
    expect(Object.keys(body).sort()).toEqual(['expected_version', 'policy']);
    expect(screen.queryByRole('textbox', { name: /Reason/ })).not.toBeInTheDocument();
    expect(body.policy).toMatchObject({ max_lines: 50, narration_required: true, stock: { reserve: true }, schema_version: 2 });
    await waitFor(() => expect(goTo).toHaveBeenCalledWith(`/masters/voucher-types/${RETAIL}?saved=revised`));
  });

  it('says which typed controls it is carrying through', async () => {
    vi.mocked(serviceCall).mockImplementation(service({ one: stocked() }));
    mount();

    expect(await screen.findByText(/also carries stock controls/)).toBeInTheDocument();
  });

  it('tells each wrong field what is wrong, and does not save', async () => {
    vi.mocked(serviceCall).mockImplementation(service());
    const user = userEvent.setup();
    mount();
    const lines = await screen.findByRole('textbox', { name: /Most lines/ });
    await user.clear(lines);
    await user.type(lines, '201');
    await user.click(group('Entry modes').getByRole('checkbox', { name: 'Items' }));
    await user.click(group('Entry modes').getByRole('checkbox', { name: 'Accounts' }));
    await user.click(group('Entry modes').getByRole('checkbox', { name: 'Mixed' }));

    await user.click(screen.getByRole('button', { name: 'Save as revision 3' }));

    expect(await screen.findByText('Enter a whole number from 0 to 200.')).toBeInTheDocument();
    expect(screen.getByText('Choose at least one entry mode.')).toBeInTheDocument();
    expect(screen.getByText('Fix the highlighted fields, then save again.')).toBeInTheDocument();
    expect(writes()).toHaveLength(0);
  });

  it('refuses a section that is both required and forbidden', async () => {
    vi.mocked(serviceCall).mockImplementation(service());
    const user = userEvent.setup();
    mount();
    const required = await screen.findByRole('group', { name: 'Required' });
    const forbidden = screen.getByRole('group', { name: 'Forbidden' });
    await user.click(within(required).getByRole('checkbox', { name: 'Tax' }));
    await user.click(within(forbidden).getByRole('checkbox', { name: 'Tax' }));

    await user.click(screen.getByRole('button', { name: 'Save as revision 3' }));

    expect(await screen.findByText('Tax cannot be both required and forbidden.')).toBeInTheDocument();
    expect(writes()).toHaveLength(0);
  });

  it('only offers a starting mode that is allowed', async () => {
    vi.mocked(serviceCall).mockImplementation(service());
    const user = userEvent.setup();
    mount();
    await screen.findByRole('textbox', { name: /Most lines/ });
    await user.click(group('Entry modes').getByRole('checkbox', { name: 'Accounts' }));

    const start = screen.getByRole('combobox', { name: 'Starts in' });
    expect(within(start).queryByRole('option', { name: 'Accounts' })).not.toBeInTheDocument();
    expect(within(start).getByRole('option', { name: 'Items' })).toBeInTheDocument();
  });

  it('shows a conflict in words and offers to reload, discarding the stale draft', async () => {
    let version = 3;
    vi.mocked(serviceCall).mockImplementation(async (endpoint, request) => {
      if ((request.method ?? 'GET') === 'POST') throw { status: 409, message: 'This voucher type was changed by someone else.' };
      return (await service({ one: detail({ row_version: version, current_revision: version }) })(endpoint, request)) as never;
    });
    const user = userEvent.setup();
    mount();
    const lines = await screen.findByRole('textbox', { name: /Most lines/ });
    await user.clear(lines);
    await user.type(lines, '5');
    await user.click(screen.getByRole('button', { name: 'Save as revision 4' }));
    expect(await screen.findByText('This voucher type was changed by someone else.')).toBeInTheDocument();

    version = 5;
    await user.click(screen.getByRole('button', { name: 'Reload this type' }));

    await waitFor(() => expect(screen.getByRole('button', { name: 'Save as revision 6' })).toBeInTheDocument());
    expect(screen.getByRole('textbox', { name: /Most lines/ })).toHaveValue('200');
    expect(screen.queryByText('This voucher type was changed by someone else.')).not.toBeInTheDocument();
  });

  it('does not offer to throw the edits away for a refusal that is about a value, not a conflict', async () => {
    vi.mocked(serviceCall).mockImplementation(service({ writeFailure: { status: 422, message: 'required section is unavailable for this kind/profile' } }));
    const user = userEvent.setup();
    mount();
    const lines = await screen.findByRole('textbox', { name: /Most lines/ });
    await user.clear(lines);
    await user.type(lines, '9');
    await user.click(screen.getByRole('button', { name: 'Save as revision 3' }));

    expect(await screen.findByText('required section is unavailable for this kind/profile')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Reload this type' })).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /Most lines/ })).toHaveValue('9');
  });

  it('offers a Receipt only the sections a Receipt has, and starts it only in Accounts', async () => {
    vi.mocked(serviceCall).mockImplementation(service({ one: detail({ kind: 'RECEIPT', policy: { ...fullPolicy, default_mode: 'ACCOUNTS' } }) }));
    mount();
    const required = within(await screen.findByRole('group', { name: 'Required' }));

    expect(required.getByRole('checkbox', { name: 'Parties' })).toBeInTheDocument();
    for (const name of ['Items', 'Charges', 'Tax']) expect(required.queryByRole('checkbox', { name }), name).not.toBeInTheDocument();
    const start = screen.getByRole('combobox', { name: 'Starts in' });
    expect(within(start).getAllByRole('option').map((option) => option.textContent)).toEqual(['Accounts']);
  });

  it('offers a Sales voucher every section and every starting mode', async () => {
    vi.mocked(serviceCall).mockImplementation(service());
    mount();
    const required = within(await screen.findByRole('group', { name: 'Required' }));

    for (const name of ['Items', 'Charges', 'Tax']) expect(required.getByRole('checkbox', { name }), name).toBeInTheDocument();
    expect(within(screen.getByRole('combobox', { name: 'Starts in' })).getAllByRole('option')).toHaveLength(3);
  });

  it('refuses, before sending, what the service always refuses', async () => {
    vi.mocked(serviceCall).mockImplementation(service());
    const user = userEvent.setup();
    mount();
    const lines = await screen.findByRole('textbox', { name: /Most lines/ });
    const required = within(screen.getByRole('group', { name: 'Required' }));
    await user.click(required.getByRole('checkbox', { name: 'Items' }));
    await user.clear(lines);
    await user.type(lines, '0');

    await user.click(screen.getByRole('button', { name: 'Save as revision 3' }));

    expect(await screen.findByText('Items are required, so the line limit cannot be zero.')).toBeInTheDocument();
    expect(writes()).toHaveLength(0);
  });

  it('keeps the request when the answer is lost, and retries exactly that request', async () => {
    let attempts = 0;
    vi.mocked(serviceCall).mockImplementation(async (endpoint, request) => {
      if ((request.method ?? 'GET') === 'POST' && attempts++ === 0) throw { status: 502, message: 'The voucher service did not answer.' };
      return (await service()(endpoint, request)) as never;
    });
    const user = userEvent.setup();
    mount();
    const lines = await screen.findByRole('textbox', { name: /Most lines/ });
    await user.clear(lines);
    await user.type(lines, '7');
    await user.click(screen.getByRole('button', { name: 'Save as revision 3' }));

    expect(await screen.findByText(/it will not create a second revision/)).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /Most lines/ })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Try again' }));

    await waitFor(() => expect(writes()).toHaveLength(2));
    expect(writes()[1]![1].key).toBe(writes()[0]![1].key);
    expect(writes()[1]![1].body).toEqual(writes()[0]![1].body);
  });

  it('will not edit a retired type', async () => {
    vi.mocked(serviceCall).mockImplementation(service({ one: detail({ status: 'RETIRED' }) }));
    mount();

    expect(await screen.findByText(/retired, so its rules can no longer be changed/)).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: /Most lines/ })).not.toBeInTheDocument();
  });

  it('refuses a type that comes back for another company', async () => {
    vi.mocked(serviceCall).mockImplementation(service({ one: detail({ company_id: '01990000-0000-7000-8000-00000000000d' }) }));
    mount();

    expect(await screen.findByText(/did not match this company/)).toBeInTheDocument();
    expect(reads('/voucher-types')).toHaveLength(0);
    expect(calls().length).toBeGreaterThan(0);
  });
});
