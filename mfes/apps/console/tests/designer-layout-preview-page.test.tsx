/**
 * The layout preview page (plan R4): who may open it, what it reads, and what it names.
 *
 * The page names the design and its version from the design service, never from the link; it
 * needs design read access on top of the Purchase print rights, as Vouchers does.
 */
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { pageContext } from '../app/lib/page-context';
import { serviceCall, type ServiceRequest } from '../app/lib/service-call';
import { companyContextFor, sessionFor } from './helpers';
import Page from '../app/(editor)/invoice-designer/[templateId]/preview/page';
import { LayoutPreviewRoute } from '../app/(editor)/invoice-designer/LayoutPreviewRoute';

vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/PurchasePrintPreview', () => ({ PurchasePrintPreview: (props: unknown) => <p>Preview {JSON.stringify(props)}</p> }));
vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));

const COMPANY = '01990000-0000-7000-8000-000000000001';
const TEMPLATE = '01990000-0000-7000-8000-0000000000d1';
const VERSION = '01990000-0000-7000-8000-0000000000d2';
const BILL = '01990000-0000-7000-8000-0000000000c1';
const REVISION = '01990000-0000-7000-8000-0000000000c2';
const PRINT = ['vouchers.read', 'vouchers.artifact.create', 'vouchers.artifact.read', 'accounting.account.read'];
const ALL = [...PRINT, 'design.template.read'];

async function setup(permissions = ALL, scope = COMPANY) {
  const session = await sessionFor({ permissions });
  session.company = { id: COMPANY, name: 'Print company' };
  session.grants = [{ scope_type: 'company', scope_id: scope, permissions, valid_from: '2020-01-01', valid_to: null }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
}
const query = { design_version: VERSION, voucher: BILL, revision: REVISION, version: '3' };
const props = (search: Record<string, string> = query) => ({ params: Promise.resolve({ templateId: TEMPLATE }), searchParams: Promise.resolve(search) });

function design(options: { template?: Record<string, unknown>; version?: Record<string, unknown>; failure?: { status: number; message: string } } = {}) {
  return async (_endpoint: string, request: ServiceRequest) => {
    if (options.failure) throw options.failure;
    if (request.path.endsWith(`/versions/${VERSION}`)) {
      return { id: VERSION, template_id: TEMPLATE, version_number: 2, schema_version: '1.1.0', created_at: '2026-11-04T00:00:00Z', ...options.version } as never;
    }
    if (request.path.endsWith(`/templates/${TEMPLATE}`)) {
      return { id: TEMPLATE, company_id: COMPANY, name: 'Our purchase bill', code: 'our', voucher_kind: 'PURCHASE', paper_size: 'A4', page_orientation: 'PORTRAIT', status: 'DRAFT', is_system: false, ...options.template } as never;
    }
    throw new Error('unexpected ' + request.path);
  };
}

beforeEach(() => {
  vi.mocked(serviceCall).mockReset();
  vi.mocked(serviceCall).mockImplementation(design());
});

describe('the page', () => {
  it('opens the preview for one design version on one saved revision, under the selected company', async () => {
    await setup();
    render(await Page(props()));
    expect(await screen.findByText(/^Preview /)).toHaveTextContent(JSON.stringify({
      company: COMPANY, voucherId: BILL, revisionId: REVISION, version: 3,
      layoutPreview: { templateId: TEMPLATE, versionId: VERSION, templateName: 'Our purchase bill', versionNumber: 2 },
    }));
  });

  it('refuses a reader without design read access, saying which right is missing', async () => {
    await setup(PRINT);
    render(await Page(props()));
    expect(screen.getByText('You need permission to read designs to preview a layout with a saved bill.')).toBeInTheDocument();
    expect(serviceCall).not.toHaveBeenCalled();
  });

  it.each(PRINT)('requires %s as well as the other print rights', async (missing) => {
    await setup(ALL.filter((key) => key !== missing));
    render(await Page(props()));
    expect(screen.getByText('Previewing with a saved bill needs permission to read and print Purchase bills.')).toBeInTheDocument();
    expect(screen.queryByText(/^Preview /)).toBeNull();
  });

  it('refuses another company’s grant', async () => {
    await setup(ALL, '01990000-0000-7000-8000-000000000009');
    render(await Page(props()));
    expect(screen.queryByText(/^Preview /)).toBeNull();
  });

  it.each([
    ['a missing version', { ...query, design_version: '' }],
    ['a malformed bill', { ...query, voucher: '../etc' }],
    ['a zero row version', { ...query, version: '0' }],
  ])('says the link is incomplete for %s', async (_, search) => {
    await setup();
    render(await Page(props(search as Record<string, string>)));
    expect(screen.getByText(/this preview link is incomplete/)).toBeInTheDocument();
    expect(serviceCall).not.toHaveBeenCalled();
  });

  it('is a 404 for a template id that is not one', async () => {
    await setup();
    await expect(Page({ params: Promise.resolve({ templateId: 'nope' }), searchParams: Promise.resolve(query) })).rejects.toThrow();
  });
});

describe('what the preview reads', () => {
  const route = () =>
    render(<LayoutPreviewRoute company={COMPANY} templateId={TEMPLATE} designVersionId={VERSION} voucherId={BILL} revisionId={REVISION} version={3} />);

  it('waits for the design before printing anything', () => {
    vi.mocked(serviceCall).mockImplementation(() => new Promise(() => undefined));
    route();
    expect(screen.queryByText(/^Preview /)).toBeNull();
    expect(screen.getByRole('link', { name: /designer/i })).toHaveAttribute('href', `/invoice-designer/${TEMPLATE}`);
  });

  it('says a 403 as the design read right, and leads back to the designer', async () => {
    vi.mocked(serviceCall).mockImplementation(design({ failure: { status: 403, message: 'denied' } }));
    route();
    expect(await screen.findByText('You need permission to read designs to preview a layout with a saved bill.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /designer/i })).toHaveAttribute('href', `/invoice-designer/${TEMPLATE}`);
  });

  it('says a 404 as a 403, so a design’s existence is not an oracle', async () => {
    vi.mocked(serviceCall).mockImplementation(design({ failure: { status: 404, message: 'template not found' } }));
    route();
    expect(await screen.findByText('template not found')).toBeInTheDocument();
    expect(screen.queryByText(/^Preview /)).toBeNull();
  });

  it('refuses a version of another design', async () => {
    vi.mocked(serviceCall).mockImplementation(design({ version: { template_id: '01990000-0000-7000-8000-0000000000ee' } }));
    route();
    expect(await screen.findByText('The design version did not match this design. Reload before continuing.')).toBeInTheDocument();
  });

  it('refuses another company’s design', async () => {
    vi.mocked(serviceCall).mockImplementation(design({ template: { company_id: '01990000-0000-7000-8000-0000000000ef' } }));
    route();
    expect(await screen.findByText(/did not match this company/)).toBeInTheDocument();
  });

  it('does not preview a design for another kind on a Purchase bill', async () => {
    vi.mocked(serviceCall).mockImplementation(design({ template: { voucher_kind: 'SALES' } }));
    route();
    expect(await screen.findByText('Only a design for Purchase, or for any voucher, can be previewed with a Purchase bill.')).toBeInTheDocument();
  });

  it('previews a design for any voucher', async () => {
    vi.mocked(serviceCall).mockImplementation(design({ template: { voucher_kind: null } }));
    route();
    expect(await screen.findByText(/^Preview /)).toHaveTextContent('"versionNumber":2');
  });
});
