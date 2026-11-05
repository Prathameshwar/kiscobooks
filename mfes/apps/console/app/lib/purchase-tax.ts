import type { components } from '@janso/api-client/vouchers';
import type { ServiceRequest } from './service-call';
import { trackingId } from './stock-tracking-resources';
import { validMasterDate } from './catalog-masters';

/**
 * Tax on the Purchase account bill.
 *
 * The person says *whether* GST applies and, if so, the facts the bill itself holds: which of the company's GST
 * registrations the bill is under, the place of supply, and when the service was completed. Rates, components and
 * amounts are never typed here; Accounting works them out from each expense account's tax default, which is why
 * this module only ever *reads* masters to tell the person what to expect, and mirrors Accounting's refusals far
 * enough to give an answer before the round trip. Accounting still validates (CLAUDE.md §5.6, invariant 14).
 *
 * "Automatic" is a blank: a draft stores only what the person chose, and the rest is resolved from the masters when it
 * is shown and when it is sent, so a bill never keeps a stale registration after its supplier or date changed.
 */
type Reader = <T>(request: ServiceRequest) => Promise<T>;
export type InvoiceTaxContext = components['schemas']['InvoiceTaxContext'];

/** `NONE` is "this bill carries no tax"; `''` is not yet decided, which a bill is never saved in. */
export type PurchaseTaxChoice = '' | 'NONE' | 'FORWARD' | 'REVERSE';
export type PurchaseTaxDraft = {
  choice: PurchaseTaxChoice;
  /** Blank: the company's primary GST registration in force on the invoice date. */
  companyRegistration: string;
  /** Blank: the state of that registration. An ISO subdivision, `IN-MH`. */
  placeOfSupply: string;
  /** Blank: the supplier invoice date. */
  completionDate: string;
  /** Blank: the supplier's only regular GST registration. */
  supplierRegistration: string;
};
export const blankPurchaseTax = (): PurchaseTaxDraft => ({ choice: '', companyRegistration: '', placeOfSupply: '', completionDate: '', supplierRegistration: '' });
export const isTaxed = (tax: PurchaseTaxDraft): boolean => tax.choice === 'FORWARD' || tax.choice === 'REVERSE';

export const TAX_PROFILES = { FORWARD: 'INDIA_DOMESTIC_SERVICE', REVERSE: 'INDIA_DOMESTIC_SERVICE_RCM' } as const;
export const TAX_CHOICE_LABELS = { FORWARD: 'Charged by the supplier', REVERSE: 'Reverse charge: you pay the GST' } as const;
export const TAX_CHOICE_HINTS = {
  FORWARD: 'The supplier’s invoice shows GST, and you owe it to the supplier with the bill.',
  REVERSE: 'The GST is yours to pay to the government; it is not added to what you owe the supplier.',
} as const;
export const TREATMENT_LABELS: Record<string, string> = { TAXABLE: 'Taxable', NIL_RATED: 'Nil-rated', EXEMPT: 'Exempt', NON_GST: 'Non-GST' };

const covers = (from: string | null | undefined, to: string | null | undefined, on: string) => (!from || from <= on) && (!to || to >= on);
const refuse = (message: string): never => { throw new Error(message); };
/** `MH` and `IN-MH` are the same state to Accounting; the wire carries the ISO subdivision. */
export function subdivision(code: string | null | undefined): string {
  const value = (code ?? '').trim().toUpperCase();
  if (/^IN-[A-Z0-9]{1,3}$/.test(value)) return value;
  return /^[A-Z0-9]{1,3}$/.test(value) ? 'IN-' + value : '';
}

export type CompanyGst = { id: string; number: string; state: string; primary: boolean; from: string; to: string | null };
export type SupplierGst = { id: string; type: string; state: string; number: string; from: string | null; to: string | null };
export type AccountTaxDefault = { id: string; account: string; code: string; codeSystem: string; supplyKind: string; treatment: string; reverse: boolean };
export type PurchaseTaxFacts = {
  /** `null` until read. */
  companies: readonly CompanyGst[] | null;
  /** The supplier's GST registrations, by party id. */
  suppliers: ReadonlyMap<string, readonly SupplierGst[]>;
  /** An account's purchase tax default on a date, by `defaultKey`; `null` is "read, and there is none". */
  defaults: ReadonlyMap<string, AccountTaxDefault | null>;
};
export const noTaxFacts = (): PurchaseTaxFacts => ({ companies: null, suppliers: new Map(), defaults: new Map() });
export const defaultKey = (account: string, date: string) => account + '|' + date;
/** The company's registrations that cover a date, primary first (the order they were read in). */
export const registrationsInForce = (facts: PurchaseTaxFacts, on: string): readonly CompanyGst[] => (facts.companies ?? []).filter(row => covers(row.from, row.to, on));

