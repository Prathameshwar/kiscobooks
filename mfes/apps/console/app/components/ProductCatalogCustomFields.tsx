'use client';
import { CustomFields, businessToday, useDisplayConfig } from '@janso/ui';
import type { MasterField } from '../lib/catalog-masters';
import { masterCustomFields } from '../lib/catalog-masters';
import { masterRequest } from '../lib/catalog-master-api';
export function ProductCatalogCustomFields({
  company,
  fields,
  values,
  creating = false,
  disabled = false,
  errors = {},
  onChange,
}: {
  company: string;
  fields: readonly MasterField[];
  values: Record<string, unknown>;
  creating?: boolean;
  disabled?: boolean;
  errors?: Record<string, string>;
  onChange: (values: Record<string, unknown>) => void;
}) {
  const display = useDisplayConfig();
  return (
    <CustomFields
      fields={masterCustomFields(fields)}
      values={(values.custom_fields as Record<string, unknown>) ?? {}}
      nativeValues={values}
      creating={creating}
      disabled={disabled}
      currencies={display.currency ? [display.currency] : []}
      errors={errors}
      onChange={onChange}
      loadOptions={(source, parent) =>
        async ({ q, cursor, signal }) => {
          const params = new URLSearchParams({
            limit: '50',
            as_of: businessToday(display.timezone),
          });
          if (q.trim().length >= 2) params.set('q', q.trim());
          if (cursor) params.set('cursor', cursor);
          if (parent) params.set('parent_id', parent);
          const page = await masterRequest<{
            items: { value: string; label: string; code: string }[];
            page: { has_more: boolean; next_cursor: string | null };
          }>({
            path: `/v1/companies/${company}/option-sources/${encodeURIComponent(source)}?${params}`,
            signal,
          });
          return {
            items: page.items.map((option) => ({
              id: option.value,
              label: option.label,
              meta: option.code,
            })),
            nextCursor: page.page.has_more ? page.page.next_cursor : null,
          };
        }}
    />
  );
}
