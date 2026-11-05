'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Card, CardBody, CardHeader, ConfirmDialog, DataTable, FormActions, Notice, PageHeader, Pager, ReviewList, SectionHeader, Select, TextField, useFormatters } from '@janso/ui';
import type { components as Api } from '@janso/api-client/catalog';
import { assertTaxReceipt, assertTaxRow, taxBase, taxRequest, useTaxContext, useTaxMetadata } from '../lib/tax-api';
import { taxBody, taxConfig, taxInitial, taxLink, taxReturn, taxSupplyLabel, taxUuid, type TaxRow } from '../lib/tax-masters';
import { initialTaxComponents, taxComponentsBody, taxContexts, type TaxComponent } from '../lib/tax-rate-form';
import { useServiceCommand, useServiceList, useServiceRead, type ServicePage } from '../lib/service-resource';
import { requestFailure, type RequestFailure } from '../lib/service-call';
import { validMasterDate } from '../lib/catalog-masters';
import { TaxFailure, TaxField, TaxNavigation, TaxReference } from './TaxCommon';
import { TaxRateFields } from './TaxRateFields';
import { useAccessDraft } from './AccessCommon';

type Review = { body: Record<string, unknown>; preview?: Api['schemas']['ReleasePreview']; background?: Api['schemas']['ImpactReviewDetail'] };
const contexts = Object.keys(taxContexts), config = taxConfig('rates')!;
export function TaxReleaseEditor({ company, ruleId: initialRule, returnTo }: { company: string; ruleId?: string; returnTo?: string }) {
  const back = taxReturn(returnTo, '/tax/rates'), format = useFormatters(), context = useTaxContext(company), metadata = useTaxMetadata(company, config, 'create');
  const componentMetadata = useTaxMetadata(company, { ...config, entity: 'catalog.tax_rate_component' }, 'create');
  const [ruleId, setRuleId] = useState<string | null>(initialRule ?? null), [rule, setRule] = useState<TaxRow | null>(null), [values, setValues] = useState<Record<string, unknown>>({}), [reason, setReason] = useState(''), [mode, setMode] = useState('preview');
  const [parts, setParts] = useState<Record<string, TaxComponent[]>>({}), [previous, setPrevious] = useState<Record<string, TaxRow>>({}), [replace, setReplace] = useState<Record<string, boolean>>({}), [loadingPrevious, setLoadingPrevious] = useState(false), [previousFailure, setPreviousFailure] = useState<RequestFailure | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({}), [failure, setFailure] = useState<RequestFailure | null>(null), [dirty, setDirty] = useState(false), [review, setReview] = useState<Review | null>(null), [saved, setSaved] = useState(false), [checking, setChecking] = useState(false), [reload, setReload] = useState(false);
  const command = useServiceCommand(taxRequest, 'tax publication'), reviewCommand = useServiceCommand(taxRequest, 'tax impact review'), busy = useRef(false), form = useRef<HTMLFormElement>(null);
  const series = useServiceRead<ServicePage<TaxRow>>(ruleId ? taxBase(company, 'tax-rate-series') + '?' + new URLSearchParams({ rule_id: ruleId, limit: '50' }) : undefined, taxRequest, page => { if (!Array.isArray(page.items) || page.page.has_more) throw { status: 502, message: 'The supply contexts could not be verified.' }; page.items.forEach(row => { assertTaxRow(row, company); if (row.rule_id !== ruleId || !contexts.includes(String(row.applicability))) throw { status: 502, message: 'The rate series does not belong to this rule.' }; }); });
  const receiveRule = useCallback((row: TaxRow | null) => setRule(row), []);
  useEffect(() => { if (context.data) { setValues(taxInitial(config, context.data.business_date)); setDirty(false); } }, [context.data]);
  useEffect(() => { setParts(Object.fromEntries(contexts.map(key => [key, initialTaxComponents(key, rule?.treatment === 'NIL_RATED')]))); }, [ruleId, rule?.treatment]);
  useEffect(() => {
    const controller = new AbortController(); setPrevious({}); setReplace({}); setLoadingPrevious(false); setPreviousFailure(null);
    if (series.data && validMasterDate(values.valid_from)) {
      setLoadingPrevious(true);
      Promise.all(series.data.items.map(async row => { const page = await taxRequest<ServicePage<TaxRow>>({ path: taxBase(company, 'tax-rates') + '?' + new URLSearchParams({ series_id: row.id, as_of: String(values.valid_from), limit: '50' }), signal: controller.signal }); if (!Array.isArray(page.items) || page.items.length > 1 || page.page.has_more) throw { status: 502, message: 'The existing rate period could not be verified.' }; page.items.forEach(rate => { assertTaxRow(rate, company); if (rate.series_id !== row.id || !Number.isSafeInteger(rate.row_version) || Number(rate.row_version) < 1) throw { status: 502, message: 'The existing rate version could not be verified.' }; }); return [String(row.applicability), page.items[0]] as const; })).then(rows => { if (!controller.signal.aborted) { setPrevious(Object.fromEntries(rows.filter(([, row]) => !!row))); setLoadingPrevious(false); } }).catch(error => { if (!controller.signal.aborted) { setPreviousFailure(requestFailure(error)); setLoadingPrevious(false); } });
    }
    return () => controller.abort();
  }, [company, series.data, values.valid_from]);
  const pending = checking || command.pending || reviewCommand.pending, uncertain = command.uncertain || reviewCommand.uncertain, locked = pending || uncertain || !!review, guard = useAccessDraft(dirty || !!review || uncertain, pending);
  const fields = metadata.data?.fields ?? [], complete = context.data?.country_code === 'IN' && ['TAXABLE', 'NIL_RATED'].includes(String(rule?.treatment)) && contexts.every(key => series.data?.items.filter(row => row.applicability === key).length === 1) && ['series_id', 'valid_from', 'source_reference', 'source_url', 'source_sha256'].every(key => fields.some(field => field.key === key && field.visible && field.writable && !field.conditional_access));
  const readFailure = metadata.failure ?? componentMetadata.failure ?? context.failure ?? series.failure ?? previousFailure;
  function change(key: string, value: unknown) { setValues(current => ({ ...current, [key]: value })); setDirty(true); setErrors({}); setFailure(null); }
  function focusErrors() { setTimeout(() => form.current?.querySelector<HTMLElement>('[aria-invalid="true"], :invalid')?.focus(), 0); }
  async function background(body: Record<string, unknown>) {
    const result = await reviewCommand.execute<Api['schemas']['ImpactReviewDetail']>({ path: taxBase(company, 'tax-impact-reviews'), method: 'POST', body }, row => verifyReport(row, body));
    if (result) setReview({ body, background: result });
  }
  function verifyReport(row: Api['schemas']['ImpactReviewDetail'], body: Record<string, unknown>, id?: string) {
    if (!taxUuid.test(row.id) || id && row.id !== id || !['PENDING', 'COMPLETE', 'STALE', 'FAILED'].includes(row.status) || row.change_count !== 3 || row.change_reason !== body.change_reason || row.policy_generation !== body.expected_generation || row.source_version !== body.expected_source_version || row.business_date !== context.data?.business_date || !Number.isSafeInteger(row.blocking_count) || row.blocking_count < 0) throw { status: 502, message: 'The reviewed change could not be verified. Retry the same request.' };
  }
  async function submit() {
    if (!complete || loadingPrevious || readFailure || busy.current || saved) return;
    if (reviewCommand.uncertain && review) { await background(review.body); return; }
    const allErrors: Record<string, string> = {};
    if (!reason.trim() || reason.trim().length > 500 || /[\x00-\x1f\x7f]/.test(reason)) allErrors.reason = 'Enter a printable reason within 500 characters.';
    const changes = contexts.map(key => {
      const selected = series.data!.items.find(row => row.applicability === key)!, predecessor = previous[key];
      const result = taxBody(config, fields, { ...values, series_id: selected.id }, context.data!, replace[key] ? predecessor : undefined, !!replace[key]);
      const components = taxComponentsBody(parts[key] ?? [], componentMetadata.data?.fields ?? [], key, String(rule?.treatment)); result.body.components = components.components;
      Object.assign(allErrors, result.errors); Object.entries(components.errors).forEach(([field, message]) => { allErrors[key + '.' + field] = message; });
      if (predecessor && !replace[key]) allErrors[key + '.replace'] = 'An existing rate covers this start date. Confirm its replacement or choose another date.';
      return { kind: 'RATE', key, definition: result.body };
    });
    setErrors(allErrors); if (Object.keys(allErrors).length) { focusErrors(); return; }
    const body = { expected_generation: context.data!.policy_generation, expected_source_version: context.data!.source_version, change_reason: reason.trim(), changes };
    busy.current = true; setChecking(true); setFailure(null);
    try {
      if (mode === 'background') { setReview({ body }); await background(body); }
      else { const result = await taxRequest<Api['schemas']['ReleasePreview']>({ path: taxBase(company, 'tax-release-previews'), method: 'POST', body }); if (!result.valid || !result.preview_token || result.policy_generation !== body.expected_generation || result.source_version !== body.expected_source_version || !Array.isArray(result.affected_item_ids) || !Array.isArray(result.checked_dates)) throw { status: 502, message: 'The publication preview could not be verified.' }; setReview({ body, preview: result }); }
    } catch (error) { setFailure(requestFailure(error, 'tax publication preview')); } finally { busy.current = false; setChecking(false); }
  }
  async function refreshReport() {
    if (!review?.background || busy.current) return; busy.current = true; setChecking(true); setFailure(null);
    try { const row = await taxRequest<Api['schemas']['ImpactReviewDetail']>({ path: taxBase(company, 'tax-impact-reviews') + '/' + review.background.id }); verifyReport(row, review.body, review.background.id); setReview({ ...review, background: row }); } catch (error) { setFailure(requestFailure(error)); } finally { busy.current = false; setChecking(false); }
  }
  async function publish() {
    if (!review || !(review.preview || review.background?.status === 'COMPLETE' && review.background.blocking_count === 0)) return;
    const result = await command.execute<TaxRow>({ path: taxBase(company, 'tax-releases'), method: 'POST', body: { ...review.body, ...(review.preview ? { preview_token: review.preview.preview_token } : { impact_review_id: review.background!.id }) } }, assertTaxReceipt);
    if (result) { setSaved(true); setDirty(false); setReview(null); }
  }
  function reset() { setReview(null); command.clear(); reviewCommand.clear(); setFailure(null); }
  const reviewedDefinition = review ? (review.body.changes as { definition: Record<string, unknown> }[])[0]!.definition : null;
  const writeFailure = command.failure ?? reviewCommand.failure;
  return <div className="janso-page"><TaxNavigation title="Coordinated rate publication" back={back} onLeave={guard.leave} /><PageHeader title="Coordinated rate publication" lede="Review and publish the three GST supply contexts together for one tax rule." />
    <TaxFailure failure={readFailure} retry={() => { metadata.refresh(); componentMetadata.refresh(); context.refresh(); series.refresh(); }} /><TaxFailure failure={writeFailure ?? failure} write={!!writeFailure} retry={(writeFailure?.status === 409 || failure?.status === 409) && !uncertain ? () => setReload(true) : undefined} />
    {saved ? <Notice tone="success">All three rate definitions published successfully. <a className="janso-link" href={taxLink('/tax/rates?rule_id=' + ruleId, back)}>View published rates</a></Notice> : <form ref={form} noValidate onSubmit={event => { event.preventDefault(); void submit(); }}><Card><CardBody><div className="janso-flow"><TaxReference company={company} resource="tax-rules" label="Tax rule" value={ruleId} required disabled={locked} onRecord={receiveRule} onChange={id => { setRuleId(id); setDirty(true); setErrors({}); setFailure(null); }} />
    {rule && !['TAXABLE', 'NIL_RATED'].includes(String(rule.treatment)) && <Notice tone="warning">Choose a taxable or nil-rated rule. Exempt and outside-GST rules do not have charged rate series.</Notice>}
    {ruleId && !series.loading && contexts.some(key => !series.data?.items.some(row => row.applicability === key)) && <Notice tone="warning">This rule needs all three supply contexts before publication. <a className="janso-link" onClick={guard.leave} href={taxLink('/tax/rates/series/new?rule_id=' + ruleId, back)}>Create missing rate series</a></Notice>}
    <TextField label="Reason for publication" value={reason} required maxLength={500} disabled={locked} error={errors.reason} onChange={event => { setReason(event.target.value); setDirty(true); }} /><div className="janso-form-grid">{fields.filter(field => field.source === 'native' && field.control && field.key !== 'series_id').map(field => <TaxField key={field.key} company={company} field={field} value={values[field.key]} error={errors[field.key]} disabled={locked} onChange={value => change(field.key, value)} />)}</div>
    {loadingPrevious && <p role="status">Checking existing rate periods...</p>}{contexts.map(key => <section key={key} aria-label={taxSupplyLabel(key)} className="janso-flow"><SectionHeader title={taxSupplyLabel(key)} />{previous[key] && <><Notice>Existing rate: {format.date(String(previous[key]!.valid_from))} through {previous[key]!.valid_to ? format.date(String(previous[key]!.valid_to)) : 'open ended'}. Replacement shortens that period to the day before the new start date.</Notice><Select label={'Replace existing rate: ' + taxSupplyLabel(key)} value={replace[key] ? 'yes' : 'no'} options={[{ value: 'no', label: 'Keep existing rate' }, { value: 'yes', label: 'Replace from the chosen future date' }]} disabled={locked} error={errors[key + '.replace']} onChange={value => { setReplace(current => ({ ...current, [key]: value === 'yes' })); setDirty(true); }} /></>}<TaxRateFields company={company} fields={componentMetadata.data?.fields ?? []} components={parts[key] ?? []} context={key} disabled={locked || !complete} errors={Object.fromEntries(Object.entries(errors).filter(([field]) => field.startsWith(key + '.')).map(([field, message]) => [field.slice(key.length + 1), message]))} onChange={rows => { setParts(current => ({ ...current, [key]: rows })); setDirty(true); }} /></section>)}
    <Select label="Impact review" value={mode} disabled={locked} options={[{ value: 'preview', label: 'Review now' }, { value: 'background', label: 'Background review for larger changes' }]} onChange={value => { setMode(value); setDirty(true); }} /><Notice>Official evidence is required. The service checks product impact, exact percentages and consistency across the three supply contexts before publishing.</Notice>{!complete && !metadata.loading && <Notice tone="warning">Complete field access, an Indian company and all three supply contexts are required.</Notice>}
    {Object.entries(errors).filter(([key]) => !fields.some(field => field.key === key) && key !== 'reason' && !contexts.some(context => key.startsWith(context + '.'))).map(([key, message]) => <Notice key={key} tone="danger">{message}</Notice>)}
    </div></CardBody><FormActions cancel={{ href: back, onClick: guard.leave }}><Button type="submit" loading={pending} disabled={!complete || loadingPrevious || !!readFailure || !!review && !reviewCommand.uncertain || command.blocked || reviewCommand.blocked && !reviewCommand.uncertain}>{reviewCommand.uncertain ? 'Retry same impact review' : 'Review coordinated publication'}</Button></FormActions></Card></form>}
    {review && <Card><CardHeader title="Review coordinated publication" /><CardBody><ReviewList items={[{ label: 'Reason', value: String(review.body.change_reason) }, { label: 'Supply contexts', value: 'Three rate definitions' }, { label: 'Effective from', value: format.date(String(reviewedDefinition!.valid_from)) }, { label: 'Official reference', value: String(reviewedDefinition!.source_reference) }, { label: 'Document URL', value: String(reviewedDefinition!.source_url) }, { label: 'Document SHA-256', value: String(reviewedDefinition!.source_sha256) }, { label: 'Affected products', value: String(review.preview?.affected_item_ids.length ?? review.background?.item_count ?? 'Checking') }]} />{(review.body.changes as { key: string; definition: { components: { component_key: string; kind: string; percentage?: string; amount?: string; basis_quantity?: string }[] } }[]).map(change => <section key={change.key}><SectionHeader title={taxSupplyLabel(change.key)} /><ReviewList items={change.definition.components.map(row => ({ label: row.component_key, value: row.kind === 'PERCENT' ? row.percentage + '%' : row.amount + ' INR / ' + row.basis_quantity + ' units' }))} /></section>)}
    {review.background && <><Notice tone={review.background.status === 'FAILED' || review.background.status === 'STALE' || review.background.blocking_count ? 'warning' : 'info'}>{review.background.status === 'PENDING' ? 'Review is queued. You can refresh its progress. If it stays queued, ask your administrator to check review processing.' : review.background.status === 'COMPLETE' ? 'Review complete.' : 'This review cannot be published. Reload the current configuration and review again.'} {review.background.checked_count} products checked; {review.background.blocking_count} blocking findings.</Notice><Button variant="ghost" loading={checking} onClick={() => void refreshReport()}>Refresh review progress</Button>{review.background.finding_count > 0 && <TaxReleaseFindings key={review.background.row_version} company={company} id={review.background.id} />}</>}
    <div className="janso-flow"><Button loading={command.pending} disabled={pending || !!command.failure && !command.uncertain || !review.preview && !(review.background?.status === 'COMPLETE' && review.background.blocking_count === 0)} onClick={() => void publish()}>{command.uncertain ? 'Retry same coordinated publication' : 'Publish all three rates'}</Button><Button variant="ghost" disabled={pending || uncertain} onClick={reset}>Edit before publishing</Button></div></CardBody></Card>}
    <ConfirmDialog open={reload} title="Reload current tax configuration?" confirmLabel="Reload and review" onCancel={() => setReload(false)} onConfirm={() => { setReload(false); reset(); context.refresh(); metadata.refresh(); componentMetadata.refresh(); series.refresh(); }}>Your draft will be replaced with current configuration. Review the dates and evidence again.</ConfirmDialog>{guard.confirmation}
  </div>;
}
function TaxReleaseFindings({ company, id }: { company: string; id: string }) {
  const list = useServiceList<Api['schemas']['ImpactFindingListItem']>(taxBase(company, 'tax-impact-reviews') + '/' + id + '/findings', '', taxRequest), format = useFormatters();
  return <><TaxFailure failure={list.failure} retry={list.first} /><DataTable caption="Tax publication impact findings" rows={list.data?.items ?? []} rowId={row => row.id} loading={list.loading} columns={[{ key: 'item_id', header: 'Product', type: 'custom', render: row => row.item_id }, { key: 'as_of', header: 'Effective on', type: 'custom', render: row => format.date(row.as_of) }, { key: 'direction', header: 'Direction', type: 'custom', render: row => row.direction === 'SALE' ? 'Sale' : 'Purchase' }, { key: 'status', header: 'Finding', type: 'custom', render: row => row.status.replaceAll('_', ' ') + ': ' + row.missing.join(', ') }, { key: 'blocking', header: 'Blocks publication', type: 'custom', render: row => row.blocking ? 'Yes' : 'No' }]} /><Pager count={list.data?.items.length ?? 0} limit={list.limit} hasPrevious={list.hasPrevious} hasNext={!!list.data?.page.has_more} onPrevious={list.previous} onNext={list.next} onLimitChange={list.setLimit} busy={list.loading} noun="finding" /></>;
}
