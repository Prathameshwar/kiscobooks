'use client';
import { useEffect, useState } from 'react';
import { masterRequest } from './catalog-master-api';
import { catalogId } from './product-classification';

const resources: Record<string, string> = {
  'product-types': 'product-types', warehouses: 'warehouses', units: 'units',
  item_groups: 'item-groups', brands: 'brands', brand_series: 'brand-series',
  manufacturers: 'manufacturers', manufacturer_sites: 'manufacturer-sites',
  category_schemes: 'category-schemes', item_categories: 'item-categories',
  attribute_definitions: 'attribute-definitions', attribute_options: 'attribute-options',
  pack_types: 'pack-types', tax_classifications: 'tax-classifications', tax_rules: 'tax-rules',
};
const parents: Record<string, string> = { brand_series: 'brand_id', manufacturer_sites: 'manufacturer_id', item_categories: 'scheme_id', attribute_options: 'definition_id' };
const configuration = new Set(['product-type-revisions', 'inventory-template-revisions', 'identifier-profiles', 'warranty-revisions', 'return-policy-revisions', 'handling-revisions']);
type RecordLabel = { id: string; company_id: string; name?: string; code?: string; description?: string; [key: string]: unknown };

export function useAdvancedReference(company: string, resource: string, value: string, parent?: string, selected?: string) {
  const key = JSON.stringify([company, resource, value, parent]);
  const [resolved, setResolved] = useState<{ key: string; label: string } | null>(null);
  useEffect(() => {
    if (!value || selected || resolved?.key === key) return;
    const controller = new AbortController();
    const unavailable = () => { if (!controller.signal.aborted) setResolved({ key, label: 'Selection unavailable' }); };
    if (!catalogId.test(value) || (!resources[resource] && !configuration.has(resource))) { unavailable(); return; }
    const root = `/v1/companies/${company}/`;
    const path = configuration.has(resource)
      ? root + `product-configuration/options/${resource}?` + new URLSearchParams({ value, limit: '1' })
      : root + resources[resource] + '/' + value;
    masterRequest<RecordLabel | { items: { value: string; label: string }[] }>({ path, signal: controller.signal }).then(result => {
      if (controller.signal.aborted) return;
      let label: string | undefined;
      if (configuration.has(resource)) {
        if ('items' in result && Array.isArray(result.items)) label = result.items.find(row => row.value === value)?.label;
      }
      else {
        const row = result as RecordLabel;
        if (row.id !== value || row.company_id !== company || (parent && parents[resource] && row[parents[resource]] !== parent)) { unavailable(); return; }
        label = row.name || row.description || row.code;
      }
      setResolved({ key, label: label || 'Selection unavailable' });
    }).catch(unavailable);
    return () => controller.abort();
  }, [company, resource, value, parent, selected, key, resolved?.key]);
  return { label: selected || (resolved?.key === key ? resolved.label : 'Loading selection…'),
    remember: (label: string, nextValue: string = value) => setResolved({ key: JSON.stringify([company, resource, nextValue, parent]), label }) };
}
