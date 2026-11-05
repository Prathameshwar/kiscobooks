'use client';
import { useCallback, useEffect, useState } from 'react';
import { Button, Card, CardBody, FormActions, Notice, PageHeader, Select, TextField } from '@janso/ui';
import { useServiceCommand, useServiceRead } from '../lib/service-resource';
import { assertTaxReceipt, assertTaxRow, taxBase, taxRequest } from '../lib/tax-api';
import { taxLink, taxReturn, taxUuid, type TaxRow } from '../lib/tax-masters';
import { TaxFailure, TaxNavigation, TaxReference } from './TaxCommon';
import { useAccessDraft } from './AccessCommon';
import type { components } from '@janso/api-client/catalog';

export function TaxSetup({ company, ruleId, applicability = false, returnTo }: { company: string; ruleId?: string; applicability?: boolean; returnTo?: string }) {
  const [values, setValues] = useState({ rule_id: ruleId ?? '', applicability: 'INTRA_STATE', code: '', match_kind: 'EXACT' }), [rule, setRule] = useState<TaxRow | null>(null), [dirty, setDirty] = useState(false), [errors, setErrors] = useState<Record<string, string>>({}), [saved, setSaved] = useState<TaxRow | null>(null);
  const entity = applicability ? 'catalog.tax_rule_applicability' : 'catalog.tax_rate_series', resource = applicability ? 'tax-rule-applicabilities' : 'tax-rate-series';
  const metadata = useServiceRead<components['schemas']['FieldSet']>(taxBase(company, 'entities/' + entity + '/field-set') + '?operation=create', taxRequest, value => { if (value.company_id !== company || value.entity_type !== entity || !Array.isArray(value.fields)) throw { status: 502, message: 'Tax form fields could not be verified.' }; });
  const command = useServiceCommand(taxRequest, 'tax service'), guard = useAccessDraft(dirty || command.uncertain, command.pending), back = taxReturn(returnTo, ruleId ? '/tax/rules/' + ruleId : '/tax/rates');
  const receiveRule = useCallback((row: TaxRow | null) => setRule(row), []), blocked = command.pending || command.uncertain;
  const required = applicability ? ['rule_id', 'code_system', 'code', 'match_kind'] : ['rule_id', 'applicability'];
  const complete = required.every(key => metadata.data?.fields.some(field => field.key === key && field.visible && field.writable && !field.conditional_access));
  async function submit() {
    if (!complete || !rule || command.pending || saved) return;
    const next: Record<string, string> = {};
    if (!taxUuid.test(values.rule_id)) next.rule_id = 'Choose an available tax rule.';
    if (applicability && !(rule.item_kind === 'SERVICE' ? values.match_kind === 'PREFIX' ? /^99\d{2}(?:\d{2})?$/ : /^99\d{4}$/ : /^(?!99)\d{4}(?:\d{2}){0,2}$/).test(values.code)) next.code = 'Enter a supported HSN/SAC code for the rule product kind.';
    setErrors(next); if (Object.keys(next).length) return;
    const body = applicability ? { rule_id: values.rule_id, code_system: rule.item_kind === 'SERVICE' ? 'SAC' : 'HSN', code: values.code, match_kind: values.match_kind } : { rule_id: values.rule_id, applicability: values.applicability };
    const result = await command.execute<TaxRow>({ path: taxBase(company, resource), method: 'POST', body }, assertTaxReceipt);
    if (result) { setSaved(result); setDirty(false); }
  }
  useEffect(() => { if (command.failure?.fields) setErrors(command.failure.fields); }, [command.failure]);
  const title = applicability ? 'New classification applicability' : 'New rate series';
  return <div className="janso-page"><TaxNavigation title={title} back={back} onLeave={guard.leave} /><PageHeader title={title} lede={applicability ? 'Restrict the rule to a supported classification code or prefix.' : 'Create one supply context for an existing taxable or nil-rated tax rule.'} /><TaxFailure failure={metadata.failure ?? command.failure} write={!!command.failure} retry={command.failure?.status === 409 ? () => { command.clear(); metadata.refresh(); } : metadata.failure ? metadata.refresh : undefined} />
    {metadata.loading ? <p role="status">Loading tax setup...</p> : metadata.failure ? null : saved ? <Card><CardBody><Notice tone="success">{applicability ? 'Classification applicability added.' : 'Rate series created.'}</Notice><div className="janso-flow">{!applicability && <a className="janso-btn janso-btn--primary" href={taxLink('/tax/rates/new?series_id=' + saved.id, back)}>Publish the first rate</a>}<a className="janso-link" href={back}>Return to previous page</a></div></CardBody></Card> : <form noValidate onSubmit={event => { event.preventDefault(); void submit(); }}><Card><CardBody><div className="janso-form-grid">
      <TaxReference company={company} resource="tax-rules" label="Tax rule" value={values.rule_id || null} required disabled={blocked || !!ruleId || !complete} error={errors.rule_id} onRecord={receiveRule} onChange={id => { setValues({ ...values, rule_id: id ?? '', code: '' }); setDirty(true); }} />
      {applicability ? <><TextField label={rule?.item_kind === 'SERVICE' ? 'SAC code' : 'HSN code'} required value={values.code} disabled={blocked || !complete} error={errors.code} maxLength={8} onChange={event => { setValues({ ...values, code: event.target.value }); setDirty(true); }} /><Select label="Match kind" value={values.match_kind} disabled={blocked || !complete} options={[{ value: 'EXACT', label: 'Exact code' }, { value: 'PREFIX', label: 'Code prefix' }]} onChange={value => { setValues({ ...values, match_kind: value }); setDirty(true); }} /></> : <Select label="Supply context" value={values.applicability} disabled={blocked || !complete} options={[{ value: 'INTRA_STATE', label: 'Within a state' }, { value: 'INTRA_UT', label: 'Within a union territory' }, { value: 'INTER_STATE', label: 'Between states / territories' }]} onChange={value => { setValues({ ...values, applicability: value }); setDirty(true); }} />}
    </div>{!complete && <Notice tone="warning">Your field access does not allow all required inputs.</Notice>}{!applicability && rule && !['TAXABLE', 'NIL_RATED'].includes(String(rule.treatment)) && <Notice tone="warning">Exempt and outside-GST rules do not have charged rate series.</Notice>}</CardBody><FormActions cancel={{ href: back, onClick: guard.leave }}><Button type="submit" loading={command.pending} disabled={!complete || !rule || !applicability && !['TAXABLE', 'NIL_RATED'].includes(String(rule.treatment)) || !!command.failure && command.failure.status !== 422 && !command.uncertain}>{command.uncertain ? 'Retry same save' : applicability ? 'Add applicability' : 'Create rate series'}</Button></FormActions></Card></form>}{guard.confirmation}
  </div>;
}
