'use client';

import { useCallback, useMemo } from 'react';
import { businessToday, useDisplayConfig, type SearchSelectLoader } from '@janso/ui';
import { SAMPLE_SALES_POLICY, type EntryMode } from '../lib/sales-entry-policy';
import type { SubjectResolver } from '../lib/sales-entry-columns';
import type { CustomerCredit } from '../lib/sales-entry-draft';
import * as D from '../lib/fixed-decimal';
import { SalesEntryPage } from './SalesEntryPage';
import type { AdvanceLoader, OpenAdvance } from './SalesSettlementDrawer';

/**
 * **The fixture-backed sales bill** — the page on static data, kept as the test double and the
 * design harness. The route renders `SalesEntryConnected`, which resolves the same props from
 * the services; this file is what the page's own tests and the browser review run against.
 *
 * What the sales form resolves against, for this phase.
 *
 * The seam, and the only place that knows the data is not real. The policy is a fixture, the
 * customer lookup answers from a local list, and `today` is resolved once here rather than
 * inside render — a date that changes between two renders of the same form is how a document
 * ends up with a different posting date than the one a reader saw.
 *
 * When the effective-policy endpoint exists this becomes a `useServiceRead` and nothing above
 * it moves, which is the whole point of the form reading from a contract rather than from
 * hardcoded fields.
 */

/**
 * Enough items to exercise a lookup, each carrying what its master would resolve: a list price,
 * a unit, an HSN/SAC and a tax rate.
 *
 * **The tax rates are fixture data, not statutory claims.** They stand in for the jurisdiction
 * adapter's answer so the preview has something to compute with; the real figure for any supply
 * comes from the published tax profile, and nothing here should be read as one.
 */
const ITEMS = [
  { id: '01990000-0000-7000-8000-0000000000e1', label: 'Basmati rice 25kg', meta: 'RICE-25 · HSN 1006', rate: '2450', unit: 'bag', hsnSac: '1006', taxRate: '5' },
  { id: '01990000-0000-7000-8000-0000000000e2', label: 'Basmati rice 10kg', meta: 'RICE-10 · HSN 1006', rate: '1010', unit: 'bag', hsnSac: '1006', taxRate: '5' },
  { id: '01990000-0000-7000-8000-0000000000e3', label: 'Sunflower oil 1L', meta: 'OIL-1L · HSN 1512', rate: '142.5', unit: 'nos', hsnSac: '1512', taxRate: '5' },
  { id: '01990000-0000-7000-8000-0000000000e4', label: 'Turmeric powder 500g', meta: 'TUR-500 · HSN 0910', rate: '96', unit: 'nos', hsnSac: '0910', taxRate: '5' },
  { id: '01990000-0000-7000-8000-0000000000e5', label: 'Delivery and handling', meta: 'SAC 9965 · service', rate: '250', unit: '', hsnSac: '9965', taxRate: '18' },
];

/**
 * Open advances per customer, as Accounting would project them: the unallocated balance of
 * credit already received. A projection only — Accounting locks and checks the authoritative
 * balance when the bill is accepted, so two bills cannot spend the same advance.
 */
const ADVANCES: Record<string, readonly OpenAdvance[]> = {
  '01990000-0000-7000-8000-0000000000c1': [
    { id: '01990000-0000-7000-8000-0000000000a5', label: 'Advance RC/26-27/0042', available: '5000' },
  ],
  '01990000-0000-7000-8000-0000000000c3': [
    { id: '01990000-0000-7000-8000-0000000000a6', label: 'Advance RC/26-27/0051', available: '1200' },
    { id: '01990000-0000-7000-8000-0000000000a7', label: 'Advance RC/26-27/0063', available: '800' },
  ],
};

/** The issuing company's registered state, which the fixture company is registered in. */
const COMPANY_STATE = 'Karnataka';

/** The income and service accounts an accounts-only bill is raised against. */
const ACCOUNTS = [
  { id: '01990000-0000-7000-8000-0000000000f1', label: 'Sales — goods', meta: 'Income', taxRate: '18' },
  { id: '01990000-0000-7000-8000-0000000000f2', label: 'Sales — services', meta: 'Income', taxRate: '18' },
  { id: '01990000-0000-7000-8000-0000000000f3', label: 'Freight recovered', meta: 'Income', taxRate: '' },
];

/**
 * Each fixture customer's credit, as the party master would project it. Sharma Traders is over
 * its limit with something overdue, so the warning paths have something to say.
 */
const CREDIT: Record<string, CustomerCredit> = {
  '01990000-0000-7000-8000-0000000000c1': { limit: '500000', outstanding: '120000', overdue: '0' },
  '01990000-0000-7000-8000-0000000000c3': { limit: '50000', outstanding: '48000', overdue: '6500' },
};

/** Addresses per customer, each with the state that makes it a place of supply. */
const ADDRESSES: Record<string, readonly { id: string; label: string; meta: string; state: string }[]> = {
  '01990000-0000-7000-8000-0000000000c1': [
    { id: '01990000-0000-7000-8000-0000000000d1', label: 'Head office, Bengaluru', meta: 'Karnataka', state: 'Karnataka' },
    { id: '01990000-0000-7000-8000-0000000000d2', label: 'Warehouse, Hosur', meta: 'Tamil Nadu', state: 'Tamil Nadu' },
  ],
  '01990000-0000-7000-8000-0000000000c3': [
    { id: '01990000-0000-7000-8000-0000000000d3', label: 'Shop, Chandni Chowk', meta: 'Delhi', state: 'Delhi' },
  ],
};

/**
 * What a price level does to a list price, for the fixture: wholesale is 5% under retail and
 * "catalog price" is retail. Fixture arithmetic, exact, standing in for the price book.
 */
