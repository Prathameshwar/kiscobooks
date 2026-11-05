'use client';

/**
 * What the sales bill reads from the masters, as the page's loaders and resolvers.
 *
 * Every call is company-scoped and goes through `/api/sales-entry`. Each function returns the
 * page's own shapes — a `SearchSelectLoader`, a partial line, a credit position — and keeps the
 * master facts the save needs (versions, units, accounts) in the `Refs` caches, keyed by the
 * master's id, so the draft itself stays the page's draft.
 */
import type { SearchSelectLoader } from '@janso/ui';
import * as D from './fixed-decimal';
import { companyPath, salesCall } from './sales-entry-api';
import type { CustomerCredit, DraftLine } from './sales-entry-draft';
import type { EntryMode, TenderMode } from './sales-entry-policy';
import type { AccountRef, CustomerRef, SubjectRef } from './sales-entry-wire';
import type { EffectiveConfiguration, SalesBinding } from './sales-entry-connection';
import type { OpenAdvance } from '../components/SalesSettlementDrawer';
import { isTypeId } from './voucher-type-routes';

type Page<T> = { items: T[]; page?: { next_cursor: string | null; has_more?: boolean }; next_cursor?: string | null };
const nextOf = (page: Page<unknown>) => page.page?.next_cursor ?? page.next_cursor ?? null;
const query = (values: Record<string, string | null | undefined>) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) if (value) params.set(key, value);
  return params.toString();
};

/* ------------------------------------------------------------------ the company */

export type CompanyFacts = {
  readonly currency: string;
  /** ISO subdivision, `IN-KA`. */
  readonly state: string;
  readonly registrationId: string | null;
};

type CompanyDetail = { base_currency?: string; state_code?: string };
type Registration = { id: string; is_primary: boolean; jurisdiction_code: string; tax_system: string; valid_to: string | null };

export async function loadCompany(company: string, today: string): Promise<CompanyFacts> {
  const [detail, registrations] = await Promise.all([
    salesCall<CompanyDetail>('identity', { path: companyPath(company, '') }),
    salesCall<Page<Registration>>('identity', { path: companyPath(company, '/tax-registrations?limit=50') }),
  ]);
  // The primary GST registration in force: it is what a service is taxed under, and its
  // jurisdiction is the company's state for the intra/inter-state decision.
  const gst = registrations.items.find(
    (row) => row.is_primary && /GST/i.test(row.tax_system) && (!row.valid_to || row.valid_to >= today),
  );
  return {
    currency: detail.base_currency ?? 'INR',
    state: gst?.jurisdiction_code ?? detail.state_code ?? '',
    registrationId: gst?.id ?? null,
  };
}

/* ------------------------------------------------------------------ the bill type */

export type SalesType = { id: string; company_id?: string; code?: string; name?: string; kind?: string; profile?: string; status?: string };

export async function loadSalesTypes(company: string, typeId?: string): Promise<SalesType[]> {
  if (typeId) {
    if (!isTypeId(typeId)) throw { status: 502, message: 'The selected sales type could not be verified.' };
    const row = await salesCall<SalesType>('vouchers', { path: companyPath(company, '/voucher-types/' + typeId) });
    if (!row || row.id !== typeId || row.company_id !== company || row.kind !== 'SALES') throw { status: 502, message: 'The selected sales type could not be verified for this company.' };
    if (row.status !== 'ACTIVE' || row.profile !== 'STANDARD') throw { status: 422, message: 'The selected sales type is not available in this invoice editor. Choose an active standard sales type.' };
    return [row];
  }
  const page = await salesCall<Page<SalesType>>('vouchers', {
    path: companyPath(company, '/voucher-types?' + query({ kind: 'SALES', status: 'ACTIVE', limit: '50' })),
  });
  return page.items.filter((row) => (row.kind === undefined || row.kind === 'SALES')
    && (row.profile === undefined || row.profile === 'STANDARD'));
}

export function loadConfiguration(company: string, typeId: string, date: string): Promise<EffectiveConfiguration> {
  return salesCall<EffectiveConfiguration>('vouchers', {
    path: companyPath(company, `/voucher-types/${typeId}/effective-configuration?` + query({ date })),
  });
}

/* ------------------------------------------------------------------ accounts the bill books to */

