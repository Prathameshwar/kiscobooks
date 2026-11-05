'use client';

import { useEffect, useState } from 'react';
import {
  Badge,
  Card,
  CardHeader,
  DataTable,
  FilterBar,
  Notice,
  PageHeader,
  Pager,
  TableSearch,
  asErrorStatus,
  useListQuery,
  type Column,
  type PageMeta,
} from '@janso/ui';
import { companyCall, companyFailure, openCompany, type CompanyFailure } from '../lib/company-api';
import { companyPermission } from '../lib/company-permissions';
import type { Session } from '../session';
import {
  SEARCH_MIN,
  SWITCHER_LIMIT,
  companyChoices,
  sessionCompanyListPath,
  type CompanyChoice,
  type SessionCompanyPage,
} from '../lib/company-list';

type Row = CompanyChoice & { isOpen: boolean };

const columns: readonly Column<Row>[] = [
  { key: 'code', header: 'Code', type: 'code', locked: true },
  { key: 'name', header: 'Company', truncate: true },
  {
    key: 'context',
    header: 'Context',
    type: 'custom',
    render: (row) => (
      <>
        {row.isOpen ? <Badge tone="success">Open</Badge> : null}
        {row.isDefault ? <Badge tone="brand" variant="outline">Default</Badge> : null}
        {row.requiresStepUp ? <Badge tone="warn" variant="outline">Verify</Badge> : null}
      </>
    ),
  },
];

/**
 * The company directory: which companies this actor can open, and which one is open now.
 *
 * Reads the same self-read list as the rail (`/v1/session/companies`), so a clerk who may work
 * in three companies sees three rows here too — without `company.read`, which would hand them
 * every company's details to answer a question about their own access.
 *
 * Opening one goes through `openCompany`, the same path the rail's switcher uses — there is
 * exactly one way company context changes, including the step-up hand-off.
 *
 * The list is keyset-paged like every other growing list (api-conventions §2.1): the
 * server-rendered first page is what the rail already fetched, and the pager walks from there.
 */
export function Companies({
  companies,
  note,
  openCompanyId,
  canCreate,
  canManage = false,
  grants,
  initialPage,
}: {
  companies: readonly CompanyChoice[];
  note: string | null;
  openCompanyId: string | undefined;
  canCreate: boolean;
  canManage?: boolean;
  grants?: Session['grants'];
  initialPage?: PageMeta;
}) {
  const [rows, setRows] = useState<readonly CompanyChoice[]>(companies);
  // The page meta of the rows in hand — `limit` included, because the pager reports the walk
  // against the size that was actually requested, not against whatever is selected now.
  const [meta, setMeta] = useState<PageMeta>(initialPage ?? { has_more: false, next_cursor: null, limit: SWITCHER_LIMIT });
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadFailure, setLoadFailure] = useState<CompanyFailure | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [opening, setOpening] = useState<string | null>(null);
  const query = useListQuery({ meta: loading ? null : meta });

  useEffect(() => {
    // The first page with no search is already in hand from the server render.
    if (!revision && !query.q && !query.cursor && query.limit === SWITCHER_LIMIT) {
      setRows(companies);
      setMeta(initialPage ?? { has_more: false, next_cursor: null, limit: SWITCHER_LIMIT });
      setLoadFailure(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setLoadFailure(null);
    companyCall<SessionCompanyPage>(
      'identity',
      sessionCompanyListPath({ q: query.q || undefined, limit: query.limit, cursor: query.cursor }),
      { signal: controller.signal },
    )
      .then((page) => {
        if (controller.signal.aborted) return;
        setRows(companyChoices(page));
        setMeta({ ...page.page, limit: query.limit });
        setLoading(false);
      })
      .catch((value) => {
        if (controller.signal.aborted) return;
        setRows([]);
        setLoadFailure(companyFailure(value));
        setLoading(false);
      });
    return () => controller.abort();
    // The query's identity is its search, its page size and its cursor; `companies` is the
    // server-rendered page the unsearched first page falls back to.
  }, [companies, initialPage, query.q, query.limit, query.cursor, revision]);

  async function open(id: string): Promise<void> {
    setOpening(id);
    setFailure(null);
    const refused = await openCompany(id);
    if (!refused) return;
    setFailure(refused.message);
    setOpening(null);
  }

  const data: Row[] = rows.map((item) => ({ ...item, isOpen: item.id === openCompanyId }));
  const create = (
    <a className="janso-btn janso-btn--primary" href="/companies/new">
      Create company
    </a>
  );

  return (
    <div className="janso-page">
      <PageHeader
        title="Companies"
        lede="The companies you can open. The one you open decides what every other screen shows."
        actions={<>{canManage && <a className="janso-btn janso-btn--ghost" href="/companies/manage">Manage companies</a>}{canCreate ? create : null}</>}
      />
      {failure ? <Notice tone="danger">{failure}</Notice> : null}
      <Card>
        <CardHeader title="Company directory" subtitle="Open a company to work in it. Every screen then reads that company's data." />
        <FilterBar
          applied={query.q ? [{ id: 'q', label: 'Search', value: query.q }] : []}
          onRemove={() => query.setSearch('')}
          onClearAll={query.clearFilters}
        >
          <TableSearch
            value={query.q}
            onChange={query.setSearch}
            minLength={SEARCH_MIN}
            maxLength={100}
            label="Search companies"
            placeholder="Search company"
            hint="code, trading name or legal name"
            busy={loading}
          />
        </FilterBar>
        <DataTable
          caption="Companies you can open"
          columns={columns}
          rows={data}
          rowId={(row) => row.id}
          rowLabel={(row) => row.name}
          loading={loading}
          error={loadFailure ? asErrorStatus(loadFailure.status) : null}
          errorDetail={loadFailure?.message}
          onRetry={loadFailure?.status === 403 ? undefined : () => setRevision(value => value + 1)}
          filtered={query.filtered}
          emptyTitle={query.q ? 'No company matches that search' : 'No company yet'}
          emptyBody={query.q ? 'Try a different code or name.' : note ?? undefined}
          emptyAction={
            canCreate && !query.q ? (
              <a className="janso-btn janso-btn--primary" href="/companies/new">
                Create the first company
              </a>
            ) : undefined
          }
          onClearFilters={query.clearFilters}
          rowActions={(row) => [
            ...(row.isOpen
              ? [{ id: 'open', label: 'Already open', disabledReason: 'This is the company you are working in' }]
              : [{ id: 'open', label: opening === row.id ? 'Opening…' : 'Open this company', disabledReason: opening ? 'A company change is in progress' : undefined }]),
            ...(companyPermission({ grants }, 'company.read', row.id) ? [{ id: 'view', label: 'View company', href: '/companies/' + row.id }] : []),
            ...(companyPermission({ grants }, 'company.read', row.id) && companyPermission({ grants }, 'company.update', row.id)
              ? [{ id: 'edit', label: 'Edit company', href: '/companies/' + row.id + '/edit' }] : []),
            ...(companyPermission({ grants }, 'period.read', row.id) ? [{ id: 'years', label: 'Manage years', href: '/companies/' + row.id + '/years' }] : []),
          ]}
          onAction={(id, row) => {
            if (id === 'open') void open(row.id);
          }}
        />
        <Pager
          noun="company"
          nounPlural="companies"
          count={data.length}
          from={query.page.from}
          limit={query.limit}
          hasPrevious={query.page.hasPrevious}
          hasNext={!loadFailure && query.page.hasNext}
          onPrevious={query.previousPage}
          onNext={query.nextPage}
          onLimitChange={query.setLimit}
          busy={loading}
        />
      </Card>
    </div>
  );
}
