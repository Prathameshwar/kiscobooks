'use client';
import { useState } from 'react';
import { Notice, SearchSelect, TextField } from '@janso/ui';
import { lookup } from '../lib/voucher-fields';
import { accountingRequest } from '../lib/accounting-configuration';
import { useServiceRead } from '../lib/service-resource';
import { owned } from '../lib/financial-opening';
import { verifyOpeningDefault, type OpeningDefaultAccount } from '../lib/financial-opening-defaults';

export function FinancialOpeningDefaults({ company, automatic, offset, disabled, onBusy, onOffset }: {
  company: string; automatic: boolean; offset: string | null; disabled: boolean; onBusy: (busy: boolean) => void; onOffset: (id: string | null) => void;
}) {
  const [error, setError] = useState(''), [checking, setChecking] = useState(false);
  const root = `/v1/companies/${company}`;
  const read = useServiceRead<OpeningDefaultAccount>(offset ? root + '/accounts/' + offset : undefined, accountingRequest, row => {
    owned(company)(row); if (row.id !== offset) throw { status: 502, message: 'The configured opening offset could not be verified.' };
  });
  async function select(id: string | null) {
    if (!id) { onOffset(null); return; }
    setChecking(true); onBusy(true); setError('');
    try {
      const account = await accountingRequest<OpeningDefaultAccount>({ path: root + '/accounts/' + id });
      if (account.id !== id) throw new Error('The selected offset account could not be verified.');
      await verifyOpeningDefault(root, account, 'offset'); onOffset(id);
    } catch (failure) { setError(failure && typeof failure === 'object' && 'message' in failure ? String(failure.message) : 'The offset account could not be verified.'); }
    finally { setChecking(false); onBusy(false); }
  }
  return <>
    {automatic ? <TextField label="Opening-balance offset account" value={read.loading ? 'Loading…' : read.data?.name ?? read.data?.code ?? (offset ? 'Account unavailable' : 'Not configured')} readOnly /> :
      <SearchSelect label="Opening-balance offset account" hint="An equity account for the difference between entered Dr and Cr balances." scopeKey={company + ':opening-offset'} value={offset} selected={read.data ? { id: read.data.id, label: read.data.name ?? read.data.code ?? 'Selected offset' } : undefined} loadOptions={lookup(company, 'accounts')} disabled={disabled || checking} onChange={id => void select(id)} />}
    {(error || read.failure) && <Notice tone="danger"><span role="alert">{error || read.failure?.message}</span></Notice>}
  </>;
}