type AccountRow = { id: string; row_version?: number; name?: string; code?: string; kind?: string; system_key?: string | null; status?: string; party_id?: string | null; party_role?: string | null };
const ref = (row: AccountRow | undefined): AccountRef | null =>
  row && row.row_version ? { id: row.id, version: row.row_version } : null;

export type BookAccounts = {
  readonly salesRevenue: AccountRef | null;
  readonly serviceRevenue: AccountRef | null;
  readonly tenders: Partial<Record<TenderMode, AccountRef>>;
  readonly rounding: { readonly gain: AccountRef | null; readonly loss: AccountRef | null };
};

/**
 * The accounts a bill books to without the reader naming them: revenue, cash, the first bank,
 * round-off. Found by their system keys — the chart's own names for them — never by display name.
 */
export async function loadBookAccounts(company: string, binding: SalesBinding): Promise<BookAccounts> {
  const [general, cash, bank] = await Promise.all(
    ['GENERAL', 'CASH', 'BANK'].map((kind) =>
      salesCall<Page<AccountRow>>('accounting', { path: companyPath(company, '/accounts?' + query({ kind, status: 'ACTIVE', limit: '200' })) }),
    ),
  );
  const bySystem = (key: string) => general!.items.find((row) => row.system_key === key);
  const allowed = (row: AccountRow | undefined) =>
    row && (!binding.supplyAccountIds || binding.supplyAccountIds.includes(row.id)) ? row : undefined;
  const firstBank = ref(bank!.items[0]);
  const cashMain = ref(cash!.items.find((row) => row.system_key === 'CASH_MAIN') ?? cash!.items[0]);
  return {
    salesRevenue: ref(allowed(bySystem('SALES_REVENUE'))),
    serviceRevenue: ref(allowed(bySystem('SERVICE_REVENUE'))),
    tenders: {
      ...(cashMain ? { CASH: cashMain } : {}),
      ...(firstBank ? { UPI: firstBank, CARD: firstBank, BANK_TRANSFER: firstBank, CHEQUE: firstBank } : {}),
    },
    rounding: { gain: ref(bySystem('ROUNDING_GAIN')), loss: ref(bySystem('ROUNDING_LOSS')) },
  };
}

/* ------------------------------------------------------------------ customers */

type Party = { id: string; name?: string; code?: string; row_version?: number; status?: string };

export function customerLoader(company: string): SearchSelectLoader {
  return async ({ q, cursor, signal }) => {
    const page = await salesCall<Page<Party>>('accounting', {
      path: companyPath(company, '/parties?' + query({ role: 'CUSTOMER', status: 'ACTIVE', q: q.trim() || null, cursor, limit: '50' })),
      ...(signal ? { signal } : {}),
    });
    return {
      items: page.items.map((row) => ({ id: row.id, label: row.name ?? row.code ?? 'Customer', ...(row.code ? { meta: row.code } : {}) })),
      nextCursor: nextOf(page),
    };
  };
}

type Address = { id: string; label?: string; city?: string; state_code?: string; status?: string };
type AddressUse = { address_id?: string; purpose?: string; is_default?: boolean; status?: string };

export type CustomerFacts = {
  readonly ref: CustomerRef;
  /** The registered (or billing) address's state, `IN-KA`. */
  readonly state: string;
  readonly credit: CustomerCredit | null;
};

/**
 * A chosen customer: its version, its receivable account, its state, its credit.
 *
 * The receivable is the customer's PARTY account — narrowed to the policy's allowlist where it
 * names one. The state is the registered address's, falling back to billing; the credit is
 * Accounting's own decision for a zero amount, which reports exposure, limit and overdue.
 */
