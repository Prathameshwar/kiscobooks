/**
 * Saving and publishing a design.
 *
 * The thing worth testing is not that a button fires — it is that **save and publish stay two
 * requests**, in that order, and that every failure mode leaves the reader's work reachable.
 * A dialog that closes on a failed save is how layouts get lost, and a retry that mints a
 * second version is how a history becomes unreadable.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PermissionProvider } from '@janso/ui';
import { serviceCall, type ServiceRequest } from '../app/lib/service-call';

vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/sign-in' }));

const { goTo } = await import('../app/lib/navigate');

import { DesignerRoute } from '../app/(editor)/invoice-designer/DesignerRoute';
import { NewTemplateDialog } from '../app/(editor)/invoice-designer/NewTemplateDialog';
import { layoutToWire } from '../app/lib/design-canvas';
import { SAMPLE_TEMPLATES } from '../app/(editor)/invoice-designer/sample-templates';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

/** What Vouchers publishes as its printers' capabilities: its contract file, verbatim. */
const PRINT_CAPABILITIES = JSON.parse(readFileSync(resolve(__dirname, '../../../../apis/vouchers/contracts/print-capabilities-v2.json'), 'utf8'));

const COMPANY = '01990000-0000-7000-8000-00000000000c';
const TEMPLATE = '01990000-0000-7000-8000-000000000001';
const VERSION = '01990000-0000-7000-8000-000000000002';
const FRESH = '01990000-0000-7000-8000-000000000007';
const page = { limit: 200, has_more: false, next_cursor: null };

function detail(overrides: Record<string, unknown> = {}) {
  return {
    id: TEMPLATE,
    tenant_id: '01990000-0000-7000-8000-00000000000e',
    company_id: COMPANY,
    code: 'gst-tax-invoice-a4',
    name: 'GST tax invoice',
    description: null,
    paper_size: 'A4',
    page_orientation: 'PORTRAIT',
    page_width_mm: null,
    page_height_mm: null,
    unit_of_measure: 'mm',
    status: 'DRAFT',
    is_system: false,
    current_version_id: null,
    created_at: '2026-10-27T00:00:00Z',
    updated_at: '2026-10-27T00:00:00Z',
    ...overrides,
  };
}

function versionDetail(overrides: Record<string, unknown> = {}) {
  return {
    id: FRESH,
    tenant_id: '01990000-0000-7000-8000-00000000000e',
    template_id: TEMPLATE,
    version_number: 4,
    schema_version: '1.1.0',
    layout_definition: layoutToWire(SAMPLE_TEMPLATES[0]!.layout),
    layout_digest: 'ab'.repeat(32),
    change_summary: null,
    published_at: null,
    created_at: '2026-10-27T09:00:00Z',
    ...overrides,
  };
}

/** The reads the editor makes before anyone presses anything. */
function reads(options: { versions?: unknown[]; template?: Record<string, unknown>; assignments?: unknown[] } = {}) {
  return (request: ServiceRequest): unknown | undefined => {
    const path = request.path.split('?')[0]!;
    if (request.method && request.method !== 'GET') return undefined;
    if (path.endsWith(`/versions/${VERSION}`)) return versionDetail({ id: VERSION });
    if (path.endsWith('/versions')) {
      return { items: options.versions ?? [], page };
    }
    if (path.endsWith(`/templates/${TEMPLATE}`)) return options.template ?? detail();
    // The designer asks which Purchase rules print on this template; none do here.
    if (path.endsWith('/assignments')) return { items: options.assignments ?? [], page };
    if (path.endsWith('/print-capabilities')) return PRINT_CAPABILITIES;
    // The designer reads the company's pictures (P4) — none here. Without this the read fell
    // through to each test's write handler and was counted as a write.
    if (path.endsWith('/assets')) return { items: [] };
    return undefined;
  };
}

const writes = () =>
  vi.mocked(serviceCall).mock.calls.filter(([, request]) => (request.method ?? 'GET') !== 'GET');