type Page<T> = { items: T[]; page?: { next_cursor: string | null } };

/** The company's GST registrations, every one it has: which are in force is decided against the bill's date. */
export async function loadCompanyGst(read: Reader, company: string, signal?: AbortSignal): Promise<CompanyGst[]> {
  const page = await read<Page<{ id: string; is_primary: boolean; jurisdiction_code: string; number: string; tax_system: string; valid_from: string; valid_to: string | null }>>({ service: 'identity', path: `/v1/companies/${company}/tax-registrations?limit=50`, signal });
  if (!Array.isArray(page?.items) || page.items.length > 50 || page.items.some(row => !trackingId.test(row.id))) refuse('The company’s GST registrations could not be verified.');
  return page.items
    .filter(row => /GST/i.test(row.tax_system) && subdivision(row.jurisdiction_code) && validMasterDate(row.valid_from) && typeof row.number === 'string')
    .map(row => ({ id: row.id, number: row.number, state: subdivision(row.jurisdiction_code), primary: row.is_primary === true, from: row.valid_from, to: row.valid_to ?? null }))
    .sort((a, b) => Number(b.primary) - Number(a.primary) || a.number.localeCompare(b.number));
}

type PartyRegistration = { id: string; company_id: string; party_id?: string | null; scheme?: string | null; registration_type?: string | null; state_code?: string | null; registration_number?: string | null; valid_from?: string | null; valid_to?: string | null };
/** A supplier's GST registrations. The list is lean (no type or state), so each is read once; a supplier has a handful. */
export async function loadSupplierGst(read: Reader, company: string, party: string, signal?: AbortSignal): Promise<SupplierGst[]> {
  const base = `/v1/companies/${company}/party-tax-registrations`;
  const page = await read<Page<PartyRegistration>>({ service: 'accounting', path: `${base}?${new URLSearchParams({ party_id: party, limit: '50' })}`, signal });
  const ours = (row: PartyRegistration) => trackingId.test(row.id) && row.company_id === company && row.party_id === party;
  if (!Array.isArray(page?.items) || page.items.length > 50 || !page.items.every(ours)) refuse('The supplier’s GST registrations could not be verified.');
  const listed = page.items.filter(row => row.scheme === 'GST_IN');
  if (listed.length > 12) refuse('This supplier has too many GST registrations to choose from here. Review them in the supplier’s tax registrations.');
  const rows = await Promise.all(listed.map(async row => {
    const detail = await read<PartyRegistration>({ service: 'accounting', path: `${base}/${row.id}`, signal });
    if (detail?.id !== row.id || !ours(detail)) refuse('The supplier’s GST registrations could not be verified.');
    return detail;
  }));
  return rows.map(row => ({ id: row.id, type: row.registration_type ?? '', state: subdivision(row.state_code), number: row.registration_number ?? '', from: row.valid_from ?? null, to: row.valid_to ?? null }));
}