export async function resolveCustomer(
  company: string,
  partyId: string,
  context: { binding: SalesBinding; currency: string; date: string },
  addresses: Map<string, string>,
): Promise<CustomerFacts> {
  const [party, accounts, places, uses] = await Promise.all([
    salesCall<Party>('accounting', { path: companyPath(company, `/parties/${partyId}`) }),
    // The customer-role account only: a party that is also a supplier holds a payable too, and a bill must never post to it.
    salesCall<Page<AccountRow>>('accounting', { path: companyPath(company, '/accounts?' + query({ party_id: partyId, kind: 'PARTY', role: 'CUSTOMER', status: 'ACTIVE', limit: '50' })) }),
    salesCall<Page<Address>>('accounting', { path: companyPath(company, '/party-addresses?' + query({ party_id: partyId, status: 'ACTIVE', limit: '50' })) }),
    salesCall<Page<AddressUse>>('accounting', { path: companyPath(company, '/party-address-uses?' + query({ party_id: partyId, status: 'ACTIVE', limit: '50' })) }),
  ]);
  for (const place of places.items) if (place.state_code) addresses.set(place.id, place.state_code);
  // The bill never asks for the account: a customer has exactly one receivable, so choosing the customer chooses it. Several
  // (or none) is a data problem for Accounting to repair, never a guess, and a row that is not in the customer role is refused.
  const allowed = accounts.items.filter(
    (row) =>
      row.party_role === 'CUSTOMER' &&
      (!context.binding.partyAccountIds || context.binding.partyAccountIds.includes(row.id)),
  );
  const receivable = ref(allowed.length === 1 ? allowed[0] : undefined);
  const used = (purpose: string) =>
    uses.items.find((row) => row.purpose === purpose && row.is_default) ?? uses.items.find((row) => row.purpose === purpose);
  const home = used('REGISTERED') ?? used('BILLING');
  const state = places.items.find((row) => row.id === home?.address_id)?.state_code ?? places.items[0]?.state_code ?? '';

  let credit: CustomerCredit | null = null;
  if (receivable) {
    try {
      const decision = await salesCall<{ exposure: string; limit: string | null; overdue: string }>('accounting', {
        path: companyPath(company, '/credit/check'),
        method: 'POST',
        // The smallest amount the check takes (it refuses zero): the decision then reports the
        // customer's exposure, limit and overdue as they stand, which is all this page reads.
        body: { account_id: receivable.id, currency: context.currency, amount: '0.0001', exchange_rate: '1', posting_date: context.date },
      });
      credit = { limit: decision.limit ?? '', outstanding: String(decision.exposure), overdue: String(decision.overdue) };
    } catch {
      // A credit position the reader cannot see is not a reason to stop billing: the service
      // applies the limit at acceptance whatever this page knew.
      credit = null;
    }
  }
  return {
    ref: { partyId, partyVersion: party.row_version ?? 1, account: receivable },
    state,
    credit,
  };
}

export function addressLoader(company: string, partyId: string, states: Map<string, string>): SearchSelectLoader {
  return async ({ q, cursor, signal }) => {
    const page = await salesCall<Page<Address>>('accounting', {
      path: companyPath(company, '/party-addresses?' + query({ party_id: partyId, status: 'ACTIVE', q: q.trim() || null, cursor, limit: '50' })),
      ...(signal ? { signal } : {}),
    });
    for (const row of page.items) if (row.state_code) states.set(row.id, row.state_code);
    return {
      items: page.items.map((row) => ({
        id: row.id,
        label: row.label ?? row.city ?? 'Address',
        meta: [row.city, row.state_code].filter(Boolean).join(' · '),
      })),
      nextCursor: nextOf(page),
    };
  };
}

/* ------------------------------------------------------------------ what is sold */

export type Item = { id: string; sku?: string; name?: string; base_unit_id?: string; row_version?: number };

/**
 * Items, accounts or both, by mode. A mixed bill searches the two masters and shows both; the
 * resolver later asks the right one, because it remembers which an id came from.
 */
export function subjectLoader(
  company: string,
  mode: EntryMode,
  binding: SalesBinding,
  sources: Map<string, 'ITEM' | 'ACCOUNT'>,
  /** Items seen in the list, so resolving one does not read it again. */
  seen?: Map<string, Item>,
): SearchSelectLoader {
  return async ({ q, cursor, signal }) => {
    const needle = q.trim() || null;
    const items =
      mode === 'ACCOUNTS'
        ? null
        : salesCall<Page<Item>>('catalog', {
            path: companyPath(company, '/items?' + query({ q: needle, sellable: 'true', status: 'ACTIVE', limit: '25', cursor: mode === 'ITEMS' ? cursor : null })),
            ...(signal ? { signal } : {}),
          });
    const accounts =
      mode === 'ITEMS'
        ? null
        : salesCall<Page<AccountRow>>('accounting', {
            path: companyPath(company, '/accounts?' + query({ q: needle, kind: 'GENERAL', status: 'ACTIVE', limit: '25', cursor: mode === 'ACCOUNTS' ? cursor : null })),
            ...(signal ? { signal } : {}),
          });
    const [itemPage, accountPage] = await Promise.all([items, accounts]);
    const options = [
      ...(itemPage?.items ?? []).map((row) => {
        sources.set(row.id, 'ITEM');
        seen?.set(row.id, row);
        return { id: row.id, label: row.name ?? row.sku ?? 'Item', ...(row.sku ? { meta: row.sku } : {}) };
      }),
      ...(accountPage?.items ?? [])
        // An accounts line credits an income account the policy allows, and nothing else.
        .filter((row) => !binding.supplyAccountIds || binding.supplyAccountIds.includes(row.id))
        .map((row) => {
          sources.set(row.id, 'ACCOUNT');
          return { id: row.id, label: row.name ?? row.code ?? 'Account', meta: mode === 'MIXED' ? `Account${row.code ? ' · ' + row.code : ''}` : (row.code ?? '') };
        }),
    ];
    const next = mode === 'ITEMS' ? (itemPage ? nextOf(itemPage) : null) : mode === 'ACCOUNTS' ? (accountPage ? nextOf(accountPage) : null) : null;
    return { items: options, nextCursor: next };
  };
}