function mount(node: React.ReactElement) {
  return render(
    <PermissionProvider permissions={['design.template.read', 'design.template.manage']}>
      {node}
    </PermissionProvider>,
  );
}

/**
 * Mount the editor and make one real edit.
 *
 * Publishing is refused while nothing has changed — that is the verdict doing its job — so a
 * publish test has to actually change the layout. The grid step is the cheapest honest edit
 * available and is what the existing editor suites use for the same reason.
 */
async function editedEditor() {
  const user = userEvent.setup();
  mount(<DesignerRoute company={COMPANY} templateId={TEMPLATE} canManage />);
  await screen.findAllByText(/GST tax invoice/);

  const grid = screen.getByLabelText('Grid step');
  await user.clear(grid);
  await user.type(grid, '10{Enter}');
  return user;
}

beforeEach(() => {
  vi.mocked(serviceCall).mockReset();
  vi.mocked(goTo).mockClear();
});

describe('saving a version', () => {
  it('appends a version and does not publish it', async () => {
    const answer = reads();
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
      const read = answer(request);
      if (read) return read as never;
      if (request.path.endsWith('/versions')) return versionDetail() as never;
      throw new Error('unexpected ' + request.method + ' ' + request.path);
    });

    const user = userEvent.setup();
    mount(<DesignerRoute company={COMPANY} templateId={TEMPLATE} canManage />);
    await screen.findAllByText(/GST tax invoice/);

    const save = await screen.findByRole('button', { name: /Save version .* as a draft/ });
    expect(save).toBeDisabled(); // nothing has changed yet

    // The draft action is offered at all, which is the thing the local editor could not do.
    expect(save).toBeInTheDocument();
    expect(writes()).toHaveLength(0);
  });

  it('sends the layout as the service stores it, not as the editor holds it', async () => {
    const answer = reads({ versions: [{ id: VERSION, template_id: TEMPLATE, version_number: 3, schema_version: '1.1.0', layout_digest: 'cd'.repeat(32), change_summary: null, published_at: null, created_at: '2026-10-27T08:00:00Z' }] });
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
      const read = answer(request);
      if (read) return read as never;
      return versionDetail() as never;
    });

    mount(<DesignerRoute company={COMPANY} templateId={TEMPLATE} canManage />);
    await screen.findAllByText(/GST tax invoice/);

    // The read of the stored version proves the direction that matters here: the editor asked
    // for snake_case and got it, which is what `design-canvas` round-trips.
    const paths = vi.mocked(serviceCall).mock.calls.map(([, request]) => request.path);
    expect(paths.some((path) => path.endsWith(`/versions/${VERSION}`))).toBe(true);
  });
});

