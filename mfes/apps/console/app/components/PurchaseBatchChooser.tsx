'use client';

import { useCallback, useRef, useState } from 'react';
import { Button, Modal, Notice, SearchSelect, TextField, useFormatters, type SearchSelectLoader } from '@janso/ui';
import { productFieldRequest as request } from '../lib/product-fields';
import { preparePurchaseBatch, purchaseBatch, purchaseBatchEligibility, purchaseBatchProblems, type PurchaseBatch, type PurchaseBatchDraft, type PurchaseTracking } from '../lib/purchase-stock';
import { trackingId } from '../lib/stock-tracking-resources';

type BatchRow = Pick<PurchaseBatch, 'id' | 'item_id' | 'code' | 'status' | 'is_held' | 'manufactured_on' | 'expires_on'>;
type BatchPage = { items: BatchRow[]; page: { has_more: boolean; next_cursor: string | null } };
const emptyBatch = (): PurchaseBatchDraft => ({ code: '', manufacturedOn: '', expiresOn: '', reason: 'Prepared for purchase bill' });

/** One chooser for a newly selected product and for later changes to its Purchase line. */
export function PurchaseBatchChooser({ company, item, name, postingDate, profile, canCreate, onSelect, onClose }: {
  company: string; item: string; name: string; postingDate: string; profile: PurchaseTracking;
  canCreate: boolean; onSelect: (batch: PurchaseBatch) => void; onClose: () => void;
}) {
  const format = useFormatters();
  const [mode, setMode] = useState<'select' | 'create'>('select');
  const [choice, setChoice] = useState<PurchaseBatch | null>(null), [loadingChoice, setLoadingChoice] = useState(false);
  const [draft, setDraft] = useState<PurchaseBatchDraft>(emptyBatch), [attempted, setAttempted] = useState(false);
  const [working, setWorking] = useState(false), [failure, setFailure] = useState('');
  const key = useRef(crypto.randomUUID()), choiceRun = useRef(0);
  const problems = purchaseBatchProblems(draft, profile, postingDate);
  const load = useCallback<SearchSelectLoader>(async ({ q, cursor, signal }) => {
    const params = new URLSearchParams({ item_id: item, status: 'ACTIVE', is_held: 'false', limit: '50' });
    if (q.trim()) params.set('q', q.trim().slice(0, 100));
    if (cursor) params.set('cursor', cursor);
    const page = await request<BatchPage>('accounting', 'GET', `/v1/companies/${company}/stock-tracking/batches?${params}`, undefined, undefined, signal);
    if (!Array.isArray(page.items) || page.items.length > 50 || !page.page || page.items.some(row => !trackingId.test(row.id) || row.item_id !== item || row.status !== 'ACTIVE' || row.is_held !== false)) throw Error('The batch list could not be verified.');
    return { items: page.items.map(row => ({ id: row.id, label: row.code || 'Batch ' + row.id.slice(-8),
      meta: [row.manufactured_on ? 'Made ' + format.date(row.manufactured_on) : '', row.expires_on ? 'Expires ' + format.date(row.expires_on) : ''].filter(Boolean).join(' · '),
      disabled: !!purchaseBatchEligibility(row, profile, postingDate) })), nextCursor: page.page.has_more ? page.page.next_cursor : null };
  }, [company, item, postingDate, profile, format]);
  const select = (id: string | null) => {
    const run = ++choiceRun.current;
    setChoice(null); setFailure(''); setLoadingChoice(!!id);
    if (!id) return;
    void purchaseBatch(company, item, id).then(batch => {
      if (run !== choiceRun.current) return;
      const issue = purchaseBatchEligibility(batch, profile, postingDate);
      if (issue) throw Error(issue);
      setChoice(batch);
    }).catch(error => { if (run === choiceRun.current) setFailure(error instanceof Error ? error.message : 'The batch could not be verified.'); })
      .finally(() => { if (run === choiceRun.current) setLoadingChoice(false); });
  };
  const edit = (patch: Partial<PurchaseBatchDraft>) => { key.current = crypto.randomUUID(); setDraft(current => ({ ...current, ...patch })); setFailure(''); };
  const confirm = async () => {
    if (working || loadingChoice) return;
    if (mode === 'select') {
      if (!choice) { setFailure('Choose an available batch for this product.'); return; }
      setWorking(true); setFailure('');
      try {
        const verified = await purchaseBatch(company, item, choice.id);
        const issue = purchaseBatchEligibility(verified, profile, postingDate);
        if (issue) throw Error(issue);
        onSelect(verified);
      } catch (error) { setFailure(error instanceof Error ? error.message : 'The batch could not be verified.'); }
      finally { setWorking(false); }
      return;
    }
    setAttempted(true);
    if (!canCreate || Object.keys(problems).length) return;
    setWorking(true); setFailure('');
    try {
      const created = await preparePurchaseBatch(company, item, draft, profile, key.current, postingDate);
      const issue = purchaseBatchEligibility(created, profile, postingDate);
      if (issue) throw Error(issue);
      onSelect(created);
    } catch (error) { setFailure(error instanceof Error ? error.message : 'The batch could not be created.'); }
    finally { setWorking(false); }
  };
  return <Modal open title="Choose batch for this purchase" size="lg" busy={working} onClose={onClose} footer={<>
    <Button type="button" variant="ghost" disabled={working} onClick={onClose}>Cancel</Button>
    <Button type="button" loading={working} disabled={loadingChoice} onClick={() => void confirm()}>{mode === 'select' ? 'Use selected batch' : 'Create and select batch'}</Button>
  </>}><div className="janso-entry-detail">
    <p className="janso-entry-workspace__caption">Product: <strong>{name}</strong>. One batch is recorded on this line; you can change it later.</p>
    <div role="tablist" aria-label="Batch choice" className="janso-entry-workflow__buttons">
      <Button type="button" role="tab" aria-selected={mode === 'select'} variant={mode === 'select' ? 'primary' : 'ghost'} disabled={working} onClick={() => { setMode('select'); setFailure(''); }}>Select existing</Button>
      {canCreate ? <Button type="button" role="tab" aria-selected={mode === 'create'} variant={mode === 'create' ? 'primary' : 'ghost'} disabled={working} onClick={() => { setMode('create'); setFailure(''); }}>Create batch</Button> : null}
    </div>
    {mode === 'select' ? <>
      <SearchSelect label="Search batches" value={choice?.id ?? null} selected={choice ? { id: choice.id, label: choice.code ?? choice.id } : null}
        loadOptions={load} scopeKey={`${company}:${item}:${postingDate}`} minQueryLength={0} onChange={select} disabled={working} />
      {loadingChoice ? <p role="status">Verifying batch…</p> : null}
      {choice ? <p className="janso-entry-workspace__caption">Batch {choice.code ?? choice.id}{choice.manufactured_on ? ` · Made ${format.date(choice.manufactured_on)}` : ''}{choice.expires_on ? ` · Expires ${format.date(choice.expires_on)}` : ''}</p> : null}
    </> : <div className="janso-form-grid">
      <TextField label="Batch code" value={draft.code} maxLength={100} required disabled={working} error={attempted ? problems.code : undefined} onChange={event => edit({ code: event.target.value })} />
      <TextField label="Manufacture date" type="date" value={draft.manufacturedOn} required={!!profile.manufactureDateRequired} disabled={working} error={attempted ? problems.manufacturedOn : undefined} onChange={event => edit({ manufacturedOn: event.target.value })} />
      <TextField label="Expiry date" type="date" value={draft.expiresOn} required={!!profile.expiryRequired} disabled={working} error={attempted ? problems.expiresOn : undefined} onChange={event => edit({ expiresOn: event.target.value })} />
      <TextField label="Reason for preparation" value={draft.reason} maxLength={500} required disabled={working} error={attempted ? problems.reason : undefined} onChange={event => edit({ reason: event.target.value })} />
      <p className="janso-entry-workspace__caption">Creating the batch records its identity and dates. Stock is received when the Purchase posts.</p>
    </div>}
    {failure ? <Notice tone="danger">{failure}</Notice> : null}
  </div></Modal>;
}