type DefaultRow = { id: string; company_id: string; account_id?: string | null; direction?: string | null };
type DefaultDetail = DefaultRow & { code?: string | null; code_system?: string | null; supply_kind?: string | null; treatment?: string | null; rcm_applicable?: boolean | null };
/** What an expense account says a purchase of it is taxed as on `on`; `null` when it says nothing. */
export async function loadAccountTaxDefault(read: Reader, company: string, account: string, on: string, signal?: AbortSignal): Promise<AccountTaxDefault | null> {
  const base = `/v1/companies/${company}/account-tax-defaults`;
  const page = await read<Page<DefaultRow>>({ service: 'accounting', path: `${base}?${new URLSearchParams({ account_id: account, direction: 'PURCHASE', as_of: on, limit: '5' })}`, signal });
  const ours = (row: DefaultRow) => trackingId.test(row.id) && row.company_id === company && row.account_id === account && row.direction === 'PURCHASE';
  if (!Array.isArray(page?.items) || page.items.length > 5 || !page.items.every(ours)) refuse('The account’s tax default could not be verified.');
  if (!page.items.length) return null;
  if (page.items.length > 1) refuse('This account has overlapping tax defaults on that date. Review them in Masters.');
  const detail = await read<DefaultDetail>({ service: 'accounting', path: `${base}/${page.items[0]!.id}`, signal });
  if (detail?.id !== page.items[0]!.id || !ours(detail) || typeof detail.treatment !== 'string' || typeof detail.supply_kind !== 'string') refuse('The account’s tax default could not be verified.');
  return { id: detail.id, account, code: detail.code ?? '', codeSystem: detail.code_system ?? '', supplyKind: detail.supply_kind!, treatment: detail.treatment!, reverse: detail.rcm_applicable === true };
}

/** Where the supplier's GST stands for this bill. */
export type SupplierGstState =
  | { kind: 'unselected' }
  | { kind: 'unread' }
  | { kind: 'none' }
  | { kind: 'ineligible'; type: string }
  | { kind: 'choose'; options: readonly SupplierGst[] }
  | { kind: 'ready'; registration: SupplierGst };

export type TaxProblem = { field: 'tax' | 'companyRegistration' | 'placeOfSupply' | 'completionDate' | 'supplierRegistration'; message: string };
export type TaxResolution = {
  company: CompanyGst | null;
  /** The company's registrations in force on the invoice date. */
  companies: readonly CompanyGst[];
  place: string;
  completion: string;
  supplier: SupplierGstState;
  /** The supplier's regular registrations in force on the invoice date: what a person may choose between. */
  supplierOptions: readonly SupplierGst[];
  problems: readonly TaxProblem[];
};

/** Accounting's rule, in one place: only a regular GST supplier can be taxed under either profile. */
export const REGISTRATION_TYPE_LABELS: Record<string, string> = { REGULAR: 'Regular', COMPOSITION: 'Composition', UNREGISTERED: 'Unregistered', SEZ_UNIT: 'SEZ unit', SEZ_DEVELOPER: 'SEZ developer', UIN: 'UIN', OVERSEAS: 'Overseas', CASUAL: 'Casual', NRTP: 'Non-resident', OTHER: 'Other' };

export function resolvePurchaseTax(input: { tax: PurchaseTaxDraft; invoiceDate: string; supplier: string; facts: PurchaseTaxFacts }): TaxResolution {
  const { tax, invoiceDate, supplier, facts } = input;
  const companies = registrationsInForce(facts, invoiceDate);
  const company = companies.find(row => row.id === tax.companyRegistration) ?? (tax.companyRegistration ? null : companies[0] ?? null);
  const place = tax.placeOfSupply || company?.state || '';
  const completion = tax.completionDate || invoiceDate;
  let state: SupplierGstState;
  let options: readonly SupplierGst[] = [];
  const registrations = supplier ? facts.suppliers.get(supplier) : undefined;
  if (!supplier) state = { kind: 'unselected' };
  else if (!registrations) state = { kind: 'unread' };
  else {
    const regular = registrations.filter(row => row.type === 'REGULAR' && covers(row.from, row.to, invoiceDate));
    options = regular;
    const chosen = regular.find(row => row.id === tax.supplierRegistration);
    state = chosen ? { kind: 'ready', registration: chosen }
      : regular.length === 1 ? { kind: 'ready', registration: regular[0]! }
      : regular.length > 1 ? { kind: 'choose', options: regular }
      : registrations.length === 0 ? { kind: 'none' }
      : { kind: 'ineligible', type: registrations.find(row => covers(row.from, row.to, invoiceDate))?.type ?? registrations[0]!.type };
  }
  const problems: TaxProblem[] = [];
  if (isTaxed(tax)) {
    if (facts.companies === null) problems.push({ field: 'companyRegistration', message: 'The company’s GST registrations have not been read yet. Wait a moment, or reload them.' });
    else if (!company) problems.push({ field: 'companyRegistration', message: companies.length ? 'Choose the GST registration this bill is under.' : 'This company has no GST registration in force on the invoice date. A company administrator needs to add one before GST can be recorded.' });
    if (!/^IN-[A-Z0-9]{1,3}$/.test(place)) problems.push({ field: 'placeOfSupply', message: 'Choose the place of supply: the state where the service is received.' });
    if (!validMasterDate(completion)) problems.push({ field: 'completionDate', message: 'Enter a valid service completion date.' });
    if (state.kind === 'none') problems.push({ field: 'supplierRegistration', message: 'This supplier has no GST registration on record. Add it to the supplier’s tax registrations, or record the bill without tax.' });
    else if (state.kind === 'ineligible') problems.push({ field: 'supplierRegistration', message: `GST can only be recorded here for a regular GST supplier; this one is ${(REGISTRATION_TYPE_LABELS[state.type] ?? (state.type || 'not regular')).toLowerCase()}. Record the bill without tax, or correct the supplier’s registration.` });
    else if (state.kind === 'choose') problems.push({ field: 'supplierRegistration', message: 'This supplier has more than one regular GST registration. Choose the one on the invoice.' });
    else if (state.kind === 'unread' && supplier) problems.push({ field: 'supplierRegistration', message: 'The supplier’s GST registration has not been read yet. Wait a moment, or reload it.' });
  }
  return { company, companies, place, completion, supplier: state, supplierOptions: options, problems };
}