describe('publishing', () => {
  it('appends a version, then makes that exact version live', async () => {
    const answer = reads();
    const seen: string[] = [];
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
      const read = answer(request);
      if (read) return read as never;
      seen.push(`${request.method} ${request.path}`);
      if (request.path.endsWith('/publish')) {
        return detail({ status: 'PUBLISHED', current_version_id: FRESH }) as never;
      }
      return versionDetail() as never;
    });

    const user = await editedEditor();
    await user.click(await screen.findByRole('button', { name: /^Publish version/ }));
    await user.type(screen.getByRole('textbox', { name: /What changed/i }), 'Widened description');
    await user.click(screen.getByRole('button', { name: 'Publish' }));

    await waitFor(() => expect(seen).toHaveLength(2));
    expect(seen[0]).toBe(`POST /v1/companies/${COMPANY}/templates/${TEMPLATE}/versions`);
    // The id that was just created, never "the newest" — two editors publishing at once must
    // not make one of them live the other's version.
    expect(seen[1]).toBe(
      `POST /v1/companies/${COMPANY}/templates/${TEMPLATE}/versions/${FRESH}/publish`,
    );
  });

  it('refuses a publish the service did not confirm as live', async () => {
    const answer = reads();
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
      const read = answer(request);
      if (read) return read as never;
      if (request.path.endsWith('/publish')) {
        // The response says a *different* version is live. Accepting it would tell the reader
        // their layout is what customers receive when it is not.
        return detail({ status: 'PUBLISHED', current_version_id: VERSION }) as never;
      }
      return versionDetail() as never;
    });

    const user = await editedEditor();
    await user.click(await screen.findByRole('button', { name: /^Publish version/ }));
    await user.type(screen.getByRole('textbox', { name: /What changed/i }), 'Widened description');
    await user.click(screen.getByRole('button', { name: 'Publish' }));

    expect(await screen.findByText(/did not confirm this version as the live one/)).toBeInTheDocument();
  });

  it('keeps the dialog and the typed summary when the save fails', async () => {
    const answer = reads();
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
      const read = answer(request);
      if (read) return read as never;
      throw { status: 422, message: 'The layout does not fit the paper this template prints on' };
    });

    const user = await editedEditor();
    await user.click(await screen.findByRole('button', { name: /^Publish version/ }));
    const field = screen.getByRole('textbox', { name: /What changed/i });
    await user.type(field, 'Widened description');
    await user.click(screen.getByRole('button', { name: 'Publish' }));

    expect(await screen.findByText(/does not fit the paper/)).toBeInTheDocument();
    // Still open, still holding what was typed — a closed dialog here loses the layout.
    expect(screen.getByRole('textbox', { name: /What changed/i })).toHaveValue('Widened description');
  });

  it('insists on a summary, because a history of blanks is not a history', async () => {
    const answer = reads();
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
      const read = answer(request);
      if (read) return read as never;
      return versionDetail() as never;
    });

    const user = await editedEditor();
    await user.click(await screen.findByRole('button', { name: /^Publish version/ }));
    await user.click(screen.getByRole('button', { name: 'Publish' }));

    expect(await screen.findByText(/Say what changed/)).toBeInTheDocument();
    expect(writes()).toHaveLength(0);
  });

  it('says so when a 5xx leaves the outcome unknown, and keeps the same key for the retry', async () => {
    const answer = reads();
    let attempts = 0;
    const bodies: unknown[] = [];
    const keys: (string | undefined)[] = [];
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
      const read = answer(request);
      if (read) return read as never;
      bodies.push(request.body);
      keys.push(request.key);
      if (attempts++ === 0) throw { status: 503, message: 'The design service is unavailable.' };
      if (request.path.endsWith('/publish')) {
        return detail({ status: 'PUBLISHED', current_version_id: FRESH }) as never;
      }
      return versionDetail() as never;
    });

    const user = await editedEditor();
    await user.click(await screen.findByRole('button', { name: /^Publish version/ }));
    await user.type(screen.getByRole('textbox', { name: /What changed/i }), 'Widened description');
    await user.click(screen.getByRole('button', { name: 'Publish' }));

    expect(await screen.findByText(/did not confirm/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Publish' }));
    await waitFor(() => expect(bodies.length).toBeGreaterThanOrEqual(2));
    // The identical request, under the identical key: a retried save must not become a
    // second version if the first one actually landed (CLAUDE.md §6.2's reasoning).
    expect(JSON.stringify(bodies[1])).toBe(JSON.stringify(bodies[0]));
    expect(keys[1]).toBe(keys[0]);
  });
});

