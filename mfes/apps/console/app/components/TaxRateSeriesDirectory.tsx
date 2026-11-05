'use client';
import { Card, CardBody, CardHeader, Select } from '@janso/ui';
import { TaxFailure, TaxReference } from './TaxCommon';
import { useServiceRead, type ServicePage } from '../lib/service-resource';
import { taxBase, taxRequest } from '../lib/tax-api';
import { taxLink, taxSupplyLabel, type TaxRow } from '../lib/tax-masters';

export function TaxRateSeriesDirectory({ company, ruleId, selectedSeries, here, canPublish, onRuleChange, onSeriesChange }: { company: string; ruleId: string | null; selectedSeries: string | null; here: string; canPublish: boolean; onRuleChange: (id: string | null) => void; onSeriesChange: (id: string | null) => void }) {
  const series = useServiceRead<ServicePage<TaxRow>>(ruleId ? taxBase(company, 'tax-rate-series') + '?' + new URLSearchParams({ rule_id: ruleId, limit: '50' }) : undefined, taxRequest);
  return <Card><CardHeader title="Find a rate series" /><CardBody><div className="janso-form-grid"><TaxReference company={company} resource="tax-rules" label="Filter by tax rule" value={ruleId} onChange={onRuleChange} /><Select label="Supply context filter" value={selectedSeries ?? ''} placeholder="All supply contexts" disabled={!ruleId || series.loading} options={(series.data?.items ?? []).map(row => ({ value: row.id, label: taxSupplyLabel(row.applicability) }))} onChange={value => onSeriesChange(value || null)} /></div><TaxFailure failure={series.failure} retry={series.refresh} />{canPublish && selectedSeries && <a className="janso-link" href={taxLink('/tax/rates/new?series_id=' + selectedSeries, here)}>Publish a rate in this series</a>}</CardBody></Card>;
}
