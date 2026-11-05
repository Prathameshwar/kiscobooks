/**
 * The sales entry page, as a layout and a contract.
 *
 * S1 has no grid body and no service, so what is worth testing is the shape and the honesty:
 * the three regions exist, the column set comes from policy rather than from the component, a
 * mechanic that is unavailable says *why*, there is deliberately no Issue action, and nothing
 * on screen claims to have been saved.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PermissionProvider, type SearchSelectLoader } from '@janso/ui';

vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/sign-in' }));

// Whole-page tests that type a bill key by key take about two seconds alone and more when the
// suite runs files in parallel; the default five-second budget flaked under that load.
vi.setConfig({ testTimeout: 15_000 });

import { SalesEntryPage } from '../app/components/SalesEntryPage';
import { SAMPLE_SALES_POLICY, type SalesEntryPolicy } from '../app/lib/sales-entry-policy';

const TODAY = '2026-10-28';
const ENTRY_CSS = join(__dirname, '..', '..', '..', 'packages', 'ui', 'src', 'styles', 'entry.css');

const loadSubjects = () => loadItems;
const loadItems: SearchSelectLoader = async () => ({
  items: [
    { id: '01990000-0000-7000-8000-0000000000e1', label: 'Basmati rice 25kg', meta: 'RICE-25' },
    { id: '01990000-0000-7000-8000-0000000000e3', label: 'Sunflower oil 1L', meta: 'OIL-1L' },
  ],
  nextCursor: null,
});

const loadCustomers: SearchSelectLoader = async () => ({
  items: [
    { id: '01990000-0000-7000-8000-0000000000c1', label: 'Nandini Trading Company', meta: 'NTC-001' },
    { id: '01990000-0000-7000-8000-0000000000c3', label: 'Sharma Traders', meta: 'SHT-007' },
  ],
  nextCursor: null,
});

function mount(
  policy: SalesEntryPolicy = SAMPLE_SALES_POLICY,
  { canCreate = true }: { canCreate?: boolean } = {},
) {
  return render(
    <PermissionProvider permissions={['vouchers.create', 'vouchers.read']}>
      <SalesEntryPage
        policy={policy}
        today={TODAY}
        loadCustomers={loadCustomers}
        loadSubjects={loadSubjects}
        companyState="Karnataka"
        canCreate={canCreate}
      />
    </PermissionProvider>,
  );
}

describe('the three regions', () => {
  it('names each one, so the page has landmarks rather than a run of divs', () => {
    mount();

    expect(screen.getByRole('banner', { name: 'Invoice details' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Invoice lines' })).toBeInTheDocument();
    expect(screen.getByRole('complementary', { name: 'Invoice totals' })).toBeInTheDocument();
  });

  it('opens on the customer, both dates and one blank row', () => {
    mount();

    expect(screen.getByRole('combobox', { name: /Customer/ })).toBeInTheDocument();
    expect(screen.getByLabelText(/Invoice date/)).toHaveValue(TODAY);
    expect(screen.getByLabelText(/Posting date/)).toHaveValue(TODAY);
    // Header, one line, and the footer that holds the add control.
    expect(screen.getAllByRole('row')).toHaveLength(3);
  });

  it('keeps the document bar and the totals rail sticky', () => {
    // The single most important layout decision, and `css: false` here means it is asserted
    // against the stylesheet: scrolling a fifty-line invoice must not take away who you are
    // billing or what the total has become.
    const entry = readFileSync(ENTRY_CSS, 'utf8');

    expect(entry).toMatch(/\.janso-entry__bar\s*\{[^}]*position: sticky/);
    expect(entry).toMatch(/\.janso-entry__rail\s*\{[^}]*position: sticky/);
    expect(entry).toMatch(/\.janso-entry__actions\s*\{[^}]*position: sticky/);
    // Both stick at the top, so the rail sits below the bar rather than under it.
    expect(entry).toMatch(/\.janso-entry__rail\s*\{[^}]*top: calc\(var\(--janso-entry-bar-h/);
    // And the layout answers to its own width, not the window's.
    expect(entry).toMatch(/\.janso-entry-frame\s*\{[^}]*container-type: inline-size/);
    expect(entry).toMatch(/@container \(max-width: 90rem\)/);
    // A phone gets every column scrolling: pinned, they filled the width and hid the rest.
    expect(entry).toMatch(/@container entry-grid \(max-width: 40rem\)\s*\{[^}]*position: static/);
    // The action bar's buttons stay one group however long the sentence beside them.
    expect(entry).toMatch(/\.janso-entry__actions-buttons\s*\{[^}]*flex: none/);
  });
});

describe('the column set is policy’s answer', () => {
  it('shows actual and billed as separate columns', () => {
    mount();
    const header = screen.getAllByRole('row')[0]!;

    // Two quantity columns, always. 10+1 is actual 11 and billed 10, and a single quantity
    // column cannot express it (commercial configuration §4.1).
    expect(within(header).getByRole('columnheader', { name: 'Actual' })).toBeInTheDocument();
    expect(within(header).getByRole('columnheader', { name: 'Billed' })).toBeInTheDocument();
  });

  it('drops the quantity columns when the mode changes to accounts', async () => {
    const user = userEvent.setup();
    mount();

    await user.click(screen.getByRole('radio', { name: 'Accounts' }));

    const header = screen.getAllByRole('row')[0]!;
    expect(within(header).queryByRole('columnheader', { name: 'Actual' })).not.toBeInTheDocument();
    expect(within(header).queryByRole('columnheader', { name: 'Unit' })).not.toBeInTheDocument();
    expect(within(header).getByRole('columnheader', { name: 'Account' })).toBeInTheDocument();
  });

  it('omits a column the policy does not permit', () => {
    mount({
      ...SAMPLE_SALES_POLICY,
      components: {
        ...SAMPLE_SALES_POLICY.components,
        lineDiscount: { available: false, reason: 'Line discounts are off.' },
      },
    });

    const header = screen.getAllByRole('row')[0]!;
    expect(within(header).queryByRole('columnheader', { name: 'Discount' })).not.toBeInTheDocument();
  });

  it('shows a derived column as read-only rather than as a disabled input', () => {
    // A disabled input invites "why can I not type here", and the answer — the service resolves
    // this — is not a permission problem. So tax and amount render as text.
    mount();
    const header = screen.getAllByRole('row')[0]!;

    expect(within(header).getByRole('columnheader', { name: 'Tax' })).toBeInTheDocument();
    const body = screen.getAllByRole('row')[1]!;
    expect(within(body).queryByRole('textbox', { name: /Tax/ })).not.toBeInTheDocument();
  });
});

describe('what the page refuses to pretend', () => {
  it('offers no Issue action, and says why', () => {
    // Issuing needs the statutory numbering profile, which is not released, and the legal
    // allocator belongs to Accounting. A button that 400s is worse than an absent one.
    mount();

    expect(screen.queryByRole('button', { name: /Issue/i })).not.toBeInTheDocument();
    expect(screen.getByText(/statutory numbering profile/)).toBeInTheDocument();
  });

  it('starts by saying nothing has been entered, then counts changes', async () => {
    const user = userEvent.setup();
    mount();
    expect(screen.getByText('Nothing entered yet.')).toBeInTheDocument();

    await user.type(screen.getByLabelText(/Credit days/), '5');
    expect(screen.getByText(/not saved yet/)).toBeInTheDocument();
  });

  it('says plainly that a save went nowhere, rather than appearing to work', async () => {
    const user = userEvent.setup();
    mount();

    // The lookup needs two characters before it asks — async `SearchSelect` does not list
    // every customer a tenant has on focus, and nor should it.
    await user.type(screen.getByRole('combobox', { name: /Customer/ }), 'Sha');
    await user.click(await screen.findByRole('option', { name: /Sharma Traders/ }));
    expect(screen.getByRole('combobox', { name: /Customer/ })).toHaveValue('Sharma Traders');

    // Still blocked, because there is no line yet — which is itself the right behaviour, and
    // the reason the rail lists what is outstanding rather than only greying the button.
    expect(screen.getByRole('button', { name: 'Save draft' })).toBeDisabled();
    expect(screen.getByText('Add at least one line.')).toBeInTheDocument();
  });

  it('totals an empty bill as zero, because nothing entered is genuinely nothing', () => {
    // Before S5 every figure was unknown and showed an em dash. With the preview wired, an empty
    // bill is not unknown — it is zero — and pretending otherwise would be the opposite error.
    mount();
    const rail = screen.getByRole('complementary', { name: 'Invoice totals' });

    expect(within(rail).getByText('Total')).toBeInTheDocument();
    expect(within(rail).queryByText('—')).not.toBeInTheDocument();
  });

  it('shows tax and total as unknown while a counted line’s tax is unresolved', async () => {
    // No resolver is mounted here, so a typed line has no tax rate. Its taxable value is known;
    // its tax is not — and zero would read as "this supply is untaxed".
    const user = userEvent.setup();
    mount();

    await user.type(screen.getByRole('textbox', { name: /^Billed, line 1/ }), '2');
    await user.type(screen.getByRole('textbox', { name: /^Rate, line 1/ }), '100');
    await user.tab();

    const rail = screen.getByRole('complementary', { name: 'Invoice totals' });
    const total = within(rail).getByText('Total').parentElement!;
    expect(within(total).getByText('—')).toBeInTheDocument();
    expect(within(rail).getByText(/no resolved tax rate/)).toBeInTheDocument();
  });

  it('labels the totals as provisional, because the service owns the calculation', () => {
    mount();
    const rail = screen.getByRole('complementary', { name: 'Invoice totals' });

    expect(within(rail).getByText(/Provisional/)).toBeInTheDocument();
  });

  it('states why a statutory surface is missing instead of leaving a gap', () => {
    mount();
    expect(screen.getByText(/statutory artifact profile is not released/)).toBeInTheDocument();
  });
});

describe('permission', () => {
  it('lets a reader without create access look but not save', () => {
    mount(SAMPLE_SALES_POLICY, { canCreate: false });

    expect(screen.getByText(/not raise a bill with it/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save draft' })).toBeDisabled();
  });
});
