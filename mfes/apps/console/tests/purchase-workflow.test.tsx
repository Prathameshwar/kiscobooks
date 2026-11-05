import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DisplayConfigProvider } from '@janso/ui';
import { PurchaseWorkflowWorkspace, type PurchaseWorkflowPermissions } from '../app/components/PurchaseWorkflowWorkspace';
import { PURCHASE_DEMO_POLICY, purchaseExample } from '../app/lib/purchase-workspace';
import { createPurchaseMemoryAdapter, type PurchaseContext, type PurchaseMemoryAdapter, type PurchaseWorkflowRecord } from '../app/lib/purchase-workflow';
import { BEFORE_COMPANY_CHANGE } from '../app/lib/use-unsaved-changes';
import { goTo } from '../app/lib/navigate';
import type { ServiceRequest } from '../app/lib/service-call';
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn() }));
vi.setConfig({ testTimeout: 25000 });
const context = { company: 'company-a', year: '2026' }, today = '2026-10-31';
const permissions: PurchaseWorkflowPermissions = { create: true, edit: true, submit: true };
beforeEach(() => vi.clearAllMocks());
function mount(options: { example?: string; access?: Partial<PurchaseWorkflowPermissions>; factory?: (context: PurchaseContext) => PurchaseMemoryAdapter; filled?: boolean } = {}) {
  return render(<DisplayConfigProvider config={{ currency: 'INR', currencySymbol: '₹' }}><PurchaseWorkflowWorkspace context={context} today={today} permissions={{ ...permissions, ...options.access }} initialExample={options.example} initialDraft={options.filled ? purchaseExample(today) : undefined} createAdapter={options.factory} /></DisplayConfigProvider>);
}
async function examples(user: ReturnType<typeof userEvent.setup>) {
  const summary = screen.getByText('Explore workflow examples');
  if (!summary.closest('details')!.open) await user.click(summary);
}
async function outcome(user: ReturnType<typeof userEvent.setup>, value: string) {
  await examples(user); await user.selectOptions(screen.getByLabelText('Next demo command outcome'), value);
}
const companyChange = () => { const event = new Event(BEFORE_COMPANY_CHANGE, { cancelable: true }); window.dispatchEvent(event); return event.defaultPrevented; };