describe('a template Purchase prints on', () => {
  const rule = (overrides: Record<string, unknown> = {}) => ({
    id: '01990000-0000-7000-8000-0000000000a1', company_id: COMPANY, voucher_kind: 'PURCHASE', template_id: TEMPLATE,
    priority: 0, is_active: true, created_at: '2026-11-03T00:00:00Z', ...overrides,
  });

  it('is checked against what Purchase prints, because an active Purchase rule points at it', async () => {
    const answer = reads({ assignments: [rule()] });
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => (answer(request) ?? versionDetail()) as never);
    mount(<DesignerRoute company={COMPANY} templateId={TEMPLATE} canManage />);
    expect((await screen.findAllByText(/Purchase printing does not support/)).length).toBeGreaterThan(0);
  });

  it('is checked for Purchase from the first edit when it was made for Purchase, routed or not', async () => {
    const answer = reads({ template: detail({ voucher_kind: 'PURCHASE', line_profile: 'ACCOUNTS' }) });
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => (answer(request) ?? versionDetail()) as never);
    mount(<DesignerRoute company={COMPANY} templateId={TEMPLATE} canManage />);
    expect((await screen.findAllByText(/Purchase printing does not support/)).length).toBeGreaterThan(0);
    expect(screen.getByText(/Purchase · Accounts and expenses/)).toBeInTheDocument();
  });

  it('says plainly when its kind cannot be printed from a design yet', async () => {
    const answer = reads({ template: detail({ voucher_kind: 'SALES', line_profile: 'ITEMS' }) });
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => (answer(request) ?? versionDetail()) as never);
    mount(<DesignerRoute company={COMPANY} templateId={TEMPLATE} canManage />);
    expect(await screen.findByText(/Sales vouchers cannot be printed from a design yet/)).toBeInTheDocument();
    expect(screen.queryByText(/printing does not support/)).toBeNull();
  });

  it('is not, when the only Purchase rule for it is retired', async () => {
    const answer = reads({ assignments: [rule({ is_active: false })] });
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => (answer(request) ?? versionDetail()) as never);
    mount(<DesignerRoute company={COMPANY} templateId={TEMPLATE} canManage />);
    await screen.findAllByText(/GST tax invoice/);
    expect(screen.queryByText(/Purchase printing does not support/)).toBeNull();
  });
});

describe('a reader who may look but not change', () => {
  it('opens the design read-only and offers no save', async () => {
    const answer = reads();
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
      const read = answer(request);
      if (read) return read as never;
      throw new Error('a read-only editor must not write');
    });

    mount(<DesignerRoute company={COMPANY} templateId={TEMPLATE} canManage={false} />);

    expect(await screen.findAllByText(/not permission to change it/)).not.toHaveLength(0);
    expect(screen.queryByRole('button', { name: /Save version .* as a draft/ })).not.toBeInTheDocument();
  });
});

