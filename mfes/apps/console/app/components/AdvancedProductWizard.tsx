'use client';
import { useEffect, useRef, useState } from 'react';
import { Notice, PageHeader, PageNavigation, PreparationProgress } from '@janso/ui';
import type { components } from '@janso/api-client/catalog';
import { masterRequest } from '../lib/catalog-master-api';
import { catalogBack } from '../lib/product-classification';
import { requestFailure, type RequestFailure, type ServiceRequest } from '../lib/service-call';
import { useUnsavedChanges } from '../lib/use-unsaved-changes';
import { newWork, readWork, type AdvancedDraft, type AdvancedDraftList, type AdvancedOptions, type AdvancedWork } from '../lib/advanced-product-draft';
import { AdvancedProfileStep } from './AdvancedProfileStep';
import { AdvancedSkuStep } from './AdvancedSkuStep';
import { AdvancedSetupStep } from './AdvancedSetupStep';
import { AdvancedOpeningReviewStep } from './AdvancedOpeningReviewStep';
import { AdvancedCreationProgress } from './AdvancedCreationProgress';
import { useAdvancedNumericProblems } from './AdvancedPriceInput';
import { advancedProductErrors } from '../lib/advanced-product-validation';
import { openingSku } from '../lib/advanced-product-opening';
import { checkRecoveryIntent, definitionBody, keepIntent, readIntent, reviseIntent, type AdvancedIntent } from '../lib/advanced-product-api';
import { useProductMode } from './ProductModeProvider';

