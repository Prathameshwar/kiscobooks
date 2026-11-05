'use client';
import { useEffect, useRef, useState } from 'react';
import { Notice } from '@janso/ui';
import type { components } from '@janso/api-client/catalog';
import { masterRequest } from '../lib/catalog-master-api';
import { requestFailure, type RequestFailure } from '../lib/service-call';
import { clearIntent, keepIntent, openingBody, setupBody, type AdvancedIntent } from '../lib/advanced-product-api';
import type { AdvancedOptions } from '../lib/advanced-product-draft';

type Status = components['schemas']['AdvancedDefinitionStatus'];
type Result = components['schemas']['AdvancedDefinitionResult'];
type Ready = components['schemas']['AdvancedSkuReadiness'];
type Family = components['schemas']['FamilyDetail'];
type Item = components['schemas']['ItemDetail'];
const valid = (status: Status, intent: AdvancedIntent) => {
  if (!status || status.company_id !== intent.company || status.id !== intent.creation_id || status.sku_ids.length !== intent.work.skus.length) throw { status: 502, message: 'Product progress did not match the reviewed request.' };
  return status;
};
export function AdvancedCreationProgress({ initial, onEdit }: { initial: AdvancedIntent; onEdit: (intent: AdvancedIntent) => void }) {
  const intent = useRef(initial);
  const running = useRef(false);
  const mounted = useRef(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('Checking product creation…');
  const [failure, setFailure] = useState<RequestFailure | null>(null);
  const [blockers, setBlockers] = useState<Ready['blockers']>([]);
  const [status, setStatus] = useState<Status | null>(null);
  const base = `/v1/companies/${initial.company}/advanced-product-creations`;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const show = (value: Status) => { if (mounted.current) setStatus(valid(value, intent.current)); };
  const note = (value: string) => { if (mounted.current) setMessage(value); };
  const saveIntent = () => keepIntent(intent.current);
  async function command<T>(name: string, path: string, body: unknown): Promise<T> {
    let frozen = intent.current.commands[name];
    if (!frozen) {
      frozen = { path, body: structuredClone(body), key: crypto.randomUUID() };
      intent.current.commands[name] = frozen;
      saveIntent();
    }
    const result = await masterRequest<T>({ path: frozen.path, method: 'POST', body: frozen.body, key: frozen.key });
    delete intent.current.commands[name];
    saveIntent();
    return result;
  }
  async function readStatus(): Promise<Status> {
    const current = await masterRequest<Status>({ path: `${base}/definitions/${intent.current.creation_id}` });
    show(current);
    return current;
  }
  async function currentOptions(): Promise<AdvancedOptions> {
    const work = intent.current.work;
    const params = new URLSearchParams({ kind: work.profile.kind, group_id: work.profile.group_id, product_type_revision_id: work.profile.product_type_revision_id });
    const value = await masterRequest<AdvancedOptions>({ path: base + '/options?' + params });
    if (value.company_id !== intent.current.company || value.selected_type?.id !== work.profile.product_type_revision_id || !value.mode.product_family_sku_enabled) throw { status: 409, message: 'Product setup changed. Review the current Product Type and company settings.' };
    return value;
  }
  async function run() {
    if (running.current) return;
    running.current = true; setBusy(true); setFailure(null); setBlockers([]);
    try {
      const current = intent.current;
      if (!current.creation_id) {
        note('Creating the Product Profile and explicit SKUs…');
        const result = await masterRequest<Result>({ path: base + '/definitions', method: 'POST', body: current.definition, key: current.key });
        if (result.creation.company_id !== current.company || result.creation.sku_ids.length !== current.work.skus.length || result.family.company_id !== current.company) throw { status: 502, message: 'Creation receipt could not be verified.' };
        current.creation_id = result.creation.id;
        saveIntent(); show(result.creation);
      }
      let state = await readStatus();
      const id = current.creation_id!;
      for (let index = 0; index < current.work.skus.length; index++) {
        const itemId = state.sku_ids[index]!;
        if (state.sku_progress?.[index]?.setup_done) continue;
        note(`Setting up SKU ${index + 1} of ${current.work.skus.length}…`);
        const options = await currentOptions();
        const [family, item] = await Promise.all([
          masterRequest<Family>({ path: `/v1/companies/${current.company}/product-families/${state.family_id}` }),
          masterRequest<Item>({ path: `/v1/companies/${current.company}/items/${itemId}` }),
        ]);
        if (family.company_id !== current.company || item.company_id !== current.company || item.family_id !== state.family_id || !family.row_version || !item.row_version) throw { status: 502, message: 'Product versions could not be verified for setup.' };
        state = await command<Status>(`setup:${itemId}`, `${base}/definitions/${id}/skus/${itemId}/setup`, setupBody(current.work, options, index, state.row_version, family.row_version, item.row_version));
        show(state);
      }
      for (let index = 0; index < current.work.skus.length; index++) {
        const itemId = state.sku_ids[index]!;
        const progress = state.sku_progress?.[index];
        if (!progress?.price_draft_ids?.length || (progress.published_price_ids?.length ?? 0) >= progress.price_draft_ids.length) continue;
        note(`Publishing prices for SKU ${index + 1}…`);
        state = await command<Status>(`publish:${itemId}`, `${base}/definitions/${id}/skus/${itemId}/publish-prices`, { expected_creation_version: state.row_version });
        show(state);
      }
      for (let index = 0; index < current.work.skus.length; index++) {
        const itemId = state.sku_ids[index]!;
        if (state.sku_progress?.[index]?.activated) continue;
        note(`Checking SKU ${index + 1} readiness…`);
        const ready = await masterRequest<Ready>({ path: `${base}/definitions/${id}/skus/${itemId}/readiness`, method: 'POST', body: { as_of: current.definition.as_of } });
        if (ready.item_id !== itemId) throw { status: 502, message: 'SKU readiness did not match the reviewed SKU.' };
        if (!ready.eligible || ready.blockers.length || ready.source_version == null) {
          setBlockers(ready.blockers);
          throw { status: 422, message: `SKU ${index + 1} needs setup before activation.` };
        }
        note(`Activating SKU ${index + 1}…`);
        state = await command<Status>(`activate:${itemId}`, `${base}/definitions/${id}/skus/${itemId}/activate`, { expected_creation_version: state.row_version, expected_family_version: ready.family_version, expected_item_version: ready.item_version, expected_generation: ready.policy_generation, expected_source_version: ready.source_version, as_of: current.definition.as_of });
        show(state);
      }
      for (let index = 0; index < current.work.skus.length; index++) {
        const itemId = state.sku_ids[index]!;
        const openingState = state.sku_progress?.[index]?.opening_state ?? 'NOT_REQUESTED';
        if (openingState === 'POSTED' || openingState === 'SKIPPED') continue;
        const opening = openingBody(current.work, index);
        if (openingState === 'NOT_REQUESTED') {
          if (opening.decision === 'OPEN') {
            note(`Checking opening for SKU ${index + 1}…`);
            const checked = await masterRequest<components['schemas']['AdvancedOpeningCheck']>({ path: `${base}/definitions/${id}/skus/${itemId}/opening-preflight`, method: 'POST', body: opening });
            if (checked.item_id !== itemId) throw { status: 502, message: 'Opening preflight did not match the SKU.' };
          }
          note(`Saving opening decision for SKU ${index + 1}…`);
          state = await command<Status>(`opening:${itemId}`, `${base}/definitions/${id}/skus/${itemId}/opening`, { expected_creation_version: state.row_version, opening });
          show(state);
        }
        for (let attempt = 0; state.sku_progress?.[index]?.opening_state === 'IN_PROGRESS' && attempt < 12; attempt++) {
          note(`Posting and reconciling opening for SKU ${index + 1}…`);
          state = await masterRequest<Status>({ path: `${base}/definitions/${id}/skus/${itemId}/opening/advance`, method: 'POST' });
          show(state);
        }
        if (state.sku_progress?.[index]?.opening_state === 'IN_PROGRESS') throw { status: 503, message: `Opening for SKU ${index + 1} remains in progress. Continue this creation to check its retained owner receipts.` };
      }
      state = await readStatus();
      if (state.status !== 'COMPLETE') throw { status: 503, message: 'Product setup is still in progress. Continue to check its saved receipts.' };
      clearIntent(current.company);
      note('Product Profile and all requested SKUs are complete.');
    } catch (error) {
      if (mounted.current) setFailure(requestFailure(error));
      if (intent.current.creation_id) try { await readStatus(); } catch { /* Keep the last verified receipt visible. */ }
    } finally { running.current = false; if (mounted.current) setBusy(false); }
  }
  useEffect(() => { void run(); }, []);
  const complete = status?.status === 'COMPLETE';
  return <section className="product-wizard__progress" aria-label="Product creation progress"><h2 tabIndex={-1}>Product creation progress</h2><p role="status">{message}</p>{status && <><p>Profile ID: <code>{status.family_id}</code></p><ul>{status.sku_ids.map((itemId, index) => { const progress = status.sku_progress?.[index]; return <li key={itemId}><strong>{intent.current.work.skus[index]?.sku || `SKU ${index + 1}`}</strong> · {progress?.activated ? 'Active' : progress?.setup_done ? 'Setup saved' : 'Definition saved'} · Opening {progress?.opening_state?.toLowerCase().replaceAll('_', ' ') ?? 'not requested'}</li>; })}</ul></>}
    {blockers.length > 0 && <Notice tone="warning"><strong>Native readiness needs attention</strong><ul>{blockers.map((blocker, index) => <li key={index}>{blocker.path}: {blocker.code.replaceAll('_', ' ')}</li>)}</ul></Notice>}
    {failure && <Notice tone="warning">{failure.message} {status && <span>Completed steps remain saved.</span>}</Notice>}
    <div className="product-wizard__actions">{!complete && !busy && <button type="button" className="janso-btn janso-btn--primary" onClick={() => void run()}>Continue this creation</button>}{failure && !busy && failure.status < 500 && <button type="button" className="janso-btn janso-btn--secondary" onClick={() => onEdit(intent.current)}>Edit remaining setup</button>}{complete && <a className="janso-btn janso-btn--primary" href="/masters/items">Return to products</a>}</div>
  </section>;
}
