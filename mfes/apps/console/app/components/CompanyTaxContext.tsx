'use client';

import { useEffect, useState } from 'react';
import type { components } from '@janso/api-client/identity';
import { Button, Card, CardBody, CardHeader, DataTable, ErrorState, Notice, ReviewList, Skeleton, Toolbar, asErrorStatus } from '@janso/ui';
import { companyCall, companyFailure, type CompanyFailure } from '../lib/company-api';
import { taxSystemLabel } from '../lib/company-labels';

type Page = components['schemas']['Page_TaxRegistrationItem_'];

/** Non-India-GST registration facts, using the same scoped statutory read contract. */
export function CompanyTaxContext({ company, taxSystem }: { company: string; taxSystem?: string }) {
  const [page, setPage] = useState<Page | null>(null);
  const [cursor, setCursor] = useState<string | undefined>();
  const [failure, setFailure] = useState<CompanyFailure | null>(null);
  const [loading, setLoading] = useState(false), [revision, setRevision] = useState(0);
  useEffect(() => {
    const abort = new AbortController(); setPage(null); setFailure(null); setLoading(!!taxSystem);
    if (taxSystem) void companyCall<Page>('identity', '/v1/companies/' + company + '/tax-registrations?limit=50' + (cursor ? '&cursor=' + encodeURIComponent(cursor) : ''), { signal: abort.signal })
      .then(value => {
        if (abort.signal.aborted) return;
        if (!Array.isArray(value.items) || !value.page) throw new Error('Tax registration response could not be verified.');
        setPage(value); setLoading(false);
      }).catch(error => { if (!abort.signal.aborted) { setFailure(companyFailure(error)); setLoading(false); } });
    return () => abort.abort();
  }, [company, taxSystem, cursor, revision]);
  const none = taxSystem === 'none', vat = taxSystem?.startsWith('vat_');
  return <section aria-label="Tax registration and applicability">
    <Card>
      <CardHeader title="Tax registration and applicability" subtitle="The default framework and your dated registrations are separate settings." />
      <CardBody><div className="janso-flow">
        <ReviewList items={[{ label: 'Default tax framework', value: none ? 'No indirect tax registration' : taxSystem ? taxSystemLabel(taxSystem) : 'Not readable' }]} />
        <p className="janso-meta">A company default does not establish registration status or determine tax on every transaction. Saved registrations retain their regime and effective dates.</p>
        {!taxSystem ? <Notice>The tax default is not readable with your current field access.</Notice> : <>
          {none && <Notice>No indirect-tax framework is selected by this default. Existing registration history, if any, is shown below. A missing registration does not certify exemption from tax.</Notice>}
          {vat && <Notice>These are VAT registration records. GSTIN, Rule 14A and GSTR-1/GSTR-3B settings apply to India GST. VAT registration editing is not yet available on this page.</Notice>}
          {loading ? <div role="status" aria-label="Loading tax registrations"><Skeleton /></div> : failure ? <ErrorState status={asErrorStatus(failure.status)} detail={failure.message} action={![401, 403].includes(failure.status) ? <Button onClick={() => setRevision(value => value + 1)}>Reload tax registrations</Button> : undefined} /> : page && <>
            <DataTable caption="Company tax registrations" rows={page.items} rowId={row => row.id} emptyTitle="No saved tax registrations" emptyBody="No registration records were returned. This does not establish whether the business is legally required to register." columns={[
              { key: 'tax_system', header: 'Tax framework', type: 'custom', render: row => taxSystemLabel(row.tax_system) },
              { key: 'number', header: 'Registration number', type: 'text' },
              { key: 'jurisdiction_code', header: 'Jurisdiction', type: 'text' },
              { key: 'regime', header: 'Regime', type: 'custom', render: row => row.regime.replaceAll('_', ' ') },
              { key: 'valid_from', header: 'Valid from', type: 'date' },
              { key: 'valid_to', header: 'Valid to', type: 'date' },
            ]} />
            <Toolbar right={<><Button variant="ghost" onClick={() => { setCursor(undefined); setRevision(value => value + 1); }}>First tax registration page</Button><Button variant="ghost" disabled={!page.page.next_cursor} onClick={() => setCursor(page.page.next_cursor!)}>Next tax registration page</Button></>} />
          </>}
        </>}
      </div></CardBody>
    </Card>
  </section>;
}
