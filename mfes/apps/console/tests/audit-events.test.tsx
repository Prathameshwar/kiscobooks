import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AuditEvents } from '../app/components/AuditEvents';
import {
  AuditQueryError,
  AUDIT_ENTITY_TYPES,
  createAuditDetailLoader,
  createAuditLoader,
  type AuditDetailLoader,
  type AuditListParams,
  type AuditLoader,
} from '../app/lib/audit-events';
import { getAuditTrail, type AuditTrail } from '../app/lib/audit-trail';
import { renderWithProviders } from './helpers';

/**
 * The audit log screen — `DataTable` and the list toolbar wired to the trail's contract.
 *
 * The loaders are injected rather than mocked at the module boundary: they are the transport seam
 * (`lib/audit-events`), so passing the *real* stand-in through a recorder is both the faster suite
 * and the more honest one — every request goes through the same cursor, filter and limit rules the
 * endpoint enforces, so a screen that reused a cursor earns the same 422 it would earn in
 * production instead of a convenient page.
 *
 * `delayMs: 0` keeps real timers: nothing here needs the pending state held open, and the
 * fake-timer shim `customer-filter.test.tsx` needs is worth its cost only when it buys something.
 */

/** A fixed instant, so the rendered stamps and the range filter never depend on when this runs. */
afterEach(() => vi.restoreAllMocks());

const NOW = Date.parse('2026-09-13T12:00:00.000Z');

/** Every request the screen made, and every rejection it was handed. */
type Harness = {
  trail: AuditTrail;
  requests: AuditListParams[];
  detailRequests: string[];
  failures: string[];
};

const harness: Harness = {
  trail: { events: [], details: {} },
  requests: [],
  detailRequests: [],
  failures: [],
};

beforeEach(async () => {
  harness.trail = await getAuditTrail(NOW);
  harness.requests = [];
  harness.detailRequests = [];
  harness.failures = [];
  /* `useColumnPreferences` persists the hidden set, and one jsdom serves the whole file — without
   * this, the test that hides a column would hide it for every test that follows. */
  globalThis.localStorage?.clear();
});

/**
 * The real loader, recorded. `pageSize` forces the size of the page it answers with, which is how a
 * twelve-event trail is made to page at all: the pager's smallest choice is 25.
 */
function recordedLoader(pageSize?: number): AuditLoader {
  const load = createAuditLoader(harness.trail.events, 0);
  return async (params, signal) => {
    harness.requests.push(params);
    try {
      return await load(pageSize === undefined ? params : { ...params, limit: pageSize }, signal);
    } catch (error) {
      if (!(error instanceof DOMException && error.name === 'AbortError')) {
        harness.failures.push(error instanceof Error ? error.message : String(error));
      }
      throw error;
    }
  };
}

function recordedDetailLoader(): AuditDetailLoader {
  const load = createAuditDetailLoader(harness.trail.details, 0);
  return (event, signal) => {
    harness.detailRequests.push(event.id);
    return load(event, signal);
  };
}

type Options = {
  permissions?: string[];
  load?: AuditLoader;
  loadDetail?: AuditDetailLoader;
  /** Forces the answered page size, for the tests that walk the trail. */
  pageSize?: number;
};

async function renderAudit({ permissions, load, loadDetail, pageSize }: Options = {}) {
  const user = userEvent.setup();
  const result = await renderWithProviders(
    <AuditEvents
      trail={harness.trail}
      exportData={async () => ({ count: 12, truncated: false })}
      load={load ?? recordedLoader(pageSize)}
      loadDetail={loadDetail ?? recordedDetailLoader()}
    />,
    permissions ? { permissions } : {},
  );

  /* The first request resolves through a microtask and a zero timer, so every test starts settled —
   * on rows, or on whatever state its loader was told to produce. */
  await waitFor(() => expect(screen.getByRole('table')).not.toHaveAttribute('aria-busy'));
  return { user, ...result };
}

/** The body's data rows: no heading row, and no open detail panel. */
function bodyRows(): HTMLElement[] {
  const body = screen.getByRole('table').querySelector('tbody') as HTMLElement;
  return within(body)
    .queryAllByRole('row')
    .filter((row) => !row.classList.contains('janso-table__detail-row'));
}