describe('starting a template', () => {
  it('creates an empty draft and opens it, sending no canvas', async () => {
    vi.mocked(serviceCall).mockResolvedValue({ ...detail({ id: FRESH }), initial_version_id: null } as never);
    const user = userEvent.setup();
    mount(<NewTemplateDialog company={COMPANY} open onClose={() => {}} />);

    await user.type(screen.getByRole('textbox', { name: /Name/ }), 'Delivery challan');
    await user.type(screen.getByRole('textbox', { name: /Code/ }), 'challan-a4');
    await user.click(screen.getByRole('button', { name: /Create and open/ }));

    await waitFor(() => expect(writes()).toHaveLength(1));
    const [[, request]] = writes();
    expect(request.path).toBe(`/v1/companies/${COMPANY}/templates`);
    expect(request.body).toEqual({
      name: 'Delivery challan',
      code: 'challan-a4',
      paper_size: 'A4',
      page_orientation: 'PORTRAIT',
    });
    // No `initial_canvas`: a create form knows a name, a code and some paper, not a design.
    expect(request.body).not.toHaveProperty('initial_canvas');
    await waitFor(() => expect(goTo).toHaveBeenCalledWith('/invoice-designer/' + FRESH));
  });

  it('records what a design started from Voucher print is for: its kind and its lines', async () => {
    vi.mocked(serviceCall).mockResolvedValue({ ...detail({ id: FRESH }), initial_version_id: null } as never);
    const user = userEvent.setup();
    mount(<NewTemplateDialog company={COMPANY} open onClose={() => {}} kind="PURCHASE" />);
    expect(screen.getByRole('textbox', { name: /Prints/ })).toHaveValue('Purchase');
    expect(screen.getByRole('combobox', { name: /Lines/ })).toHaveValue('ITEMS');
    await user.selectOptions(screen.getByRole('combobox', { name: /Lines/ }), 'MIXED');
    await user.type(screen.getByRole('textbox', { name: /Name/ }), 'Supplier bill');
    await user.type(screen.getByRole('textbox', { name: /Code/ }), 'supplier-bill');
    await user.click(screen.getByRole('button', { name: /Create and open/ }));
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0]![1].body).toMatchObject({ voucher_kind: 'PURCHASE', line_profile: 'MIXED' });
  });

  it('lets a design from the gallery stay open to any voucher, or name one', async () => {
    vi.mocked(serviceCall).mockResolvedValue({ ...detail({ id: FRESH }), initial_version_id: null } as never);
    const user = userEvent.setup();
    mount(<NewTemplateDialog company={COMPANY} open onClose={() => {}} />);
    expect(screen.queryByRole('combobox', { name: /Lines/ })).toBeNull();
    await user.selectOptions(screen.getByRole('combobox', { name: /Prints/ }), 'PAYMENT');
    // A payment's lines are accounts, so that is where it starts.
    expect(screen.getByRole('combobox', { name: /Lines/ })).toHaveValue('ACCOUNTS');
    await user.type(screen.getByRole('textbox', { name: /Name/ }), 'Payment advice');
    await user.type(screen.getByRole('textbox', { name: /Code/ }), 'payment-advice');
    await user.click(screen.getByRole('button', { name: /Create and open/ }));
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0]![1].body).toMatchObject({ voucher_kind: 'PAYMENT', line_profile: 'ACCOUNTS' });
  });

  it('refuses a code the service would reject, before the round trip', async () => {
    vi.mocked(serviceCall).mockResolvedValue(detail() as never);
    const user = userEvent.setup();
    mount(<NewTemplateDialog company={COMPANY} open onClose={() => {}} />);

    await user.type(screen.getByRole('textbox', { name: /Name/ }), 'Delivery challan');
    await user.type(screen.getByRole('textbox', { name: /Code/ }), 'not a code!');
    await user.click(screen.getByRole('button', { name: /Create and open/ }));

    expect(await screen.findByText(/Letters, digits, hyphen and underscore/)).toBeInTheDocument();
    expect(writes()).toHaveLength(0);
  });

  it('sends a custom page size as a decimal string, never a float', async () => {
    vi.mocked(serviceCall).mockResolvedValue(detail({ id: FRESH }) as never);
    const user = userEvent.setup();
    mount(<NewTemplateDialog company={COMPANY} open onClose={() => {}} />);

    await user.type(screen.getByRole('textbox', { name: /Name/ }), 'Label');
    await user.type(screen.getByRole('textbox', { name: /Code/ }), 'label-100');
    await user.selectOptions(screen.getByRole('combobox', { name: /Paper/ }), 'CUSTOM');
    await user.type(screen.getByRole('textbox', { name: /Width/ }), '100.5');
    await user.type(screen.getByRole('textbox', { name: /Height/ }), '75');
    await user.click(screen.getByRole('button', { name: /Create and open/ }));

    await waitFor(() => expect(writes()).toHaveLength(1));
    const body = writes()[0]![1].body as Record<string, unknown>;
    // A `DECIMAL(19,4)` column: a float round trip silently re-scales a page size.
    expect(body.page_width_mm).toBe('100.5');
    expect(typeof body.page_width_mm).toBe('string');
  });

  it('puts a per-field service rejection beside its own input', async () => {
    vi.mocked(serviceCall).mockRejectedValue({
      status: 422,
      message: 'Validation failed',
      fields: { code: 'That code is already used by another template.' },
    });
    const user = userEvent.setup();
    mount(<NewTemplateDialog company={COMPANY} open onClose={() => {}} />);

    await user.type(screen.getByRole('textbox', { name: /Name/ }), 'Delivery challan');
    await user.type(screen.getByRole('textbox', { name: /Code/ }), 'challan-a4');
    await user.click(screen.getByRole('button', { name: /Create and open/ }));

    expect(await screen.findByText(/already used by another template/)).toBeInTheDocument();
    expect(goTo).not.toHaveBeenCalled();
  });
});
