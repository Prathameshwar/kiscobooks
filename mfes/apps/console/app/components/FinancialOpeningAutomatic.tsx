'use client';
import { useEffect, useRef, useState } from 'react';
import { Button, Card, CardBody, Notice, SectionHeader } from '@janso/ui';
import type { components } from '@janso/api-client/accounting';
import { base, blockerLabel, owned, request, verifyWorkspace, type Access, type Reconciliation, type Workspace } from '../lib/financial-opening';
import { useServiceCommand } from '../lib/service-resource';
import type { ServiceRequest } from '../lib/service-call';

type Journal = components['schemas']['JournalDetail'];
// A declaration total can exceed one DECIMAL(19,4) line (up to 10,000 lines).
function total(value: string): bigint {
  if (typeof value !== 'string' || !/^(?:0|[1-9]\d{0,18})(?:\.\d{1,4})?$/.test(value)) throw new Error('Opening reconciliation contains an invalid exact total.');
  const [whole, fraction = ''] = value.split('.');
  return BigInt(whole!) * 10000n + BigInt(fraction.padEnd(4, '0'));
}
/** Mounted only after the user confirms Prepare and post. Each native command retains its own retry receipt. */
export function FinancialOpeningAutomatic({ company, initial, access, reason, onDirty, onDone }: {
  company: string; initial: Workspace; access: Access; reason: string; onDirty: (dirty: boolean) => void; onDone: (completed: boolean) => void;
}) {
  const command = useServiceCommand(request, 'automatic opening completion');
  const [running, setRunning] = useState(false), [message, setMessage] = useState('Preparing the reviewed opening…'), [error, setError] = useState('');
  const active = useRef(false), started = useRef(false), mounted = useRef(true), pause = useRef(false);
  const authority = useRef(access); authority.current = access;
  const [waiting, setWaiting] = useState(false);
  const frozen = useRef<{ payload: ServiceRequest; verify: (result: unknown) => void } | null>(null);
  const path = base(company) + '/workspaces/' + initial.id;
  function checkWorkspace(result: Workspace) {
    verifyWorkspace(company)(result);
    if (result.id !== initial.id || result.manifest_hash !== initial.manifest_hash || result.revision_id !== initial.revision_id ||
        result.posting_date !== initial.posting_date || result.currency !== initial.currency || !['DRAFT', 'FINALIZED'].includes(result.status))
      throw { status: 409, message: 'The opening changed. Review the current worksheet before continuing.' };
  }
  function checkFinalized(result: Workspace) {
    try { checkWorkspace(result); } catch { throw { status: 502, message: 'Opening completion could not be verified. Retry the same request.' }; }
    if (result.status !== 'FINALIZED' || result.effect_kind !== 'POSTED' || !result.journal_ids.length || result.posted_journals !== result.journal_ids.length)
      throw { status: 502, message: 'Opening completion was not confirmed. Retry the same request.' };
  }
  function checkReconciliation(result: Reconciliation) {
    if (result.batch_id !== initial.id || result.revision_id !== initial.revision_id || result.posting_date !== initial.posting_date ||
        result.currency !== initial.currency || result.coverage_mode !== initial.coverage_mode || !Array.isArray(result.blockers) ||
        typeof result.confirmation_pending !== 'boolean' || typeof result.ready_to_finalize !== 'boolean')
      throw new Error('Opening reconciliation could not be verified for the reviewed revision. Retry to refresh its status.');
    if (total(result.expected_debit) !== total(initial.expected_debit) || total(result.expected_credit) !== total(initial.expected_credit) ||
        total(result.posted_debit) !== total(result.expected_debit) || total(result.posted_credit) !== total(result.expected_credit) ||
        total(result.clearing_balance) !== 0n || result.declared_documents !== initial.document_count ||
        result.posted_documents !== result.declared_documents || result.gl_matches !== true || result.party_items_match !== true)
      throw new Error('Opening reconciliation has unresolved ledger, outstanding or clearing differences. Review the details on this page before continuing.');
    const blockers = result.blockers.filter(code => code !== 'NATIVE_CONFIRMATION_PENDING');
    if (blockers.length) throw new Error(blockers.map(blockerLabel).join(' '));
  }
  function checkJournal(id: string) {
    return (journal: Journal) => {
      owned(company)(journal);
      if (journal.id !== id || journal.kind !== 'OPENING' || journal.source_type !== 'financial_opening_chunk' ||
          !Number.isSafeInteger(journal.row_version) || !['DRAFT', 'PREPARED', 'POSTED'].includes(journal.status ?? ''))
        throw { status: 502, message: 'The opening journal could not be verified.' };
    };
  }
  async function mutate<T>(payload: ServiceRequest, verify: (result: T) => void) {
    if (!mounted.current) return false;
    if (!authority.current.manage || !authority.current.post || authority.current.period === false) throw new Error('Opening posting authority changed. Restore the required access before continuing.');
    frozen.current = { payload, verify: verify as (result: unknown) => void };
    const result = await command.execute<T>(payload, verify);
    if (!result) return false;
    frozen.current = null;
    return true;
  }
  async function continuePosting() {
    if (active.current || !access.manage || !access.post || access.period === false) return;
    active.current = true; pause.current = false; setRunning(true); setError('');
    try {
      // Replay before any new read/command. A timeout may already have applied the effect.
      if (command.uncertain && frozen.current && !await mutate(frozen.current.payload, frozen.current.verify)) return;
      let previousCount = -1;
      for (let attempt = 0; attempt < 100 && mounted.current; attempt++) {
        const current = await request<Workspace>({ path }); checkWorkspace(current);
        if (!mounted.current) return;
        if (current.status === 'FINALIZED') { checkFinalized(current); onDone(true); return; }
        if (current.blockers.includes('OPENING_DRAFTS_NOT_PREPARED') || !current.journal_ids.length) {
          if (current.journal_ids.length <= previousCount) throw new Error('Preparation made no further progress. Review the current opening status before continuing.');
          previousCount = current.journal_ids.length;
          setMessage(`Preparing opening journals · ${current.journal_ids.length} prepared`);
          if (!await mutate<Workspace>({ path: path + '/prepare-drafts', method: 'POST', body: { expected_version: current.expected_version, manifest_hash: current.manifest_hash, reason } }, result => {
            try { checkWorkspace(result); } catch { throw { status: 502, message: 'Opening preparation could not be verified. Retry the same request.' }; }
          })) return;
          continue;
        }
        for (const [index, id] of current.journal_ids.entries()) {
          const journalPath = `/v1/companies/${company}/journals/${id}`;
          const journal = await request<Journal>({ path: journalPath }); checkJournal(id)(journal);
          if (!mounted.current) return;
          if (journal.status === 'POSTED') continue;
          setMessage(`Posting opening journal ${index + 1} of ${current.journal_ids.length}`);
          if (!await mutate({ path: journalPath + '/post', method: 'POST', body: { expected_version: journal.row_version } }, result => {
            checkJournal(id)(result as Journal);
            if ((result as Journal).status !== 'POSTED') throw { status: 502, message: 'Posting was not confirmed. Retry the same request.' };
          })) return;
        }
        setMessage('Checking ledger, outstanding balances and migration clearing');
        while (mounted.current) {
          const reconciliation = await request<Reconciliation>({ path: path + '/reconciliation' }); checkReconciliation(reconciliation);
          if (!mounted.current) return;
          if (pause.current) { onDone(false); return; }
          if (reconciliation.confirmation_pending || reconciliation.blockers.includes('NATIVE_CONFIRMATION_PENDING')) {
            setMessage('Waiting for posting confirmation. This page will reconcile and finalize your opening automatically.'); setWaiting(true);
            await new Promise(resolve => setTimeout(resolve, 2000));
            continue;
          }
          setWaiting(false);
          // Read the latest version after confirmation; the server checks reconciliation again atomically.
          const latest = await request<Workspace>({ path }); checkWorkspace(latest);
          if (!mounted.current) return;
          if (latest.status === 'FINALIZED') { checkFinalized(latest); onDone(true); return; }
          if (!reconciliation.ready_to_finalize) throw new Error('Opening reconciliation is not ready for completion. Retry to refresh its status.');
          setMessage('Finalizing the reconciled opening');
          if (await mutate({ path: path + '/finalize', method: 'POST', body: { expected_version: latest.expected_version, manifest_hash: latest.manifest_hash, reason } }, checkFinalized) && mounted.current) onDone(true);
          return;
        }
        return;
      }
      setError('Preparation has not completed. Review the current status before continuing.');
    } catch (failure) {
      setError(failure && typeof failure === 'object' && 'message' in failure ? String(failure.message) : 'Opening status could not be loaded. Retry to continue from confirmed progress.');
    } finally { active.current = false; if (mounted.current) { setRunning(false); setWaiting(false); } }
  }
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { onDirty(true); return () => onDirty(false); }, [onDirty]);
  useEffect(() => { if (!started.current) { started.current = true; void continuePosting(); } }, []);
  return <Card><CardBody><div className="janso-flow"><SectionHeader title="Completing your opening" description="Prepare, post, reconcile and finalize in one action." />
    <p role="status" aria-live="polite">{message}</p>
    {(error || command.failure) && <Notice tone="danger">{error || command.failure?.message}</Notice>}
    {command.uncertain && <Notice>The last request is unconfirmed. Retry retains its exact values and request key.</Notice>}
    {running && waiting && <Button variant="ghost" onClick={() => { pause.current = true; setMessage('Pausing after the current status check'); }}>Pause automatic completion</Button>}
    {!running && <div className="janso-form-actions"><Button disabled={!access.post || !access.manage || access.period === false} onClick={() => void continuePosting()}>{command.uncertain ? 'Retry the same request' : 'Continue automatic opening'}</Button><Button variant="ghost" disabled={command.uncertain} onClick={() => onDone(false)}>Review posting status</Button></div>}
  </div></CardBody></Card>;
}