function atLevel(rate: string, level: string): string {
  if (level !== 'Wholesale') return rate;
  const value = D.parse(rate);
  return value === null ? rate : D.format(D.round(value - D.percent(value, D.parse('5')!), 2), 2);
}

/** Enough customers to exercise a lookup, including two that collide on a prefix. */
const CUSTOMERS = [
  { id: '01990000-0000-7000-8000-0000000000c1', label: 'Nandini Trading Company', meta: 'NTC-001 · Karnataka', state: 'Karnataka' },
  { id: '01990000-0000-7000-8000-0000000000c2', label: 'Nandini Enterprises', meta: 'NEN-014 · Karnataka', state: 'Karnataka' },
  { id: '01990000-0000-7000-8000-0000000000c3', label: 'Sharma Traders', meta: 'SHT-007 · Delhi', state: 'Delhi' },
  { id: '01990000-0000-7000-8000-0000000000c4', label: 'Kerala Spice Exports', meta: 'KSE-002 · Kerala', state: 'Kerala' },
  { id: '01990000-0000-7000-8000-0000000000c5', label: 'Deccan Wholesale', meta: 'DWS-021 · Telangana', state: 'Telangana' },
];

export function SalesEntryRoute({
  company,
  canCreate,
}: {
  company: string;
  canCreate: boolean;
}) {
  /*
   * Once per mount, so every render of this form agrees about what day it is — and the day in
   * the company's timezone. `toISOString` is the UTC date: before 05:30 in India it was
   * yesterday, and on 1 April that is the previous financial year.
   */
  const { timezone } = useDisplayConfig();
  const today = useMemo(() => businessToday(timezone), [timezone]);

  const loadCustomers = useCallback<SearchSelectLoader>(
    async ({ q }) => {
      const needle = q.trim().toLowerCase();
      const items = CUSTOMERS.filter(
        (customer) =>
          !needle ||
          customer.label.toLowerCase().includes(needle) ||
          customer.meta.toLowerCase().includes(needle),
      );
      return { items, nextCursor: null };
    },
    // `company` is in the dependency list even though the fixture ignores it: the real loader
    // is company-scoped, and a lookup that silently kept another company's candidates after a
    // switch is exactly the bug this closes over.
    [company],
  );

  /*
   * Items or accounts, by mode. One loader rather than two props because the grid asks for "the
   * thing this line is about" and the mode decides what that is — which is also how the real
   * lookup will work, against two different services.
   */
  const loadSubjects = useCallback(
    (mode: EntryMode): SearchSelectLoader =>
      async ({ q }) => {
        const needle = q.trim().toLowerCase();
        // A mixed bill looks in both: the item master and the income accounts.
        const source = mode === 'ACCOUNTS' ? ACCOUNTS : mode === 'MIXED' ? [...ITEMS, ...ACCOUNTS] : ITEMS;
        return {
          items: source.filter(
            (entry) =>
              !needle ||
              entry.label.toLowerCase().includes(needle) ||
              entry.meta.toLowerCase().includes(needle),
          ),
          nextCursor: null,
        };
      },
    [],
  );

  /*
   * What a chosen master supplies. The fixture stands in for Catalog (items) and Accounting
   * (accounts); the shape — a partial line, with the rate marked as the list price — is what the
   * real resolver will return.
   */
  const resolveSubject = useCallback<SubjectResolver>((id, priceLevel = '') => {
    const item = ITEMS.find((entry) => entry.id === id);
    if (item) {
      const service = item.unit === '';
      return {
        subjectKind: 'ITEM',
        subjectNature: service ? 'SERVICE' : 'GOODS',
        rate: atLevel(item.rate, priceLevel),
        unit: item.unit,
        hsnSac: item.hsnSac,
        taxRate: item.taxRate,
        // A service line moves no stock; saying so here keeps a reader from having to.
        stockIntent: service ? 'NONE' : 'EXECUTE',
      };
    }
    const account = ACCOUNTS.find((entry) => entry.id === id);
    return account
      ? { subjectKind: 'ACCOUNT', subjectNature: 'SERVICE', taxRate: account.taxRate, stockIntent: 'NONE' }
      : null;
  }, []);

  const resolveCustomerCredit = useCallback((id: string) => CREDIT[id] ?? null, []);

  const loadAddresses = useCallback(
    (customerId: string): SearchSelectLoader =>
      async ({ q }) => {
        const needle = q.trim().toLowerCase();
        return {
          items: (ADDRESSES[customerId] ?? []).filter(
            (address) => !needle || address.label.toLowerCase().includes(needle),
          ),
          nextCursor: null,
        };
      },
    [],
  );

  const resolveAddressState = useCallback(
    (id: string) =>
      Object.values(ADDRESSES)
        .flat()
        .find((address) => address.id === id)?.state ?? '',
    [],
  );

  const loadAdvances = useCallback<AdvanceLoader>(
    async (customerId) => ADVANCES[customerId] ?? [],
    [],
  );

  const resolveCustomerState = useCallback(
    (id: string) => CUSTOMERS.find((customer) => customer.id === id)?.state ?? '',
    [],
  );

  return (
    <SalesEntryPage
      policy={SAMPLE_SALES_POLICY}
      today={today}
      loadCustomers={loadCustomers}
      loadSubjects={loadSubjects}
      resolveSubject={resolveSubject}
      resolveCustomerState={resolveCustomerState}
      resolveCustomerCredit={resolveCustomerCredit}
      loadAddresses={loadAddresses}
      resolveAddressState={resolveAddressState}
      loadAdvances={loadAdvances}
      companyState={COMPANY_STATE}
      canCreate={canCreate}
    />
  );
}
