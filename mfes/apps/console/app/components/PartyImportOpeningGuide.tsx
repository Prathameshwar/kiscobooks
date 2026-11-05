'use client';
import { Notice, SectionHeader } from '@janso/ui';
import { base, blockerLabel, owned, request, type Readiness } from '../lib/financial-opening';
import { useServiceRead } from '../lib/service-resource';

/** Once any of these hold, no opening declaration can take a new balance. */
const CLOSED = ['OPENING_ALREADY_FINALIZED', 'LEGACY_ACTIVITY_REQUIRES_REVIEW', 'FINANCIAL_SETUP_NOT_INITIALIZED', 'ACCOUNTING_NOT_INITIALIZED', 'LATER_BOOKS_CLOSED'];

/** What the optional opening columns of a supplier or customer file do, and whether they can be used now. */
export function PartyImportOpeningGuide({ company }: { company: string }) {
  const ready = useServiceRead<Readiness>(base(company) + '/readiness', request, owned(company));
  const closed = ready.data?.blockers.filter(code => CLOSED.includes(code)) ?? [];
  return <div className="janso-flow">
    <SectionHeader title="Optional opening balances" />
    <p className="janso-fine">Bring in what a supplier or customer owes in the same row. Fill Opening balance type and Opening amount; leave every opening column empty for no balance.</p>
    <p className="janso-fine">DR or TO_RECEIVE is a debit balance: they owe you. CR or TO_PAY is a credit balance: you owe them.</p>
    <p className="janso-fine">Add Bill reference, Bill date and Bill due date to record one dated bill. Leave them empty to hold the balance on account, with dates unknown.</p>
    <p className="janso-fine">For another currency, also fill Opening currency, Opening exchange rate and Opening base amount.</p>
    <p className="janso-fine">A ledger account is created for the party. Its code is the party code unless you set Ledger account code.</p>
    <p className="janso-fine">Nothing is posted. The balances are held for <a className="janso-link" href="/accounting/opening">Account and party openings</a>, where you add them to the opening worksheet and balance them against your other accounts.</p>
    {closed.length > 0 && <Notice tone="warning"><span role="status">Opening balances cannot be added now, so rows with opening columns will be rejected. {closed.map(blockerLabel).join(' ')}</span></Notice>}
  </div>;
}
