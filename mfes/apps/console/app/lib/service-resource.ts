'use client';
import { useEffect, useRef, useState } from 'react';
import type { PageMeta } from '@janso/ui';
import { requestFailure, type RequestFailure, type ServiceRequest } from './service-call';
import { goTo } from './navigate';

export type ServiceReader = <T>(request: ServiceRequest) => Promise<T>;
export type ServicePage<T> = { items: T[]; page: PageMeta };
export function useServiceRead<T>(path: string | undefined, reader: ServiceReader, verify?: (value: T) => void, subject = 'configuration service') {
  const [state, setState] = useState<{ data: T | null; loading: boolean; failure: RequestFailure | null }>({ data: null, loading: !!path, failure: null });
  const [revision, setRevision] = useState(0), verifier = useRef(verify); verifier.current = verify;
  useEffect(() => {
    const controller = new AbortController(); setState({ data: null, loading: !!path, failure: null });
    if (path) reader<T>({ path, signal: controller.signal }).then(data => { if (!controller.signal.aborted) { verifier.current?.(data); setState({ data, loading: false, failure: null }); } }).catch(error => { if (!controller.signal.aborted) setState({ data: null, loading: false, failure: requestFailure(error, subject) }); });
    return () => controller.abort();
  }, [path, revision, reader, subject]);
  return { ...state, refresh: () => setRevision(value => value + 1) };
}
export function useServiceList<T>(base: string, filters: string, reader: ServiceReader, verifyItem?: (value: T) => void, enabled = true) {
  const [cursor, setCursor] = useState<string | null>(null), [previous, setPrevious] = useState<(string | null)[]>([]), [limit, setLimit] = useState(25);
  useEffect(() => { setCursor(null); setPrevious([]); }, [base, filters, limit]);
  const params = new URLSearchParams(filters); params.set('limit', String(limit)); if (!params.has('sort')) params.set('sort', '-id'); if (cursor) params.set('cursor', cursor);
  const read = useServiceRead<ServicePage<T>>(enabled ? base + '?' + params : undefined, reader, value => {
    if (!Array.isArray(value.items) || !value.page || !Number.isSafeInteger(value.page.limit)) throw { status: 502, message: 'The configuration list could not be verified.' };
    if (verifyItem) value.items.forEach(verifyItem);
  });
  return { ...read, limit, setLimit, hasPrevious: !!previous.length, first: () => { setCursor(null); setPrevious([]); read.refresh(); }, next: () => { if (!read.loading && read.data?.page.has_more && read.data.page.next_cursor) { setPrevious([...previous, cursor]); setCursor(read.data.page.next_cursor); } }, previous: () => { if (!read.loading && previous.length) { setCursor(previous.at(-1) ?? null); setPrevious(previous.slice(0, -1)); } } };
}
/** Replays retain the exact body/key; synchronous busy protection prevents double submission. */
type CommandReceipt = { signature: string; key: string; request: ServiceRequest };
type CommandRecovery = { storageKey: string; targetPath: string };
function readCommandRecovery(recovery?: CommandRecovery): { receipt: CommandReceipt | null; failure: RequestFailure | null } {
  const empty = { receipt: null, failure: null };
  const invalid = { receipt: null, failure: { status: 409, message: 'The saved tracking request could not be verified. Review its native history before starting another save.' } };
  if (!recovery) return empty;
  try {
    const raw = sessionStorage.getItem(recovery.storageKey);
    if (!raw) return empty;
    if (raw.length > 65536) return invalid;
    const value = JSON.parse(raw) as CommandReceipt;
    const request = value?.request;
    const path = request?.path;
    if (typeof path !== 'string' || /[?%\\#]/.test(path) || !['POST', 'PATCH'].includes(request.method ?? '') || !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value.key)) return invalid;
    if (path !== recovery.targetPath && !['hold', 'release', 'retire', 'reactivate'].some(action => path === recovery.targetPath + '/' + action)) return invalid;
    if (request.service !== undefined || request.signal !== undefined || typeof request.body !== 'object' || request.body === null || Array.isArray(request.body)) return invalid;
    const signature = JSON.stringify({ path, method: request.method, body: request.body });
    if (signature !== value.signature) return invalid;
    return { receipt: { signature, key: value.key, request: { path, method: request.method, body: request.body } }, failure: null };
  } catch { return invalid; }
}
export function useServiceCommand(reader: ServiceReader, subject = 'configuration service', recovery?: CommandRecovery) {
  const [restored] = useState(() => readCommandRecovery(recovery));
  const [pending, setPending] = useState(false), [failure, setFailure] = useState<RequestFailure | null>(restored.failure), [uncertain, setUncertain] = useState(!!restored.receipt);
  // `uncertain` is also kept in a ref: `execute` closes over the state of the render it was made in, so a caller
  // that `clear()`s and then executes in one click would otherwise be refused by the flag it has just cleared.
  const busy = useRef(false), uncertainNow = useRef(!!restored.receipt), receipt = useRef<CommandReceipt | null>(restored.receipt);
  const recoveryKey = useRef(recovery?.storageKey);
  const forgetRecovery = () => { if (recovery) try { sessionStorage.removeItem(recovery.storageKey); } catch { /* Verified receipts still remain authoritative. */ } };
  async function execute<T>(request: ServiceRequest, verify: (value: T) => void): Promise<T | null> {
    if (busy.current || restored.failure) return null;
    if (recoveryKey.current !== recovery?.storageKey) { setFailure({ status: 409, message: 'The signed-in user or company changed. Reload before saving.' }); return null; }
    const signature = JSON.stringify({ path: request.path, method: request.method ?? 'POST', body: request.body });
    if (uncertainNow.current && receipt.current?.signature !== signature) return null;
    if (request.key && !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(request.key)) {
      setFailure({ status: 422, message: 'A valid retained command key is required.' }); return null;
    }
    if (receipt.current?.signature !== signature) receipt.current = { signature, key: request.key ?? crypto.randomUUID(), request: { ...request, method: request.method ?? 'POST', body: structuredClone(request.body) } };
    busy.current = true; setPending(true); setFailure(null);
    const wasUncertain = uncertainNow.current;
    try {
      if (recovery) sessionStorage.setItem(recovery.storageKey, JSON.stringify(receipt.current));
      const result = await reader<T>({ ...receipt.current.request, key: receipt.current.key }); verify(result);
      forgetRecovery();
      receipt.current = null; uncertainNow.current = false; setUncertain(false); return result;
    } catch (error) {
      const problem = requestFailure(error, subject);
      const retrySame = problem.status >= 500 || [408, 429].includes(problem.status) || (wasUncertain && [401, 403, 409].includes(problem.status)) || (problem.status === 409 && ['request is busy; retry with the same idempotency key', 'request is already in progress; retry later'].includes(problem.message));
      setFailure(problem); uncertainNow.current = retrySame; setUncertain(retrySame);
      if (!retrySame) { receipt.current = null; forgetRecovery(); }
      return null;
    } finally { busy.current = false; setPending(false); }
  }
  function clear() { if (busy.current || restored.failure || recovery && uncertainNow.current) return; receipt.current = null; forgetRecovery(); uncertainNow.current = false; setFailure(null); setUncertain(false); }
  function retry<T>(verify: (value: T) => void): Promise<T | null> {
    return uncertainNow.current && receipt.current ? execute(receipt.current.request, verify) : Promise.resolve(null);
  }
  return { execute, retry, clear, pending, failure, uncertain, restoredRequest: restored.receipt?.request, blocked: pending || uncertain || !!failure && failure.status !== 422 };
}
export function useServiceDestination(pending: boolean) {
  const [destination, setDestination] = useState<string | null>(null);
  useEffect(() => { if (destination && !pending) goTo(destination); }, [destination, pending]);
  return { destination, setDestination };
}