type Binding = { id: string; unit_id?: string | null; usage_role?: string; code?: string };
type UnitRevision = { id: string; conversion_mode?: string; valid_from?: string; valid_to?: string | null };
type Price = { status: 'RESOLVED' | 'MISSING' | 'NEEDS_TAX_CONTEXT'; amount: string | number | null; price_basis_quantity?: string | number | null };
type TaxResolution = {
  status: 'COMPLETE' | 'MISSING' | 'REQUIRE_EXPLICIT';
  classification_code?: string | null;
  treatment?: string | null;
  rates?: { components: { component: string; percentage?: string | number | null }[] }[];
};

/**
 * A chosen subject, resolved: the partial line the page merges, and the reference the save needs.
 *
 * An item's selling unit is its binding in force today, priced through `prices/resolve` for this
 * customer and price level; a `MISSING` price leaves the rate blank — a blank rate is not a price
 * of nil. Its tax classification says goods (HSN) or service (SAC), and the rate shown is the
 * catalog's, for the preview only: the service calculates the tax that is billed.
 */
export async function resolveSubject(
  company: string,
  id: string,
  kind: 'ITEM' | 'ACCOUNT',
  context: { date: string; currency: string; partyId: string | null; priceLevelId: string | null; accounts: BookAccounts },
  items: Map<string, Item>,
): Promise<{ patch: Partial<DraftLine>; ref: SubjectRef } | null> {
  if (kind === 'ACCOUNT') {
    const account = await salesCall<AccountRow>('accounting', { path: companyPath(company, `/accounts/${id}`) });
    const own = ref(account);
    if (!own) return null;
    return {
      patch: { subjectKind: 'ACCOUNT', subjectNature: 'SERVICE', stockIntent: 'NONE' },
      ref: { kind: 'ACCOUNT', account: own },
    };
  }

  const item =
    items.get(id) ??
    (await salesCall<Item>('catalog', { path: companyPath(company, `/items/${id}`) }));
  items.set(id, item);
  const bindings = await salesCall<Page<Binding>>('catalog', {
    path: companyPath(company, `/items/${id}/unit-bindings?` + query({ as_of: context.date, limit: '50' })),
  });
  const binding =
    bindings.items.find((row) => row.unit_id && /SALE/i.test(row.usage_role ?? '')) ??
    bindings.items.find((row) => row.unit_id && /BASE/i.test(row.usage_role ?? '')) ??
    bindings.items.find((row) => row.unit_id === item.base_unit_id);
  const unitId = binding?.unit_id ?? item.base_unit_id ?? null;
  let revisionId: string | null = null;
  if (binding) {
    const revisions = await salesCall<Page<UnitRevision>>('catalog', {
      path: companyPath(company, `/item-unit-bindings/${binding.id}/revisions?` + query({ as_of: context.date, limit: '50' })),
    });
    revisionId =
      revisions.items.find(
        (row) => row.valid_from && row.valid_from <= context.date && (!row.valid_to || row.valid_to >= context.date),
      )?.id ?? null;
  }

  const [price, tax] = await Promise.all([
    revisionId
      ? salesCall<Price>('catalog', {
          path: companyPath(company, '/prices/resolve'),
          method: 'POST',
          body: {
            item_id: id,
            unit_revision_id: revisionId,
            currency: context.currency,
            as_of: context.date,
            quantity: '1',
            purpose: 'SALE',
            ...(context.partyId ? { party_id: context.partyId } : {}),
            ...(context.priceLevelId ? { price_level_id: context.priceLevelId } : {}),
          },
        }).catch(() => null)
      : Promise.resolve(null),
    salesCall<TaxResolution>('catalog', {
      path: companyPath(company, '/tax-configurations/resolve'),
      method: 'POST',
      body: { item_id: id, as_of: context.date, direction: 'SALE' },
    }).catch(() => null),
  ]);

  const rate = priceRate(price);
  const code = tax?.classification_code ?? '';
  // SAC classifies a service and HSN goods; an unclassified item is treated as goods, which is
  // the case the service cannot yet bill and so the one that must not be mistaken for the other.
  const nature: 'GOODS' | 'SERVICE' = /^99/.test(code) ? 'SERVICE' : 'GOODS';
  const percent = taxPercent(tax);
  if (!unitId) return null;
  return {
    patch: {
      subjectKind: 'ITEM',
      subjectNature: nature,
      hsnSac: code,
      taxRate: percent ?? '',
      unit: '',
      stockIntent: nature === 'SERVICE' ? 'NONE' : 'EXECUTE',
      ...(rate ? { rate } : {}),
    },
    ref: {
      kind: 'ITEM',
      itemVersion: item.row_version ?? 1,
      unitId,
      nature,
      incomeAccount: nature === 'SERVICE' ? context.accounts.serviceRevenue : context.accounts.salesRevenue,
    },
  };
}

