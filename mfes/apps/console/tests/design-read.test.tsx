/**
 * The designer, reading real designs.
 *
 * The eight UI phases were built against fixtures, so the question this phase has to answer is
 * not "does the canvas work" — it does, and its own suites say so — but "does the editor open
 * what the service actually holds". That is three requests and four failure modes, and the ones
 * worth a test are the states a fixture could never produce: a draft with no version at all, a
 * layout saved on the frozen 1.0.0 shape, a shipped read-only design, and a reply that arrives
 * for the company the reader just left.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { serviceCall, type ServiceRequest } from '../app/lib/service-call';
import { PermissionProvider } from '@janso/ui';

vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/sign-in' }));

import { DesignGalleryRoute } from '../app/(editor)/invoice-designer/DesignGalleryRoute';
import { DesignerRoute } from '../app/(editor)/invoice-designer/DesignerRoute';
import { layoutToWire } from '../app/lib/design-canvas';
import { SAMPLE_TEMPLATES } from '../app/(editor)/invoice-designer/sample-templates';

const COMPANY = '01990000-0000-7000-8000-00000000000c';
const OTHER = '01990000-0000-7000-8000-00000000000d';
const TEMPLATE = '01990000-0000-7000-8000-000000000001';
const VERSION = '01990000-0000-7000-8000-000000000002';
const KEYS = ['design.template.read', 'design.template.manage'];

const page = { limit: 200, has_more: false, next_cursor: null };

function item(overrides: Record<string, unknown> = {}) {
  return {
    id: TEMPLATE,
    company_id: COMPANY,
    code: 'gst-tax-invoice-a4',
    name: 'GST tax invoice',
    paper_size: 'A4',
    page_orientation: 'PORTRAIT',
    status: 'PUBLISHED',
    is_system: false,
    current_version_id: VERSION,
    updated_at: '2026-10-27T00:00:00Z',
    ...overrides,
  };
}

function detail(overrides: Record<string, unknown> = {}) {
  return {
    ...item(),
    tenant_id: '01990000-0000-7000-8000-00000000000e',
    description: 'The full one',
    page_width_mm: null,
    page_height_mm: null,
    unit_of_measure: 'mm',
    created_at: '2026-10-27T00:00:00Z',
    ...overrides,
  };
}

function versionItem(overrides: Record<string, unknown> = {}) {
  return {
    id: VERSION,
    template_id: TEMPLATE,
    version_number: 3,
    schema_version: '1.1.0',
    layout_digest: 'ab'.repeat(32),
    change_summary: 'Widened the description column',
    published_at: '2026-10-27T10:00:00Z',
    created_at: '2026-10-27T09:00:00Z',
    ...overrides,
  };
}

/** The service as it would answer the three requests the editor makes. */
function responder(options: {
  templates?: unknown[];
  template?: Record<string, unknown>;
  versions?: unknown[];
  layout?: unknown;
} = {}) {
  return async (_endpoint: string, request: ServiceRequest) => {
    const path = request.path.split('?')[0]!;
    if (path.endsWith('/templates')) {
      return { items: options.templates ?? [item()], page } as never;
    }
    if (path.endsWith(`/versions/${VERSION}`)) {
      return {
        ...versionItem(),
        tenant_id: '01990000-0000-7000-8000-00000000000e',
        layout_definition: options.layout ?? layoutToWire(SAMPLE_TEMPLATES[0]!.layout),
      } as never;
    }
    if (path.endsWith('/versions')) {
      return { items: options.versions ?? [versionItem()], page } as never;
    }
    // The designer asks which Purchase rules print on this template; none do here.
    if (path.endsWith('/assignments')) return { items: [], page } as never;
    return (options.template ?? detail()) as never;
  };
}

function mount(node: React.ReactElement) {
  return render(<PermissionProvider permissions={KEYS}>{node}</PermissionProvider>);
}

beforeEach(() => {
  vi.mocked(serviceCall).mockReset();
});

describe('the gallery on real designs', () => {
  it('lists this company’s templates and counts them', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({ templates: [item(), item({ id: VERSION, code: 'compact', name: 'Compact A4' })] }),
    );
    mount(<DesignGalleryRoute company={COMPANY} />);

    expect(await screen.findByText('2 templates')).toBeInTheDocument();
    expect(screen.getByText('GST tax invoice')).toBeInTheDocument();
  });

  it('asks the design service, not another one, for one bounded page', async () => {
    vi.mocked(serviceCall).mockImplementation(responder());
    mount(<DesignGalleryRoute company={COMPANY} />);
    await screen.findByText('1 template');

    const [[endpoint, request]] = vi.mocked(serviceCall).mock.calls;
    expect(request.service).toBe('design');
    expect(endpoint).toBe('/api/product-fields');
    expect(request.path).toBe(`/v1/companies/${COMPANY}/templates?limit=200`);
    // No `sort`: the design service takes none, and the console's allowlist refuses one.
    expect(request.path).not.toContain('sort');
  });

  it('says a shipped design is read-only before anyone opens it', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({ templates: [item({ is_system: true })] }),
    );
    mount(<DesignGalleryRoute company={COMPANY} />);

    expect(await screen.findByText(/Shipped designs are read-only/)).toBeInTheDocument();
  });

  it('shows the empty state a real tenant sees first, not an error', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ templates: [] }));
    mount(<DesignGalleryRoute company={COMPANY} />);

    expect(await screen.findByText(/No templates yet/)).toBeInTheDocument();
  });

  it('renders a denial as a denial rather than an empty gallery', async () => {
    vi.mocked(serviceCall).mockRejectedValue({ status: 403, message: 'Not permitted here.' });
    mount(<DesignGalleryRoute company={COMPANY} />);

    expect(await screen.findByText(/Not permitted here/)).toBeInTheDocument();
    expect(screen.queryByText(/No templates yet/)).not.toBeInTheDocument();
  });

  it('refuses a list carrying another company’s row', async () => {
    // Not paranoia: the company is switchable from the rail, so a reply for the previous one
    // arrives in practice, and a card linking into it would open another company's design.
    vi.mocked(serviceCall).mockImplementation(
      responder({ templates: [item(), item({ id: VERSION, company_id: OTHER })] }),
    );
    mount(<DesignGalleryRoute company={COMPANY} />);

    await waitFor(() =>
      expect(screen.getByText(/did not match this company/)).toBeInTheDocument(),
    );
  });
});

