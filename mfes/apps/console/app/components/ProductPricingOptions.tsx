'use client';
import { Card, CardBody, CardHeader, Notice, ReviewList } from '@janso/ui';
import { configFields, configLabel, configRecord, useConfigRead, type ConfigFieldSet, type ConfigRevision } from '../lib/product-configuration';
import { ConfigurationFailure, ConfigurationLoading } from './ProductConfigurationCommon';

export function ProductPricingOptions({ company, revisionId }: { company: string; revisionId: string }) {
  const root = `/v1/companies/${company}`;
  const revision = useConfigRead<ConfigRevision>(root + '/product-configuration-revisions/' + revisionId, value => { configRecord(value, company, revisionId); });
  const metadata = useConfigRead<ConfigFieldSet>(root + '/entities/catalog.product_pricing_policy/field-set?operation=read', value => { configFields(value, company, 'catalog.product_pricing_policy'); });
  const fields = metadata.data ? configFields(metadata.data, company, 'catalog.product_pricing_policy') : [];
  const items = revision.data ? fields.filter(field => field.visible && field.control && field.display_group === 'pricing_options' && field.key in revision.data!.pricing).map(field => {
    const value = (revision.data!.pricing as Record<string, unknown>)[field.key];
    return { label: configLabel(field), value: field.control!.choices.find(choice => choice.value === value)?.label ?? (value == null ? 'Not readable' : String(value)) };
  }) : [];
  return <Card><CardHeader title="Published pricing options" subtitle="Latest published revision. Inspect effective settings to check a particular date." /><CardBody>
    <ConfigurationFailure failure={revision.failure} retry={revision.refresh} />
    <ConfigurationFailure failure={metadata.failure} retry={metadata.refresh} />
    {revision.loading || metadata.loading ? <ConfigurationLoading /> : !revision.failure && !metadata.failure && (items.length ? <ReviewList items={items} /> : <Notice>No readable pricing options in this revision.</Notice>)}
  </CardBody></Card>;
}