/** A resolved price as a unit rate, exactly: the amount over the quantity it prices. */
export function priceRate(price: Price | null): string | null {
  if (!price || price.status !== 'RESOLVED' || price.amount === null || price.amount === undefined) return null;
  const amount = D.parse(String(price.amount));
  const per = D.parse(String(price.price_basis_quantity ?? '1')) ?? D.ONE;
  if (amount === null || per <= D.ZERO) return null;
  return D.format(D.div(amount, per)).replace(/\.?0+$/, '');
}

/** The GST rate the catalog classifies an item at: IGST, or CGST and SGST together. */
export function taxPercent(tax: TaxResolution | null): string | null {
  if (!tax || tax.status !== 'COMPLETE') return null;
  const components = tax.rates?.[0]?.components ?? [];
  const igst = components.find((row) => row.component === 'IGST');
  if (igst?.percentage !== undefined && igst.percentage !== null) return String(igst.percentage);
  const halves = components.filter((row) => row.component === 'CGST' || row.component === 'SGST' || row.component === 'UTGST');
  if (halves.length === 0) return null;
  const sum = halves.reduce((total, row) => total + (D.parse(String(row.percentage ?? '0')) ?? D.ZERO), D.ZERO);
  return D.format(sum).replace(/\.?0+$/, '');
}

/* ------------------------------------------------------------------ price levels */

type Level = { id: string; code?: string; name?: string; status?: string };

export async function loadPriceLevels(company: string): Promise<{ value: string; label: string }[]> {
  const page = await salesCall<Page<Level>>('catalog', { path: companyPath(company, '/price-levels?limit=100') });
  return page.items.map((row) => ({ value: row.id, label: row.name ?? row.code ?? 'Price level' }));
}

/* ------------------------------------------------------------------ advances */

type OpenItem = { id: string; reference?: string | null; amount?: string | number | null; currency?: string | null };

/**
 * A customer's credit open items with what is left of each — Accounting's projection, which it
 * locks and checks again at acceptance, so two bills cannot spend one advance.
 */
export function advanceLoader(company: string, date: string): (customerId: string) => Promise<OpenAdvance[]> {
  return async (customerId) => {
    const page = await salesCall<Page<OpenItem>>('accounting', {
      path: companyPath(company, '/open-items?' + query({ party_id: customerId, role: 'CUSTOMER', direction: 'CREDIT', limit: '50' })),
    });
    const balances = await Promise.all(
      page.items.map((row) =>
        salesCall<{ remaining: string | number }>('accounting', {
          path: companyPath(company, `/open-items/${row.id}/balance?` + query({ as_of: date })),
        }).then((balance) => ({ row, remaining: String(balance.remaining) })),
      ),
    );
    return balances
      .filter(({ remaining }) => (D.parse(remaining) ?? D.ZERO) > D.ZERO)
      .map(({ row, remaining }) => ({ id: row.id, label: row.reference ? `Advance ${row.reference}` : 'Advance', available: remaining }));
  };
}
