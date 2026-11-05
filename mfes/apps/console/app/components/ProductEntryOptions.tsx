'use client';
import { Notice } from '@janso/ui';
import { configFields, configRecord, useConfigRead, type ConfigFieldSet, type ConfigRevision, type ConfigValues } from '../lib/product-configuration';
import { ConfigurationFailure, ConfigurationGroupedValues, ConfigurationLoading } from './ProductConfigurationCommon';

export function ProductEntryOptions({ company, revisionId }: { company: string; revisionId: string }) {
  const root = `/v1/companies/${company}`, entity = 'catalog.product_entry_option_policy';
  const revision = useConfigRead<ConfigRevision>(root + '/product-configuration-revisions/' + revisionId, value => { configRecord(value, company, revisionId); });
  const metadata = useConfigRead<ConfigFieldSet>(root + '/entities/' + entity + '/field-set?operation=read', value => { configFields(value, company, entity); });
  return <>
    <ConfigurationFailure failure={revision.failure} retry={revision.refresh} />
    <ConfigurationFailure failure={metadata.failure} retry={metadata.refresh} />
    {revision.loading || metadata.loading ? <ConfigurationLoading /> : !revision.failure && !metadata.failure && revision.data && metadata.data && <>
      <Notice>These options show the latest published revision. Inspect effective settings for a particular date.</Notice>
      <ConfigurationGroupedValues title="Published entry options" fields={configFields(metadata.data, company, entity)} values={revision.data.options as ConfigValues} />
    </>}
  </>;
}
