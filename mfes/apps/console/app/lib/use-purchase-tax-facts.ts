'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ServiceRequest } from './service-call';
import { requestFailure } from './service-call';
import { validMasterDate } from './catalog-masters';
import { defaultKey, loadAccountTaxDefault, loadCompanyGst, loadSupplierGst, type AccountTaxDefault, type CompanyGst, type PurchaseTaxFacts, type SupplierGst } from './purchase-tax';

type Reader = <T>(request: ServiceRequest) => Promise<T>;
export type TaxFactFailures = { companies?: string; supplier?: string; defaults?: string };

const why = (error: unknown) => error instanceof Error ? error.message : requestFailure(error, 'Tax').message;

/**
 * The masters a taxed Purchase bill is checked against: the company's GST registrations, the supplier's, and what each
 * expense account says about purchase tax. Read only while the actor may read tax masters (`enabled`) and, for the
 * supplier and accounts, only while the bill is taxed (`active`). Every read is verified for this company by
 * `purchase-tax`; one that fails is reported, never guessed, and `reload` reads them all again (after the person has
 * fixed a master in another tab).
 */
export function usePurchaseTaxFacts({ enabled, active, read, company, supplier, accounts, on }: {
  enabled: boolean; active: boolean; read: Reader; company: string; supplier: string; accounts: readonly string[]; on: string;
}) {
  const [companies, setCompanies] = useState<readonly CompanyGst[] | null>(null);
  const [suppliers, setSuppliers] = useState<ReadonlyMap<string, readonly SupplierGst[]>>(() => new Map());
  const [defaults, setDefaults] = useState<ReadonlyMap<string, AccountTaxDefault | null>>(() => new Map());
  const [failures, setFailures] = useState<TaxFactFailures>({});
  const [attempt, setAttempt] = useState(0);
  const failed = (key: keyof TaxFactFailures, error: unknown) => setFailures(current => ({ ...current, [key]: why(error) }));
  const wanted = useMemo(() => [...new Set(accounts.filter(Boolean))].sort(), [accounts.join('|')]);

  useEffect(() => {
    if (!enabled || companies !== null || failures.companies) return;
    const controller = new AbortController();
    loadCompanyGst(read, company, controller.signal).then(rows => { if (!controller.signal.aborted) setCompanies(rows); }).catch(error => { if (!controller.signal.aborted) failed('companies', error); });
    return () => controller.abort();
  }, [enabled, company, companies === null, failures.companies, attempt]);

  useEffect(() => {
    if (!enabled || !active || !supplier || suppliers.has(supplier) || failures.supplier) return;
    const controller = new AbortController();
    loadSupplierGst(read, company, supplier, controller.signal).then(rows => { if (!controller.signal.aborted) setSuppliers(current => new Map(current).set(supplier, rows)); }).catch(error => { if (!controller.signal.aborted) failed('supplier', error); });
    return () => controller.abort();
  }, [enabled, active, company, supplier, suppliers.has(supplier), failures.supplier, attempt]);

  // One read of a bill's accounts at a time, in order: a long bill is not a burst of requests.
  const reading = useRef('');
  useEffect(() => {
    const missing = wanted.filter(account => !defaults.has(defaultKey(account, on)));
    if (!enabled || !active || !validMasterDate(on) || !missing.length || failures.defaults) return;
    const controller = new AbortController(), batch = missing.slice(0, 4), token = batch.join('|') + on + attempt;
    if (reading.current === token) return;
    reading.current = token;
    Promise.all(batch.map(async account => [defaultKey(account, on), await loadAccountTaxDefault(read, company, account, on, controller.signal)] as const))
      .then(rows => { if (!controller.signal.aborted) setDefaults(current => new Map([...current, ...rows])); })
      .catch(error => { if (!controller.signal.aborted) failed('defaults', error); })
      .finally(() => { if (reading.current === token) reading.current = ''; });
    return () => { controller.abort(); if (reading.current === token) reading.current = ''; };
  }, [enabled, active, company, on, wanted, defaults, failures.defaults, attempt]);

  const reload = useCallback(() => {
    setCompanies(null); setSuppliers(new Map()); setDefaults(new Map()); setFailures({}); setAttempt(value => value + 1);
  }, []);
  const facts = useMemo<PurchaseTaxFacts>(() => ({ companies, suppliers, defaults }), [companies, suppliers, defaults]);
  const loading = enabled && !failures.companies && companies === null
    || enabled && active && !failures.supplier && !!supplier && !suppliers.has(supplier)
    || enabled && active && !failures.defaults && wanted.some(account => !defaults.has(defaultKey(account, on)));
  return { facts, failures, loading, reload };
}