const labels = ['Product Profile', 'SKUs and units', 'Business setup', 'Opening and review'];
type Mode = components['schemas']['ProductModeDetail'];
export function AdvancedProductWizard({ company, returnTo, mode }: { company: string; returnTo?: string; mode: Mode }) {
  const root = `/v1/companies/${company}/advanced-product-creations`;
  const currentMode = useProductMode();
  const [work, setWork] = useState<AdvancedWork>(newWork);
  const [step, setStep] = useState(1);
  const [maxStep, setMaxStep] = useState(1);
  const [options, setOptions] = useState<AdvancedOptions | null>(null);
  const [loading, setLoading] = useState(true);
  const resolvedOptions = useRef('');
  const [failure, setFailure] = useState<RequestFailure | null>(null);
  const [saveFailure, setSaveFailure] = useState<RequestFailure | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const { invalid: hasNumericErrors, report: reportNumeric } = useAdvancedNumericProblems();
  const [focusPath, setFocusPath] = useState('');
  const focusSequence = useRef(0);
  const [drafts, setDrafts] = useState<AdvancedDraftList[]>([]);
  const [draft, setDraft] = useState<AdvancedDraft | null>(null);
  const [savedAt, setSavedAt] = useState('');
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [setupReady, setSetupReady] = useState(true);
  const [operation, setOperation] = useState('Saving your draft');
  const [reload, setReload] = useState(0);
  const [retry, setRetry] = useState<ServiceRequest | null>(null);
  const [needsReview, setNeedsReview] = useState(false);
  const [restoreFailure, setRestoreFailure] = useState('');
  const [impact, setImpact] = useState('');
  const [intent, setIntent] = useState<AdvancedIntent | null>(null);
  const [editingStatus, setEditingStatus] = useState<components['schemas']['AdvancedDefinitionStatus'] | null>(null);
  const summary = useRef<HTMLDivElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const main = useRef<HTMLElement>(null);
  const back = catalogBack(returnTo, '/masters/items');
  const changedMode = !!currentMode && (currentMode.company !== company || !!currentMode.failure || !currentMode.data || currentMode.data.product_family_sku_enabled !== true || currentMode.data.row_version !== mode.row_version || currentMode.data.policy_generation !== mode.policy_generation);
  useUnsavedChanges(() => dirty || busy || !!retry);
  useEffect(() => { const pending = readIntent(company); if (pending) setIntent(pending); }, [company]);
  useEffect(() => {
    const scope = (group: string, revision: string) => JSON.stringify([company, work.profile.kind, group, revision, mode.row_version, mode.policy_generation, reload]);
    if (resolvedOptions.current === scope(work.profile.group_id, work.profile.product_type_revision_id)) { setLoading(false); setFailure(null); return; }
    const controller = new AbortController();
    const params = new URLSearchParams({ kind: work.profile.kind });
    if (work.profile.group_id) params.set('group_id', work.profile.group_id);
    if (work.profile.product_type_revision_id) params.set('product_type_revision_id', work.profile.product_type_revision_id);
    setLoading(true); setFailure(null);
    masterRequest<AdvancedOptions>({ path: root + '/options?' + params, signal: controller.signal }).then(value => {
      if (controller.signal.aborted) return;
      if (value.company_id !== company || value.kind !== work.profile.kind || value.mode.row_version !== mode.row_version || value.mode.policy_generation !== mode.policy_generation || !value.mode.product_family_sku_enabled || value.family_fields.company_id !== company || value.sku_fields.company_id !== company || value.family_fields.entity_type !== 'catalog.product_family' || value.sku_fields.entity_type !== 'catalog.item') throw { status: 502, message: 'Product options could not be verified for this company.' };
      const group = work.profile.group_id || value.default_group_id || '';
      const revision = work.profile.product_type_revision_id || (!work.profile.product_type_id ? value.defaults.product_type_revision_id : '') || '';
      // The response already resolved these defaults. Applying them must not refetch it.
      resolvedOptions.current = scope(group, revision);
      setOptions(value); setLoading(false);
      if (group !== work.profile.group_id || revision !== work.profile.product_type_revision_id) setWork(previous => ({ ...previous, profile: { ...previous.profile, group_id: group, product_type_revision_id: revision } }));
    }).catch(error => { if (!controller.signal.aborted) { setFailure(requestFailure(error)); setLoading(false); } });
    return () => controller.abort();
  }, [root, company, work.profile.kind, work.profile.group_id, work.profile.product_type_revision_id, mode.row_version, mode.policy_generation, reload]);
  useEffect(() => {
    const controller = new AbortController();
    masterRequest<AdvancedDraftList[]>({ path: root + '/drafts', signal: controller.signal }).then(rows => { if (!controller.signal.aborted) setDrafts(rows.filter(row => row.company_id === company)); }).catch(() => undefined);
    return () => controller.abort();
  }, [root, company]);
  const update = (next: AdvancedWork) => { if (retry) return; setWork(next); setDirty(true); setSavedAt(''); setErrors({}); setSaveFailure(null); };
  const navigate = (next: number) => { setStep(next); setErrors({}); requestAnimationFrame(() => heading.current?.focus()); };
  const errorStep = (path: string) => path.startsWith('business.') ? 3 : path.startsWith('opening.') ? 4 : path.startsWith('skus.') ? 2 : 1;
  const focusError = (path: string) => {
    setStep(errorStep(path)); setFocusPath(path + '#' + ++focusSequence.current);
    requestAnimationFrame(() => requestAnimationFrame(() => ((main.current?.querySelector('[aria-invalid="true"]') as HTMLElement | null) ?? summary.current)?.focus()));
  };
  const continueStep = () => {
    if (!options || loading || changedMode || failure || hasNumericErrors || (step === 3 && !setupReady)) return;
    const validation = advancedProductErrors(work, options, editingStatus, step);
    setErrors(validation);
    if (Object.keys(validation).length) { requestAnimationFrame(() => summary.current?.focus()); return; }
    if (step < 4) { setMaxStep(value => Math.max(value, step + 1)); navigate(step + 1); }
  };
  const save = async () => {
    if (!options || loading || changedMode || busy || failure || hasNumericErrors) return;
    const payload: components['schemas']['AdvancedDraftSave'] = { mode_version: options.mode.row_version, policy_generation: options.mode.policy_generation, source_version: options.defaults.configuration.source_version, family_field_version: options.family_fields.source_version, sku_field_version: options.sku_fields.source_version, step, content: { profile: { ...work.profile, axes: work.axes }, skus: work.skus, business: work.business, opening: work.opening } };
    const request: ServiceRequest = retry ?? { path: root + (draft ? '/drafts/' + draft.id : '/drafts'), method: draft ? 'PUT' : 'POST', body: draft ? { ...payload, expected_version: draft.row_version } : payload, ...(draft ? {} : { key: crypto.randomUUID() }) };
    setOperation('Saving your draft'); setBusy(true); setSaveFailure(null);
    try {
      const result = await masterRequest<AdvancedDraft>(request);
      if (result.company_id !== company || !result.id || result.row_version < 1) throw { status: 502, message: 'Saved draft could not be verified.' };
      setDraft(result); setSavedAt(result.updated_at); setDirty(false); setRetry(null); setNeedsReview(result.needs_review);
      setDrafts(before => [result, ...before.filter(row => row.id !== result.id)]);
    } catch (error) {
      const problem = requestFailure(error);
      if (problem.status === 409 && draft && request.method === 'PUT') {
        try {
          const current = await masterRequest<AdvancedDraft>({ path: root + '/drafts/' + draft.id });
          const submitted = (request.body as components['schemas']['AdvancedDraftRevision']).content;
          if (current.company_id === company && current.id === draft.id && current.row_version === draft.row_version + 1 && JSON.stringify(current.content) === JSON.stringify(submitted)) {
            setDraft(current); setSavedAt(current.updated_at); setDirty(false); setRetry(null); setNeedsReview(current.needs_review); setSaveFailure(null);
            return;
          }
        } catch { /* Keep the draft blocked for an explicit recovery read. */ }
      }
      setSaveFailure(problem);
      if ([408, 429, 502, 503, 504].includes(problem.status)) setRetry(request);
      if (problem.status === 409) setNeedsReview(true);
    } finally { setBusy(false); }
  };
  const restore = async (id: string) => {
    if (busy || retry) return;
    if (dirty && !window.confirm('Replace your unsaved changes with this saved draft?')) return;
    setOperation('Opening your saved draft'); setBusy(true); setRestoreFailure('');
    try {
      const result = await masterRequest<AdvancedDraft>({ path: root + '/drafts/' + id });
      if (result.company_id !== company || result.id !== id) throw { status: 502, message: 'Draft did not match this company.' };
      setWork(readWork(result.content)); setDraft(result); setStep(result.step); setMaxStep(result.step); setNeedsReview(result.needs_review); setDirty(false); setRetry(null); setSavedAt(result.updated_at); setErrors({});
      requestAnimationFrame(() => heading.current?.focus());
    } catch (error) { setRestoreFailure(requestFailure(error).message); } finally { setBusy(false); }
  };
  const submit = async () => {
    if (!options || loading || changedMode || busy || failure || retry || needsReview || hasNumericErrors) return;
    const validation = advancedProductErrors(work, options, editingStatus);
    setErrors(validation);
    if (Object.keys(validation).length) {
      const first = Object.keys(validation)[0]!;
      focusError(first);
      setErrors(validation);
      return;
    }
    setOperation('Checking your product before creation'); setBusy(true); setFailure(null);
    try {
      const params = new URLSearchParams({ kind: work.profile.kind, group_id: work.profile.group_id, product_type_revision_id: work.profile.product_type_revision_id });
      const fresh = await masterRequest<AdvancedOptions>({ path: root + '/options?' + params });
      if (fresh.company_id !== company || !fresh.mode.product_family_sku_enabled || fresh.kind !== work.profile.kind || fresh.mode.row_version !== mode.row_version || fresh.mode.policy_generation !== options.mode.policy_generation || fresh.defaults.configuration.source_version !== options.defaults.configuration.source_version || fresh.family_fields.source_version !== options.family_fields.source_version || fresh.sku_fields.source_version !== options.sku_fields.source_version || fresh.selected_type?.id !== work.profile.product_type_revision_id) throw { status: 409, message: 'Product settings changed. Review the four steps before submitting.' };
      const pending = readIntent(company);
      checkRecoveryIntent(pending, editingStatus?.id ?? null);
      const current = editingStatus ? await masterRequest<components['schemas']['AdvancedDefinitionStatus']>({ path: `${root}/definitions/${editingStatus.id}` }) : null;
      const next: AdvancedIntent = current && pending ? reviseIntent(pending, work, fresh, current) : { company, key: crypto.randomUUID(), definition: definitionBody(work, fresh), work: structuredClone(work), commands: {}, reviewed_source_version: fresh.defaults.configuration.source_version, reviewed_policy_generation: fresh.mode.policy_generation, reviewed_mode_version: fresh.mode.row_version };
      keepIntent(next);
      setDirty(false); setEditingStatus(null); setIntent(next);
    } catch (error) { setFailure(requestFailure(error)); setNeedsReview(true); } finally { setBusy(false); }
  };
  const blocked = loading || !!failure || changedMode || busy || needsReview || !!retry;
  const saveBlocked = loading || !!failure || changedMode || busy || needsReview || !!editingStatus;
  if (intent) return <div className="janso-page product-wizard"><PageNavigation back={{ href: back, label: 'products' }} /><PageHeader title="Product creation" lede="Follow the setup of each SKU, including prices, activation and opening stock." /><AdvancedCreationProgress initial={intent} onEdit={(pending, status, nextStep, fields) => { setWork(pending.work); setEditingStatus(status); if (!status) setDirty(true); setIntent(null); setStep(nextStep); setMaxStep(4); setNeedsReview(false); setErrors(fields ?? {}); setFocusPath(Object.keys(fields ?? {})[0] ?? ''); }} /></div>;
  return <div className="janso-page product-wizard"><PageNavigation back={{ href: back, label: 'products' }} /><PageHeader title="New Product Profile + SKUs" lede="A Product Profile holds shared details, such as name and brand. A SKU is one version you sell or purchase, such as a size or pack." />
    <div className="product-wizard__header"><span className="product-wizard__eyebrow">Step {step} of {labels.length}</span><h2 ref={heading} tabIndex={-1}>{labels[step - 1]}</h2><p>{step === 1 ? 'Enter the shared product name, code and type. These details apply to every SKU.' : step === 2 ? 'Add a code, name and base unit for each version you will use. For example, Tea 100 g and Tea 250 g are two SKUs.' : step === 3 ? 'Select each SKU to enter its tax and purchase, selling and MRP details where enabled.' : 'Choose opening stock for each SKU, then check the summary. Creating will save and activate the SKUs and post any requested opening stock.'}</p></div>
    <nav className="product-wizard__steps" aria-label="Product creation steps">{labels.map((label, index) => <button key={label} type="button" className="product-wizard__step" aria-current={index + 1 === step ? 'step' : undefined} disabled={index + 1 > maxStep || blocked || hasNumericErrors} onClick={() => navigate(index + 1)}><span>{index + 1}</span><strong>{label}</strong></button>)}</nav>
    {busy && <PreparationProgress label="Product preparation progress" title={operation} detail="Your entered details are retained while this finishes." />}
    {editingStatus && <Notice tone="warning">Your Profile and SKU definitions are saved. Completed setup and opening choices are locked. Correct the remaining details, then review and continue this creation.</Notice>}
    {changedMode && <Notice tone="warning">Product setup changed. Your work is retained; reload settings and review before continuing. <button className="janso-link" type="button" onClick={currentMode?.refresh}>Check setup again</button></Notice>}
    {failure && <Notice tone="danger">{failure.message} <button type="button" className="janso-link" onClick={() => { setFailure(null); setReload(value => value + 1); }}>Retry loading</button></Notice>}
    {saveFailure && <Notice tone="danger">{saveFailure.message} {retry ? 'The result is uncertain. Retry the same save before editing.' : 'Your unsaved changes are still here.'}</Notice>}
    {needsReview && <Notice tone="warning">This draft uses changed settings. Review the Profile and SKU fields before saving again. <button type="button" className="janso-link" onClick={() => { setNeedsReview(false); setReload(value => value + 1); navigate(1); }}>Review settings</button></Notice>}
    {restoreFailure && <Notice tone="warning">{restoreFailure}</Notice>}
    {impact && <Notice tone="warning">{impact}</Notice>}
    {loading && <p role="status">Loading available product options…</p>}
    {!draft && drafts.length > 0 && <aside className="product-wizard__resume"><div><strong>Continue a saved draft</strong><p>Your recent work is private to your account and this company.</p></div><button className="janso-btn janso-btn--secondary" type="button" disabled={busy || !!retry} onClick={() => void restore(drafts[0]!.id)}>Open latest draft</button></aside>}
    {hasNumericErrors && <Notice tone="danger">Correct the highlighted numeric entries before saving or changing steps.</Notice>}
    <div ref={summary} tabIndex={-1}>{Object.keys(errors).length > 0 && <Notice tone="danger"><strong>Check these fields before continuing</strong><ul>{Object.entries(errors).map(([key, message]) => <li key={key}><button type="button" className="janso-link" onClick={() => focusError(key)}>{labels[errorStep(key) - 1]}{key.match(/(?:skus)\.(\d+)/)?.[1] !== undefined ? ` · SKU ${Number(key.match(/(?:skus)\.(\d+)/)![1]) + 1}` : ''}: {message}</button></li>)}</ul></Notice>}</div>
    <div className="product-wizard__layout"><main ref={main} className="product-wizard__main" aria-busy={loading}>
      {options?.company_id === company && step === 1 && <AdvancedProfileStep company={company} value={work.profile} options={options} definitionLocked={!!editingStatus} setupLocked={!!editingStatus?.sku_progress?.[0]?.setup_done} onChange={profile => { if ((profile.kind !== work.profile.kind || profile.product_type_revision_id !== work.profile.product_type_revision_id && !!work.profile.product_type_revision_id) && (work.axes.length > 0 || work.skus.some(row => row.sku || row.attributes.length))) { if (!window.confirm('Changing the kind or Type can affect SKU setup. Keep your entered SKUs and review them before continuing?')) return; setImpact('Product structure changed. Review every SKU and its business setup before creating.'); } update({ ...work, profile }); }} errors={errors} disabled={changedMode || busy || needsReview || !!retry || !!failure} refreshing={loading} />}
      {options?.company_id === company && step === 2 && <AdvancedSkuStep company={company} work={work} options={options} onChange={update} errors={errors} disabled={blocked} definitionLocked={!!editingStatus} locked={editingStatus?.sku_progress?.map(row => !!row.setup_done)} focusPath={focusPath} />}
      {options?.company_id === company && step === 3 && <AdvancedSetupStep onReadyChange={setSetupReady} onNumericProblem={reportNumeric} company={company} work={work} options={options} onChange={update} errors={errors} disabled={blocked} locked={editingStatus?.sku_progress?.map(row => !!row.setup_done)} focusPath={focusPath} />}
      {options?.company_id === company && step === 4 && <AdvancedOpeningReviewStep onNumericProblem={reportNumeric} company={company} work={work} options={options} onChange={update} onEdit={navigate} errors={errors} disabled={blocked} definitionLocked={!!editingStatus} dateLocked={editingStatus?.sku_progress?.map(row => !!row.setup_done)} locked={editingStatus?.sku_progress?.map(row => (row.opening_state ?? 'NOT_REQUESTED') !== 'NOT_REQUESTED')} focusPath={focusPath} />}
    </main><aside className="product-wizard__aside"><span>YOUR PRODUCT</span><strong>{work.profile.name || 'Untitled Profile'}</strong><p>{work.profile.kind === 'GOODS' ? 'Goods' : 'Service'} · {work.skus.length} SKU{work.skus.length === 1 ? '' : 's'}</p><hr /><span>DRAFT STATUS</span><p>{busy ? operation : dirty ? 'Unsaved changes' : savedAt ? `Saved ${new Date(savedAt).toLocaleString()}` : 'Not saved yet'}</p>{draft && <small>Draft version {draft.row_version}</small>}</aside></div>
    <div className="product-wizard__actions"><button type="button" className="janso-btn janso-btn--secondary" disabled={step === 1 || busy || hasNumericErrors} onClick={() => navigate(step - 1)}>Back</button><span className="product-wizard__actions-spacer" />{!editingStatus && <button type="button" className="janso-btn janso-btn--secondary" disabled={saveBlocked || hasNumericErrors || (!dirty && !!draft && !retry)} onClick={() => void save()}>{retry ? 'Retry same save' : busy ? 'Saving…' : 'Save draft'}</button>}{step < 4 ? <button type="button" className="janso-btn janso-btn--primary" disabled={blocked || hasNumericErrors || (step === 3 && !setupReady)} onClick={continueStep}>{step === 1 ? 'Continue to SKUs' : step === 2 ? 'Continue to business setup' : 'Continue to opening and review'}</button> : <button type="button" className="janso-btn janso-btn--primary" disabled={blocked || hasNumericErrors} onClick={() => void submit()}>{busy ? 'Checking product…' : work.skus.some(row => openingSku(work, row).decision === 'OPEN') ? 'Create product and opening stock' : 'Create product and SKUs'}</button>}</div>
  </div>;
}