function cellsOf(row: HTMLElement): string[] {
  return within(row)
    .getAllByRole('cell')
    .map((cell) => cell.textContent?.trim() ?? '');
}

/** The action in each row, in page order — the cheapest proof of *which* page is on screen. */
function actionsOnPage(): string[] {
  // Control column, Recorded, Category, Action: the expand button leads every row.
  return bodyRows().map((row) => cellsOf(row)[3] ?? '');
}

describe('the audit log', () => {
  it('refreshes the recent audit page without reusing its signed cursor or losing category filters', async () => {
    const { user } = await renderAudit({ pageSize: 2 });
    await user.selectOptions(screen.getByRole('combobox', { name: 'Category' }), 'money');
    await waitFor(() => expect(harness.requests.at(-1)?.category).toBe('money'));
    await waitFor(() => expect(screen.getByRole('button', { name: /next/i })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: /next/i }));
    await waitFor(() => expect(harness.requests.at(-1)?.cursor).toBeTruthy());
    await waitFor(() => expect(screen.getByRole('button', { name: 'Refresh audit logs' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Refresh audit logs' }));
    await waitFor(() => expect(harness.requests.at(-1)).toMatchObject({ category: 'money', cursor: null }));
    expect(screen.getByRole('combobox', { name: 'Category' })).toHaveValue('money');
  });

  it('lists the trail newest first, and says what each row is about', async () => {
    await renderAudit();

    expect(bodyRows()).toHaveLength(harness.trail.events.length);
    expect(cellsOf(bodyRows()[0]!)).toEqual(
      expect.arrayContaining(['Money', 'invoice.posted', expect.stringContaining('invoice ·')]),
    );

    // The endpoint's own default, restated on the screen so the first request and the header agree.
    expect(harness.requests[0]).toMatchObject({ sort: '-occurred_at', cursor: null });
    expect(screen.getByRole('columnheader', { name: /Recorded/ })).toHaveAttribute(
      'aria-sort',
      'descending',
    );
  });

  it('shows an actor as an id, never as a name', async () => {
    await renderAudit();
    const table = screen.getByRole('table');

    /*
     * The row holds `actor_user_id` and nothing else about the person (docs/audit.md §5.2,
     * CLAUDE.md §6.9). The signed-in user's own name is elsewhere on the page, so this asserts on
     * the table rather than on the document.
     */
    expect(within(table).getAllByText(/^user ·[0-9a-f]{6}$/).length).toBeGreaterThan(0);
    expect(table.textContent).not.toMatch(/Prathameshwar/);
    // A service acted on one event, and that reads as its type rather than as a blank.
    expect(within(table).getByText('service')).toBeInTheDocument();
  });

  it('states the instant, not how long ago it was', async () => {
    await renderAudit();
    const table = screen.getByRole('table');

    /*
     * `datetime`, not `relative`, in this column: an auditor cites an instant — and the column is
     * rendered on the server first, where "2 hours ago" would be computed against a different clock
     * than the browser's and hydrate to a mismatch. The elapsed form is prose in the panel, which
     * only ever exists after a click.
     */
    expect(within(table).getAllByText(/13 Sep 2026, \d\d:\d\d/).length).toBeGreaterThan(0);
    expect(table.textContent).not.toMatch(/ago/);
  });

  it('has no search box, no selection and no row verbs', async () => {
    await renderAudit();

    /*
     * All three are deliberate. The endpoint has no `q` — substring-scanning a partitioned
     * append-only table is the query that takes the database down. And an audit row cannot be
     * edited, voided or deleted; that is what makes it evidence (docs/audit.md §2.2), so a kebab
     * would have nothing to put in it and a checkbox nothing to act on.
     */
    expect(screen.queryByRole('searchbox')).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Select all rows/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Actions for/ })).not.toBeInTheDocument();
  });

  it('says that security events are excluded, and will not let that be lifted', async () => {
    await renderAudit();

    /*
     * Screen-imposed and unremovable: security events are a separate surface behind
     * `audit.read_security` (§5.1). Stated rather than silent, because a reader looking for a failed
     * sign-in needs to know why it is not here — and it must not look like a filter they applied.
     */
    const chips = screen.getByRole('group', { name: 'Filters in force' });
    expect(within(chips).getByText('Security events excluded')).toBeInTheDocument();
    expect(chips).not.toHaveTextContent(/never/i);
    expect(within(chips).queryByRole('button')).not.toBeInTheDocument();
    // Nothing removable, so no "Clear all" either — a button that would change nothing.
    expect(within(chips).queryByRole('button', { name: 'Clear all' })).not.toBeInTheDocument();
  });

  it('does not report an empty event count when the audit request failed', async () => {
    await renderAudit({ load: async () => { throw new Error('Audit temporarily unavailable'); } });
    expect(screen.getByText('Audit temporarily unavailable')).toBeVisible();
    expect(screen.queryByText('No events')).not.toBeInTheDocument();
  });

  it('filters by category, chips what it applied, and lifts it again', async () => {
    const { user } = await renderAudit();

    await user.selectOptions(screen.getByLabelText('Category'), 'money');
    await waitFor(() => expect(harness.requests.at(-1)).toMatchObject({ category: 'money' }));
    await waitFor(() => expect(bodyRows()).toHaveLength(4));

    const chips = screen.getByRole('group', { name: 'Filters in force' });
    expect(within(chips).getByText('Money')).toBeInTheDocument();

    await user.click(
      within(chips).getByRole('button', { name: 'Remove filter: Category is Money' }),
    );
    await waitFor(() => expect(bodyRows()).toHaveLength(harness.trail.events.length));
    expect(harness.requests.at(-1)?.category).toBeUndefined();
    // Every request was accepted: a filter change that kept its cursor would be a 422 here.
    expect(harness.failures).toEqual([]);
  });

  it('turns a period choice into an instant bound, computed once', async () => {
    vi.spyOn(Date, 'now').mockReturnValue(NOW);
    const { user } = await renderAudit();

    await user.selectOptions(screen.getByLabelText('Recorded'), '24h');
    await waitFor(() => expect(harness.requests.at(-1)?.occurred_from).toEqual(expect.any(String)));
    const from = harness.requests.at(-1)!.occurred_from!;

    /* A bound, not a phrase: the chip states the instant, so it cannot drift as the page stays open
     * the way "last 24 hours" would. Asserted by shape rather than against a literal, because the
     * bound is derived from the live clock — as it must be, since a range is what the reader means
     * *now* — while the trail is seeded from a fixed instant. */
    const chips = screen.getByRole('group', { name: 'Filters in force' });
    expect(within(chips).getByText('on or after')).toBeInTheDocument();
    expect(within(chips).getByText(/^\d\d [A-Za-z]{3,4} \d{4}, \d\d:\d\d$/)).toBeInTheDocument();

    // Only the events inside the window survive, and the window really does exclude some.
    const inWindow = harness.trail.events.filter((event) => event.occurred_at >= from).length;
    expect(inWindow).toBeGreaterThan(0);
    expect(inWindow).toBeLessThan(harness.trail.events.length);
    await waitFor(() => expect(bodyRows()).toHaveLength(inWindow));

    // And the bound is fixed when it is chosen, not recomputed on the next request.
    await user.selectOptions(screen.getByLabelText('Category'), 'money');
    await waitFor(() => expect(harness.requests.at(-1)?.category).toBe('money'));
    expect(harness.requests.at(-1)?.occurred_from).toBe(from);
    expect(harness.failures).toEqual([]);
  });

  it('pages forward and back with the cursors it was given', async () => {
    const { user } = await renderAudit({ pageSize: 5 });
    const first = actionsOnPage();
    expect(first).toHaveLength(5);

    await user.click(screen.getByRole('button', { name: 'Next page of events' }));
    await waitFor(() => expect(harness.requests.at(-1)?.cursor).toEqual(expect.any(String)));
    await waitFor(() => expect(actionsOnPage()).not.toEqual(first));
    // A keyset walk visits each row once: no overlap between two consecutive pages.
    expect(actionsOnPage().filter((action) => first.includes(action))).toEqual([]);

    /* "Previous" is a step back through the cursors already used, not a query — the first page's
     * cursor is `null`, because a keyset cursor only ever points forward. */
    await user.click(screen.getByRole('button', { name: 'Previous page of events' }));
    await waitFor(() => expect(actionsOnPage()).toEqual(first));
    expect(harness.requests.at(-1)?.cursor).toBeNull();
    expect(harness.failures).toEqual([]);
  });

  it('restarts the walk when the query changes, rather than reusing a cursor', async () => {
    const { user } = await renderAudit({ pageSize: 5 });

    /* Forward first, so a cursor is genuinely in hand at the moment the query changes — the only
     * state in which this can go wrong at all. */
    await user.click(screen.getByRole('button', { name: 'Next page of events' }));
    await waitFor(() => expect(harness.requests.at(-1)?.cursor).toEqual(expect.any(String)));

    await user.selectOptions(screen.getByLabelText('Category'), 'admin');
    await waitFor(() => expect(harness.requests.at(-1)?.category).toBe('admin'));

    expect(harness.requests.at(-1)?.cursor).toBeNull();
    /* The proof that it restarted rather than being rejected: the stand-in answers a cursor minted
     * for a different query with a 422, and nothing failed. */
    expect(harness.failures).toEqual([]);
  });

  it('states the range it is showing, and offers no page numbers or total', async () => {
    await renderAudit();

    // Twelve events at the default page size: one page, so both directions are dead ends.
    expect(screen.getByRole('button', { name: 'Next page of events' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Previous page of events' })).toBeDisabled();

    // A keyset walk has no count to derive either of those from (api-conventions §2.1).
    expect(screen.getByText('Showing 1–12')).toBeInTheDocument();
    expect(screen.queryByText(/of \d+ pages/)).not.toBeInTheDocument();
  });

  it('hides a column on request, and refuses the one that identifies the row', async () => {
    const { user } = await renderAudit();
    const requestsBefore = harness.requests.length;

    await user.click(screen.getByRole('button', { name: 'Columns' }));
    const menu = screen.getByRole('menu', { name: 'Columns' });

    /* `occurred_at` is locked: it is what a reader cites. Offered with its reason rather than
     * omitted, because a silently missing toggle reads as a bug in the picker. */
    const locked = within(menu).getByRole('menuitemcheckbox', { name: /Recorded/ });
    expect(locked).toHaveTextContent('Always shown');
    await user.click(locked);
    expect(screen.getByRole('columnheader', { name: /Recorded/ })).toBeInTheDocument();

    await user.click(within(menu).getByRole('menuitemcheckbox', { name: /Chain/ }));
    await waitFor(() =>
      expect(screen.queryByRole('columnheader', { name: /Chain/ })).not.toBeInTheDocument(),
    );

    /* A hidden column is layout, not authorization: the field arrived in the payload either way, so
     * nothing is re-requested for it (docs/field-permissions.md §6). */
    expect(harness.requests).toHaveLength(requestsBefore);
  });

  it('offers an export only to an actor holding the export key', async () => {
    await renderAudit();
    /* The fixture session holds `audit.read` and not `audit.export`. Absent rather than greyed: a
     * disabled control tells someone a capability exists that they are not going to get. */
    expect(screen.queryByRole('button', { name: 'Export' })).not.toBeInTheDocument();
  });

  it('asks the server for an export, and never builds a file', async () => {
    const { user } = await renderAudit({ permissions: ['audit.read', 'audit.export'] });

    await user.click(screen.getByRole('button', { name: 'Export' }));
    await user.click(screen.getByRole('menuitem', { name: 'JSON' }));

    /*
     * Nothing downloaded and nothing assembled from the rows in hand: an export covers the query
     * rather than the page, re-applies field policy server-side and is itself audited
     * (CLAUDE.md §6.15, §5.14).
     */
    expect(await screen.findByText('12 events exported.')).toBeInTheDocument();
    expect(screen.getByText('Export ready')).toBeInTheDocument();
  });

  it('fetches a row’s detail only when it is opened', async () => {
    const { user } = await renderAudit();

    /* Twelve rows on screen and no detail request: `changes` and `context` are JSON columns a list
     * must not return, and most rows are never expanded (api-conventions §3). */
    expect(harness.detailRequests).toEqual([]);

    await user.click(screen.getByRole('button', { name: /^Show details for invoice\.posted/ }));
    await waitFor(() => expect(harness.detailRequests).toHaveLength(1));

    const changes = (await screen.findByText('What changed')).closest(
      '.console-audit-detail__block',
    ) as HTMLElement;
    /* The before and the after, as the strings the trail stored — a money amount is never a number
     * on this wire (CLAUDE.md §6.1), and it is not re-formatted here either: the point of the panel
     * is what was written, not how it would read today. */
    expect(within(changes).getByRole('rowheader', { name: 'status' })).toBeInTheDocument();
    expect(within(changes).getByText('draft')).toBeInTheDocument();
    expect(within(changes).getByText('posted')).toBeInTheDocument();
    expect(within(changes).getAllByText('18400.0000')).toHaveLength(2);
  });

  it('shows the chain proof, and says when an event starts the chain', async () => {
    const { user } = await renderAudit();
    const oldest = harness.trail.events[harness.trail.events.length - 1]!;

    await user.click(
      screen.getByRole('button', { name: new RegExp(`^Show details for ${oldest.action}`) }),
    );

    /* The hash chain is what makes the trail tamper-evident, so it is shown in full (§4.2) — and the
     * first event of a chain has no predecessor, which is stated rather than left blank. */
    expect(await screen.findByText('First event in this chain')).toBeInTheDocument();
    expect(screen.getByText(harness.trail.details[oldest.id]!.row_hash)).toBeInTheDocument();
  });

  it('says a detail could not be read, and offers to try again', async () => {
    let attempts = 0;
    const { user } = await renderAudit({
      loadDetail: async (event) => {
        attempts += 1;
        if (attempts === 1) throw new Error('gone');
        return harness.trail.details[event.id]!;
      },
    });

    await user.click(screen.getAllByRole('button', { name: /^Show details for/ })[0]!);

    // The row is still on screen and still evidence — only this one request failed.
    expect(await screen.findByText('This event could not be read')).toBeInTheDocument();
    expect(screen.getByRole('table')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('What changed')).toBeInTheDocument();
    expect(attempts).toBe(2);
  });

  it('renders a rejected query as a recoverable state, and retries it', async () => {
    let calls = 0;
    const real = createAuditLoader(harness.trail.events, 0);
    const { user } = await renderAudit({
      load: async (params, signal) => {
        calls += 1;
        if (calls === 1) throw new AuditQueryError('cursor was minted for a different query');
        return real(params, signal);
      },
    });

    /*
     * A 422 on a list is most often a cursor that no longer describes this query — recoverable,
     * because the rows are all still there and only the position was lost. So the state names the
     * server's own detail and the way out is the first page of the same query (§2.1). "Try again"
     * has to re-request even when the walk is already at its head, or it is a dead control on the
     * first page — which is exactly where a first-load failure lands.
     */
    expect(await screen.findByText('cursor was minted for a different query')).toBeInTheDocument();
    expect(screen.getByText("We couldn't accept those details")).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(bodyRows()).toHaveLength(harness.trail.events.length));
  });

  it('renders an outage as an outage, and retries that too', async () => {
    let calls = 0;
    const real = createAuditLoader(harness.trail.events, 0);
    const { user } = await renderAudit({
      load: async (params, signal) => {
        calls += 1;
        if (calls === 1) throw new Error('the audit service is unavailable');
        return real(params, signal);
      },
    });

    /* Not "no events", which would be a false all-clear on the one table an auditor trusts to be
     * complete. */
    expect(await screen.findByText('the audit service is unavailable')).toBeInTheDocument();
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.queryByText('No events match these filters')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(bodyRows()).toHaveLength(harness.trail.events.length));
  });

  it('announces the row count for a reader who cannot see the table', async () => {
    await renderAudit();
    /* A table's own rows are not announced when they change, so the count is stated in a live region
     * rather than left to be discovered. */
    expect(screen.getByText('12 rows')).toBeInTheDocument();
  });

  it('says nothing matches, and offers to lift the filters', async () => {
    const { user } = await renderAudit();

    await user.selectOptions(screen.getByLabelText('Subject'), 'report_run');
    await user.selectOptions(screen.getByLabelText('Category'), 'money');

    /* "No matches" is about the query and is recoverable by lifting it — a different failure from
     * "nothing yet", which is about the ledger. */
    expect(await screen.findByText('No events match these filters')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Clear filters' }));
    await waitFor(() => expect(bodyRows()).toHaveLength(harness.trail.events.length));

    // The screen-imposed chip survives a "clear all": it was never the reader's to lift.
    expect(screen.getByText('Security events excluded')).toBeInTheDocument();
  });
});

describe('the audit screen’s own guards', () => {
  it('re-requests a detail that was closed and opened again', async () => {
    const { user } = await renderAudit();

    await user.click(screen.getAllByRole('button', { name: /^Show details for/ })[0]!);
    await waitFor(() => expect(harness.detailRequests).toHaveLength(1));

    await user.click(screen.getByRole('button', { name: /^Hide details for/ }));
    expect(screen.queryByText('What changed')).not.toBeInTheDocument();

    /* A fresh request rather than a cached panel: the trail is append-only, but the panel is a
     * second endpoint and the row may read differently once field policy is re-applied to it. */
    await user.click(screen.getAllByRole('button', { name: /^Show details for/ })[0]!);
    await waitFor(() => expect(harness.detailRequests).toHaveLength(2));
  });

  it('does not re-request the page when nothing about the query changed', async () => {
    const { user } = await renderAudit();
    const before = harness.requests.length;

    /* Opening a panel is presentation. A screen that rebuilt its request object on every render
     * would re-fetch the whole page here, which is the defect this asserts against. */
    await user.click(screen.getAllByRole('button', { name: /^Show details for/ })[0]!);
    await waitFor(() => expect(harness.detailRequests).toHaveLength(1));

    expect(harness.requests).toHaveLength(before);
  });
});

/** A guard on the trail the screen is built from, rather than on the screen. */
describe('the trail handed to the screen', () => {
  it('is built per call, so no two requests share one object', async () => {
    const first = await getAuditTrail(NOW);
    const second = await getAuditTrail(NOW);

    /* A module-scope binding is one object per server *process*, shared by every request it serves —
     * for an audit trail, the cross-tenant leak session-level filtering exists to prevent
     * (CLAUDE.md §5.3). */
    expect(first.events).not.toBe(second.events);
    expect(first.events).toEqual(second.events);
  });
});

it('shows authorized actor names with the stable IDs in an opened detail', async () => {
  const user = userEvent.setup();
  for (const detail of Object.values(harness.trail.details)) {
    detail.actor_name = 'Authorized actor';
    detail.on_behalf_of_name = 'Effective actor';
    detail.on_behalf_of_user_id = 'effective-user';
  }
  renderWithProviders(<AuditEvents load={recordedLoader()} loadDetail={recordedDetailLoader()} />);
  await user.click((await screen.findAllByRole('button', { name: /^Show details for/ }))[0]!);
  expect(await screen.findByText(/^Authorized actor \(/)).toBeInTheDocument();
  expect(screen.getByText('Effective actor (effective-user)')).toBeInTheDocument();
});


it('offers Catalog entity filters and renders precise money with legacy markers', async () => {
  expect(AUDIT_ENTITY_TYPES).toContain('catalog.item_price');
  expect(AUDIT_ENTITY_TYPES).toContain('catalog.bulk_job');
  const original = harness.trail.events[0]!;
  const event = { ...original, entity_type: 'catalog.item_price', action: 'catalog.item_price.create', category: 'money' };
  harness.trail.events = [event];
  harness.trail.details[event.id] = {
    ...harness.trail.details[event.id]!, ...event,
    changes: { amount: { from: null, to: '900719925474099.1234' },
      source_reference: { from: null, to: null, changed: true } },
  };
  const { user } = await renderAudit();
  await user.click(screen.getByRole('button', { name: /^Show details for catalog\.item_price\.create/ }));
  expect(await screen.findByText('900719925474099.1234')).toBeInTheDocument();
  expect(screen.getByRole('rowheader', { name: 'source_reference' })).toBeInTheDocument();
});