describe('Purchase workflow preview', () => {
  it('creates a tab draft, resumes the same representation and guards its non-persistent data', async () => {
    const user = userEvent.setup(); mount({ filled: true });
    await user.click(screen.getByRole('button', { name: 'Save demo draft' }));
    expect(await screen.findByText(/Demo draft kept in this tab/)).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Edit purchase draft' })).toBeVisible();
    expect(screen.getByText(/DEMO-LOCAL-1 · revision 1/)).toBeVisible();
    expect(companyChange()).toBe(true);
    await examples(user); await user.selectOptions(screen.getByLabelText('Workflow example'), 'NEW');
    await user.click(screen.getByRole('button', { name: 'Open workflow example' }));
    await user.click(screen.getByRole('button', { name: 'Discard current entries and continue' }));
    expect(screen.getByLabelText(/Supplier invoice number/)).toHaveValue('');
    await examples(user); await user.selectOptions(screen.getByLabelText('Drafts in this tab'), 'DEMO-LOCAL-1');
    await user.click(screen.getByRole('button', { name: 'Resume selected demo' }));
    await user.click(screen.getByRole('button', { name: 'Discard current entries and continue' }));
    expect(screen.getByLabelText(/Supplier invoice number/)).toHaveValue('PC-261034');
    expect(screen.getByText(/DEMO-LOCAL-1 · revision 1/)).toBeVisible();
  });
  it('reviews the exact saved draft before submitting and then freezes all editors', async () => {
    const user = userEvent.setup(); mount({ example: 'DRAFT' });
    await user.click(screen.getByRole('button', { name: 'Review & submit demo' }));
    const dialog = screen.getByRole('dialog', { name: 'Review before demo submission' });
    expect(within(dialog).getByText('PC-261034')).toBeVisible();
    expect(within(dialog).getByText('₹5,723.00')).toBeVisible();
    expect(within(dialog).getByText('₹4,723.00')).toBeVisible();
    await user.click(within(dialog).getByRole('button', { name: 'Submit demo for review' }));
    expect(await screen.findByText('Submitted · demo')).toBeVisible();
    expect(screen.getByLabelText(/Supplier invoice number/)).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Save demo draft' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /^Discounts & charges/ }));
    expect(screen.getByLabelText('Component 1 value')).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Apply details' })).not.toBeInTheDocument();
  });
  it.each(['SUBMITTED', 'APPROVED'])('opens %s as read only and still permits detail review', async example => {
    const user = userEvent.setup(); mount({ example });
    expect(screen.getByLabelText(/Supplier invoice number/)).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Save demo draft' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /^Tax details/ }));
    expect(screen.getByRole('dialog', { name: 'Tax details' })).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Done' }));
    expect(screen.getByRole('button', { name: /^Tax details/ })).toHaveFocus();
  });
  it('corrects a rejected bill into a separate draft without changing the original', async () => {
    const adapter = createPurchaseMemoryAdapter(context), user = userEvent.setup(); mount({ example: 'REJECTED', factory: () => adapter });
    expect(screen.getByText('Purchase rejected')).toBeVisible();
    const original = await adapter.latest('DEMO-REJECTED');
    await user.click(screen.getByRole('button', { name: 'Correct purchase' }));
    await user.click(screen.getByRole('button', { name: 'Create demo correction' }));
    expect(screen.getByLabelText('Reason for correction')).toHaveFocus();
    await user.type(screen.getByLabelText('Reason for correction'), 'Correct supplier invoice reference');
    await user.click(screen.getByRole('button', { name: 'Create demo correction' }));
    expect(await screen.findByRole('heading', { name: 'Correct purchase draft' })).toBeVisible();
    expect(screen.getByLabelText(/Supplier invoice number/)).toBeEnabled();
    expect(screen.getByText(/Corrects DEMO-REJECTED, revision 3/)).toBeVisible();
    expect(await adapter.latest('DEMO-REJECTED')).toEqual(original);
    expect(screen.queryByText('Purchase rejected')).not.toBeInTheDocument();
  });
  it('recovers an uncertain save with unchanged body/key and blocks edits and context changes', async () => {
    const adapter = createPurchaseMemoryAdapter(context), request = vi.fn(adapter.request), user = userEvent.setup();
    mount({ filled: true, factory: () => ({ ...adapter, request: request as typeof adapter.request }) });
    await outcome(user, 'UNCERTAIN');
    await user.click(screen.getByRole('button', { name: 'Save demo draft' }));
    expect(await screen.findByText('Demo result unconfirmed')).toBeVisible();
    expect(screen.getByLabelText(/Supplier invoice number/)).toBeDisabled(); expect(companyChange()).toBe(true);
    expect(screen.getByRole('button', { name: 'Open workflow example' })).toBeDisabled();
    fireEvent.click(screen.getByRole('link', { name: 'Back to vouchers' }));
    expect(goTo).not.toHaveBeenCalled(); expect(screen.getByText('Finish the current action')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Recover same demo command' }));
    expect(await screen.findByText(/Demo draft kept in this tab/)).toBeVisible();
    expect(request).toHaveBeenCalledTimes(2); expect(request.mock.calls[1]![0]).toEqual(request.mock.calls[0]![0]);
    expect(screen.getByText(/DEMO-LOCAL-1 · revision 1/)).toBeVisible();
    expect(screen.queryByText('Finish the current action')).not.toBeInTheDocument();
  });
  it('keeps input editable after a known failure and uses a new command after correction', async () => {
    const adapter = createPurchaseMemoryAdapter(context), request = vi.fn(adapter.request), user = userEvent.setup();
    mount({ filled: true, factory: () => ({ ...adapter, request: request as typeof adapter.request }) });
    await outcome(user, 'FAILURE'); await user.click(screen.getByRole('button', { name: 'Save demo draft' }));
    expect(await screen.findByText('Demo command did not complete')).toBeVisible();
    await user.type(screen.getByLabelText(/Supplier invoice number/), '-fixed');
    await outcome(user, 'SUCCESS'); await user.click(screen.getByRole('button', { name: 'Save demo draft' }));
    expect(await screen.findByText(/Demo draft kept in this tab/)).toBeVisible();
    expect(request.mock.calls[1]![0].key).not.toBe(request.mock.calls[0]![0].key);
    expect(screen.getByLabelText(/Supplier invoice number/)).toHaveValue('PC-261034-fixed');
  });
  it('focuses and associates a field-level validation refusal without losing entries', async () => {
    const user = userEvent.setup(); mount({ filled: true }); await outcome(user, 'VALIDATION');
    await user.click(screen.getByRole('button', { name: 'Save demo draft' }));
    const invoice = screen.getByLabelText(/Supplier invoice number/);
    await waitFor(() => expect(invoice).toHaveFocus()); expect(invoice).toHaveAttribute('aria-invalid', 'true');
    expect(invoice).toHaveAccessibleDescription('Check the invoice reference against the supplier bill.');
    expect(invoice).toHaveValue('PC-261034');
  });
  it('compares stale revisions and requires a second confirmation before replacing local input', async () => {
    const user = userEvent.setup(); mount({ example: 'DRAFT' });
    await user.type(screen.getByLabelText(/Supplier invoice number/), '-mine'); await outcome(user, 'STALE');
    await user.click(screen.getByRole('button', { name: 'Save demo draft' }));
    expect(await screen.findByText('A newer revision exists')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Compare latest demo revision' }));
    expect(await screen.findByRole('dialog', { name: 'Compare demo revisions' })).toBeVisible();
    expect(screen.getByLabelText(/Supplier invoice number/)).toHaveValue('PC-261034-mine');
    await user.click(screen.getByRole('button', { name: 'Use latest demo revision' }));
    expect(screen.getByRole('dialog', { name: 'Replace your entries with the latest revision?' })).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Stay with this purchase' }));
    expect(screen.getByLabelText(/Supplier invoice number/)).toHaveValue('PC-261034-mine');
    await user.click(screen.getByRole('button', { name: 'Use latest demo revision' }));
    await user.click(screen.getByRole('button', { name: 'Discard current entries and continue' }));
    expect(screen.getByLabelText(/Supplier invoice number/)).toHaveValue('PC-261034');
    expect(screen.getByText(/DEMO-DRAFT · revision 4/)).toBeVisible();
  });
  it('can keep stale entries as a separate new demo instead of overwriting', async () => {
    const user = userEvent.setup(); mount({ example: 'DRAFT' });
    await user.type(screen.getByLabelText(/Supplier invoice number/), '-mine'); await outcome(user, 'STALE');
    await user.click(screen.getByRole('button', { name: 'Save demo draft' }));
    await user.click(await screen.findByRole('button', { name: 'Compare latest demo revision' }));
    await user.click(await screen.findByRole('button', { name: 'Copy my entries to a new demo' }));
    expect(screen.getByRole('heading', { name: 'New purchase' })).toBeVisible();
    expect(screen.getByLabelText(/Supplier invoice number/)).toHaveValue('PC-261034-mine');
  });
  it('requires explicit leave confirmation and can discard all tab drafts before a company change', async () => {
    const user = userEvent.setup(); mount({ filled: true });
    await user.type(screen.getByLabelText(/Supplier invoice number/), '-edit');
    await user.click(screen.getByRole('link', { name: 'Back to vouchers' }));
    expect(screen.getByRole('dialog', { name: 'Leave purchase preview?' })).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Stay with this purchase' })); expect(goTo).not.toHaveBeenCalled();
    await examples(user); await user.click(screen.getByRole('button', { name: 'Discard tab drafts' }));
    await user.click(screen.getByRole('button', { name: 'Discard current entries and continue' }));
    expect(companyChange()).toBe(false); expect(screen.getByLabelText(/Supplier invoice number/)).toHaveValue('');
  });
  it('separates create/edit/submit rights', async () => {
    const user = userEvent.setup(); mount({ example: 'DRAFT', access: { edit: false, submit: false } });
    expect(screen.getByLabelText(/Supplier invoice number/)).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Save demo draft' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Review & submit demo' })).not.toBeInTheDocument();
    await outcome(user, 'REFUSED'); // Simulation settings cannot grant edit rights.
    expect(screen.getByLabelText(/Supplier invoice number/)).toBeDisabled();
  });
  it('freezes edits after a write refusal while retaining the complete bill', async () => {
    const user = userEvent.setup(); mount({ filled: true }); await outcome(user, 'REFUSED');
    await user.click(screen.getByRole('button', { name: 'Save demo draft' }));
    expect(await screen.findByText('Write access refused')).toBeVisible();
    expect(screen.getByLabelText(/Supplier invoice number/)).toHaveValue('PC-261034');
    expect(screen.getByLabelText(/Supplier invoice number/)).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Save demo draft' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /^Discounts & charges/ }));
    expect(screen.getByLabelText('Component 1 value')).toBeDisabled();
  });
  it('sends only one pending command and blocks company changes until its result arrives', async () => {
    const adapter = createPurchaseMemoryAdapter(context); let finish!: () => void;
    const request = vi.fn(async (input: ServiceRequest) => { await new Promise<void>(resolve => { finish = resolve; }); return adapter.request(input); });
    mount({ filled: true, factory: () => ({ ...adapter, request: request as typeof adapter.request }) });
    const save = screen.getByRole('button', { name: 'Save demo draft' });
    // Two actual activations in one render exercise the synchronous guard, before
    // React can replace the button with its disabled pending representation.
    act(() => { save.click(); save.click(); });
    expect(request).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText(/Supplier invoice number/)).toBeDisabled(); expect(companyChange()).toBe(true);
    await act(async () => finish());
    expect(await screen.findByText(/DEMO-LOCAL-1 · revision 1/)).toBeVisible();
  });
  it('disables every dismissal control while the reviewed submission is pending', async () => {
    const adapter = createPurchaseMemoryAdapter(context); let finish!: () => void;
    const request = vi.fn(async (input: ServiceRequest) => { await new Promise<void>(resolve => { finish = resolve; }); return adapter.request(input); });
    const user = userEvent.setup(); mount({ example: 'DRAFT', factory: () => ({ ...adapter, request: request as typeof adapter.request }) });
    await user.click(screen.getByRole('button', { name: 'Review & submit demo' }));
    const dialog = screen.getByRole('dialog', { name: 'Review before demo submission' });
    await user.click(within(dialog).getByRole('button', { name: 'Submit demo for review' }));
    expect(within(dialog).getByRole('button', { name: 'Close' })).toBeDisabled();
    expect(within(dialog).getByRole('button', { name: 'Back to draft' })).toBeDisabled();
    await user.keyboard('{Escape}'); expect(dialog).toBeVisible();
    await act(async () => finish()); expect(await screen.findByText('Submitted · demo')).toBeVisible();
  });
  it('treats an unverified response as uncertain and recovers the same command before replacing inputs', async () => {
    const adapter = createPurchaseMemoryAdapter(context); let first = true;
    const request = vi.fn(async (input: ServiceRequest) => {
      const result = await adapter.request<PurchaseWorkflowRecord>(input);
      if (first) { first = false; return { ...result, context: { ...context, company: 'other' } }; }
      return result;
    });
    const user = userEvent.setup(); mount({ filled: true, factory: () => ({ ...adapter, request: request as typeof adapter.request }) });
    await user.click(screen.getByRole('button', { name: 'Save demo draft' }));
    expect(await screen.findByText('Demo result unconfirmed')).toBeVisible();
    expect(screen.getByLabelText(/Supplier invoice number/)).toHaveValue('PC-261034');
    expect(screen.queryByText(/DEMO-LOCAL-1/)).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Recover same demo command' }));
    expect(await screen.findByText(/DEMO-LOCAL-1 · revision 1/)).toBeVisible();
    expect(request.mock.calls[1]![0]).toEqual(request.mock.calls[0]![0]);
  });
  it('retains stale input when the latest read fails verification and supports retry', async () => {
    const adapter = createPurchaseMemoryAdapter(context), latest = vi.fn(adapter.latest);
    latest.mockImplementationOnce(async id => ({ ...await adapter.latest(id), context: { ...context, year: 'other' } }));
    const user = userEvent.setup(); mount({ example: 'DRAFT', factory: () => ({ ...adapter, latest }) });
    await user.type(screen.getByLabelText(/Supplier invoice number/), '-mine'); await outcome(user, 'STALE');
    await user.click(screen.getByRole('button', { name: 'Save demo draft' }));
    await user.click(await screen.findByRole('button', { name: 'Compare latest demo revision' }));
    expect(await screen.findByText('Latest revision unavailable')).toBeVisible();
    expect(screen.getByLabelText(/Supplier invoice number/)).toHaveValue('PC-261034-mine');
    await user.click(screen.getByRole('button', { name: 'Retry loading latest' }));
    expect(await screen.findByRole('dialog', { name: 'Compare demo revisions' })).toBeVisible();
  });
  it('allows a draft without supplied tax evidence but refuses submission until that evidence is available', async () => {
    const user = userEvent.setup(); mount({ example: 'DRAFT' });
    const rate = screen.getByRole('textbox', { name: /Rate, line 1/ });
    await user.clear(rate); await user.type(rate, '126'); await user.tab();
    await user.click(screen.getByRole('button', { name: 'Save demo draft' }));
    expect(await screen.findByText(/Demo draft kept in this tab/)).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Review & submit demo' }));
    expect(screen.queryByRole('dialog', { name: 'Review before demo submission' })).not.toBeInTheDocument();
    expect(screen.getByText(/Submission needs complete supplied calculation evidence/)).toBeVisible();
  });
  it('clears a navigation blocker notice after invalid raw numeric input is corrected', async () => {
    const user = userEvent.setup(); mount({ filled: true });
    const rate = screen.getByRole('textbox', { name: /Rate, line 1/ });
    await user.clear(rate); await user.type(rate, '125.12345'); await user.tab();
    await user.click(screen.getByRole('link', { name: 'Back to vouchers' }));
    expect(screen.getByText('Finish the current action')).toBeVisible(); expect(goTo).not.toHaveBeenCalled();
    await user.clear(rate); await user.type(rate, '126'); await user.tab();
    expect(screen.queryByText('Finish the current action')).not.toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: 'Back to vouchers' }));
    expect(screen.getByRole('dialog', { name: 'Leave purchase preview?' })).toBeVisible();
  });
  it('retains original supplier, item and receipt labels when current masters change', () => {
    mount({ example: 'MASTER_CHANGED' });
    expect(screen.getByText('Master details have changed')).toBeVisible();
    expect(screen.getByText(/original trading name/)).toBeVisible();
    expect(screen.getByText(/original receipt label/)).toBeVisible();
    expect(screen.getByRole('combobox', { name: /Item, line 1/ })).toHaveValue('Notebooks · saved item description');
    expect(screen.getByRole('combobox', { name: /^Supplier/ })).toHaveValue('Paper & Co. · original trading name');
  });
  it('ignores a late prior-company save result after context remount and isolates year changes', async () => {
    let finish!: (record: PurchaseWorkflowRecord) => void;
    let captured!: ServiceRequest;
    const oldAdapter = createPurchaseMemoryAdapter(context);
    const factory = (scope: PurchaseContext) => scope.company === context.company && scope.year === context.year ? { ...oldAdapter, request: vi.fn((request: ServiceRequest) => {
      captured = request; return new Promise<never>(resolve => { finish = resolve as never; });
    }) } : createPurchaseMemoryAdapter(scope);
    const user = userEvent.setup();
    const view = render(<PurchaseWorkflowWorkspace context={context} today={today} permissions={permissions} initialDraft={purchaseExample(today)} createAdapter={factory} />);
    await user.click(screen.getByRole('button', { name: 'Save demo draft' }));
    expect(screen.getByRole('button', { name: 'Checking demo command…' })).toBeDisabled();
    const next = { company: 'company-b', year: '2027' };
    view.rerender(<PurchaseWorkflowWorkspace context={next} today={today} permissions={permissions} createAdapter={factory} />);
    expect(screen.getByLabelText(/Supplier invoice number/)).toHaveValue('');
    await act(async () => finish(await oldAdapter.request<PurchaseWorkflowRecord>(captured)));
    expect(screen.getByLabelText(/Supplier invoice number/)).toHaveValue('');
    expect(screen.queryByText(/DEMO-LOCAL-1/)).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Load example bill' }));
    view.rerender(<PurchaseWorkflowWorkspace context={{ ...next, year: '2028' }} today={today} permissions={permissions} createAdapter={factory} />);
    expect(screen.getByLabelText(/Supplier invoice number/)).toHaveValue('');
  });
});