export type RowTax = { tone: 'ok' | 'bad' | 'pending'; text: string; fix?: 'tax-default' };
/** What to tell the person about one expense account, against how the bill is taxed. Accounting decides; this predicts. */
export function rowTaxStatus(choice: PurchaseTaxChoice, found: AccountTaxDefault | null | undefined): RowTax {
  if (found === undefined) return { tone: 'pending', text: 'Reading the account’s tax default…' };
  if (found === null) return { tone: 'bad', text: 'This account has no purchase tax default, so Accounting cannot work out the GST.', fix: 'tax-default' };
  if (found.supplyKind !== 'SERVICE' || found.codeSystem !== 'SAC') return { tone: 'bad', text: 'This account’s tax default is for goods. Only services can carry GST on this bill.', fix: 'tax-default' };
  if (found.reverse !== (choice === 'REVERSE')) return { tone: 'bad', text: found.reverse ? 'This account is set to reverse charge. Choose “Reverse charge” for this bill, or use another account.' : 'This account is not set to reverse charge. Choose “Charged by the supplier” for this bill, or use another account.' };
  const treatment = TREATMENT_LABELS[found.treatment] ?? found.treatment;
  return { tone: 'ok', text: `SAC ${found.code} · ${treatment}${found.treatment === 'TAXABLE' ? '' : ': no GST is charged'}` };
}

/** The tax block of the bill, for a taxed bill. Throws the sentence the person needs when it cannot be built. */
export function purchaseTaxContext(input: { tax: PurchaseTaxDraft; invoiceDate: string; invoice: string; supplier: string; facts: PurchaseTaxFacts }): InvoiceTaxContext {
  const { tax } = input;
  if (tax.choice !== 'FORWARD' && tax.choice !== 'REVERSE') refuse('Only a taxed bill has a tax context.');
  const resolution = resolvePurchaseTax(input);
  if (resolution.problems.length) refuse(resolution.problems[0]!.message);
  const supplier = resolution.supplier.kind === 'ready' ? resolution.supplier.registration : refuse('Choose the supplier’s GST registration.');
  const number = input.invoice.trim();
  if (!number || number.length > 120) refuse('Enter the supplier invoice number: GST needs it.');
  return {
    profile: TAX_PROFILES[tax.choice as 'FORWARD' | 'REVERSE'],
    company_registration_id: resolution.company!.id,
    party_registration_id: supplier.id,
    place_of_supply: resolution.place,
    service_completion_date: resolution.completion,
    supplier_invoice_number: number,
    supplier_invoice_date: input.invoiceDate,
  };
}

/** The choice a saved profile stands for, or null for a profile this screen does not capture. */
export function choiceOfProfile(profile: string | undefined): PurchaseTaxChoice | null {
  return profile === 'UNTAXED_ACCOUNT' ? 'NONE' : profile === TAX_PROFILES.FORWARD ? 'FORWARD' : profile === TAX_PROFILES.REVERSE ? 'REVERSE' : null;
}