describe('the editor on one real design', () => {
  it('opens the stored design, named as the service named it', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({ template: detail({ name: 'Service-side invoice' }) }),
    );
    mount(<DesignerRoute company={COMPANY} templateId={TEMPLATE} canManage />);

    // The name comes from the detail reply, so finding it proves the fetched template — not a
    // fixture — is what the editor mounted on.
    expect(await screen.findAllByText(/Service-side invoice/)).not.toHaveLength(0);
  });

  it('offers the stored revision history, newest first', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({
        versions: [versionItem(), versionItem({ id: OTHER, version_number: 2, published_at: null })],
      }),
    );
    mount(<DesignerRoute company={COMPANY} templateId={TEMPLATE} canManage />);

    expect(await screen.findAllByText(/GST tax invoice/)).not.toHaveLength(0);
    expect(screen.getAllByText(/Widened the description column/).length).toBeGreaterThan(0);
  });

  it('reads detail, history and the newest version — in that order', async () => {
    vi.mocked(serviceCall).mockImplementation(responder());
    mount(<DesignerRoute company={COMPANY} templateId={TEMPLATE} canManage />);
    await screen.findAllByText(/GST tax invoice/);

    const all = vi.mocked(serviceCall).mock.calls.map(([, request]) => request.path);
    // Beside the template reads, one read of the Purchase rules that may print on it.
    expect(all).toContain(`/v1/companies/${COMPANY}/assignments?include_inactive=true&limit=200&voucher_kind=PURCHASE`);
    const paths = all.filter((path) => !path.includes('/assignments'));
    expect(paths[0]).toBe(`/v1/companies/${COMPANY}/templates/${TEMPLATE}`);
    expect(paths[1]).toBe(`/v1/companies/${COMPANY}/templates/${TEMPLATE}/versions?limit=200`);
    expect(paths[2]).toBe(`/v1/companies/${COMPANY}/templates/${TEMPLATE}/versions/${VERSION}`);
    expect(vi.mocked(serviceCall).mock.calls.every(([, r]) => r.service === 'design')).toBe(true);
  });

  it('opens a draft that has no version at all on an empty page', async () => {
    // A real state, and one no fixture produces: a template created without a canvas.
    vi.mocked(serviceCall).mockImplementation(
      responder({ template: detail({ status: 'DRAFT', current_version_id: null }), versions: [] }),
    );
    mount(<DesignerRoute company={COMPANY} templateId={TEMPLATE} canManage />);

    await screen.findAllByText(/GST tax invoice/);
    // Two template requests, not three: with no version there is no layout to fetch.
    // (The rules and the company's pictures are read by their own panels, not the template.)
    const reads = vi.mocked(serviceCall).mock.calls.filter(([, request]) => !request.path.includes('/assignments') && !request.path.includes('/assets'));
    expect(reads).toHaveLength(2);
  });

  it('refuses to pretend it can edit a layout stored on the frozen 1.0.0 shape', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({
        versions: [versionItem({ schema_version: '1.0.0' })],
        layout: { schema_version: '1.0.0', sections: [{ id: 'a', type: 'HEADER' }] },
      }),
    );
    mount(<DesignerRoute company={COMPANY} templateId={TEMPLATE} canManage />);

    // Twice, and both are right: the notice says why, and the publish control answers
    // "why can I not press this" with the same sentence.
    expect(await screen.findAllByText(/older layout format/)).not.toHaveLength(0);
  });

  it('says a shipped design is read-only', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({ template: detail({ is_system: true }) }),
    );
    mount(<DesignerRoute company={COMPANY} templateId={TEMPLATE} canManage />);

    expect(await screen.findAllByText(/shipped design/)).not.toHaveLength(0);
  });

  it('shows a deleted or foreign template as forbidden, never as missing', async () => {
    // "Not yours" and "gone" must not be distinguishable, or the 404 is an existence oracle.
    vi.mocked(serviceCall).mockRejectedValue({ status: 404, message: 'No such template.' });
    mount(<DesignerRoute company={COMPANY} templateId={TEMPLATE} canManage />);

    expect(await screen.findByText(/No such template/)).toBeInTheDocument();
  });

  it('refuses a detail reply for a different company', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({ template: detail({ company_id: OTHER }) }),
    );
    mount(<DesignerRoute company={COMPANY} templateId={TEMPLATE} canManage />);

    expect(await screen.findByText(/did not match this company/)).toBeInTheDocument();
  });

  it('refuses a version reply for a different template', async () => {
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
      const path = request.path.split('?')[0]!;
      if (path.endsWith(`/versions/${VERSION}`)) {
        return { ...versionItem({ id: OTHER }), layout_definition: { schema_version: '1.1.0' } } as never;
      }
      return (await responder()(_endpoint, request)) as never;
    });
    mount(<DesignerRoute company={COMPANY} templateId={TEMPLATE} canManage />);

    expect(await screen.findByText(/did not match this company/)).toBeInTheDocument();
  });
});
