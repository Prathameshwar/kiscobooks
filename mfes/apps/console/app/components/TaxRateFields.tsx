'use client';
import { useCallback, useEffect, useState } from 'react';
import { Button, Notice, SectionHeader, Select } from '@janso/ui';
import { TaxField, TaxReference } from './TaxCommon';
import { assertTaxRow, taxBase, taxRequest } from '../lib/tax-api';
import type { TaxField as Field, TaxRow } from '../lib/tax-masters';
import { taxContexts, type TaxComponent } from '../lib/tax-rate-form';
import type { ServicePage } from '../lib/service-resource';
import { requestFailure } from '../lib/service-call';

export function TaxSeriesPicker({ company, value, disabled, error, onChange, onTouched }: { company: string; value: string | null; disabled?: boolean; error?: string; onChange: (id: string | null, context: string, treatment: string) => void; onTouched?: () => void }) {
  const [ruleId, setRuleId] = useState<string | null>(null), [rule, setRule] = useState<TaxRow | null>(null), [series, setSeries] = useState<TaxRow[]>([]), [problem, setProblem] = useState(''), [loading, setLoading] = useState(false);
  const receiveRule = useCallback((row: TaxRow | null) => setRule(row), []);
  useEffect(() => {
    const controller = new AbortController();
    if (value) taxRequest<TaxRow>({ path: taxBase(company, 'tax-rate-series') + '/' + value, signal: controller.signal }).then(row => { assertTaxRow(row, company, value); if (!controller.signal.aborted) setRuleId(String(row.rule_id)); }).catch(error => { if (!controller.signal.aborted) setProblem(requestFailure(error).message); });
    return () => controller.abort();
  }, [company, value]);
  useEffect(() => {
    const controller = new AbortController(); setSeries([]); setProblem(''); setLoading(!!ruleId);
    if (ruleId) taxRequest<ServicePage<TaxRow>>({ path: taxBase(company, 'tax-rate-series') + '?' + new URLSearchParams({ rule_id: ruleId, limit: '50' }), signal: controller.signal }).then(page => {
      if (!controller.signal.aborted) { setSeries(page.items); setLoading(false); }
    }).catch(error => { if (!controller.signal.aborted) { setProblem(requestFailure(error).message); setLoading(false); } });
    return () => controller.abort();
  }, [company, ruleId]);
  const selected = series.find(row => row.id === value);
  useEffect(() => { if (selected && rule) onChange(selected.id, String(selected.applicability), String(rule.treatment)); }, [selected, rule, onChange]);
  return <><TaxReference company={company} resource="tax-rules" label="Tax rule for rate" value={ruleId} disabled={disabled} required onRecord={receiveRule} onChange={id => { setRuleId(id); onChange(null, '', ''); onTouched?.(); }} />
    <Select label="Rate series" name="series_id" value={value ?? ''} disabled={disabled || loading || !ruleId || !rule} required placeholder={loading ? 'Loading rate series...' : 'Choose a supply context'} options={series.filter(row => typeof row.applicability === 'string').map(row => ({ value: row.id, label: row.applicability === 'INTRA_STATE' ? 'Within a state (CGST + SGST)' : row.applicability === 'INTRA_UT' ? 'Within a union territory (CGST + UTGST)' : 'Between states / territories (IGST)' }))} error={error ?? (problem || undefined)} onChange={id => { const row = series.find(row => row.id === id); onChange(id || null, String(row?.applicability ?? ''), String(rule?.treatment ?? '')); onTouched?.(); }} />
    {ruleId && !loading && !problem && !series.length && <Notice>No rate series exist for this rule. Create its required supply contexts from the Tax rates directory first.</Notice>}
    {rule && !['TAXABLE', 'NIL_RATED'].includes(String(rule.treatment)) && <Notice tone="warning">Exempt and outside-GST rules do not have charged rate series.</Notice>}</>;
}
export function TaxRateFields({ company, fields, components, onChange, context, disabled, errors }: { company: string; fields: Field[]; components: TaxComponent[]; onChange: (value: TaxComponent[]) => void; context: string; disabled?: boolean; errors: Record<string, string> }) {
  function change(index: number, key: string, value: unknown) {
    const next = components.map((row, i) => i === index ? { ...row, [key]: value } : row);
    if (key === 'kind') Object.assign(next[index]!, value === 'PERCENT' ? { amount: null, unit_id: null, currency: null, basis_quantity: null, percentage: '' } : { percentage: null, currency: 'INR', amount: '', basis_quantity: '' });
    onChange(next);
  }
  return <><SectionHeader title="Rate components" description="Enter exact percentages. Fixed compensation cess requires an INR amount and a unit basis." />{errors.components && <Notice tone="danger">{errors.components}</Notice>}
    {!context && <Notice>Choose a rate series to enter its GST components.</Notice>}
    {components.map((row, index) => <div className="janso-flow" key={index}><SectionHeader title={(row.component === 'CESS' ? 'Compensation cess' : row.component) + ' component'} /><div className="janso-form-grid">{fields.filter(field => field.control && !['rate_id', 'position', 'currency'].includes(field.key) && (field.key !== 'kind' || row.component === 'CESS') && (row.kind === 'PERCENT' ? !['amount', 'basis_quantity', 'unit_id'].includes(field.key) : field.key !== 'percentage')).map(field => {
      const options = field.key === 'component' ? { ...field, control: { ...field.control!, choices: (field.control!.choices ?? []).filter(choice => choice.value === row.component) } } : field;
      return <TaxField key={field.key} company={company} field={options} value={row[field.key]} disabled={disabled || field.key === 'component'} error={errors['components.' + index + '.' + field.key]} onChange={value => change(index, field.key, value)} />;
    })}</div>{row.component === 'CESS' && <Button variant="ghost" disabled={disabled} onClick={() => onChange(components.filter((_, i) => i !== index))}>Remove cess component {index + 1}</Button>}</div>)}
    {context && <Button variant="ghost" disabled={disabled || components.length >= 16 || !(taxContexts[context as keyof typeof taxContexts]?.length)} onClick={() => onChange([...components, { component_key: 'CESS_' + (components.length + 1), component: 'CESS', kind: 'PERCENT', percentage: '', rounding_mode: 'HALF_UP', position: components.length }])}>Add compensation cess</Button>}</>;
}
