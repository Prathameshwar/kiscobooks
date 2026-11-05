'use client';
import type { MasterImportProfile } from './master-import-profiles';
import { masterRequest } from './catalog-master-api';
import { catalogId } from './product-classification';

export function productImportContext(
  today: string,
): NonNullable<MasterImportProfile['templateContext']> {
  return {
    defaults: { as_of: today },
    async loadOptions(company, field, values, { q, cursor, signal }) {
      const source =
        field === 'product_type_revision_id'
          ? 'product-type-revisions'
          : field === 'group_id'
            ? 'groups'
            : null;
      if (!source) throw new Error('Unsupported product template choice.');
      const params = new URLSearchParams({
        q,
        kind: values.kind ?? 'GOODS',
        limit: '25',
      });
      if (cursor) params.set('cursor', cursor);
      const page = await masterRequest<{
        items: { value: string; label: string }[];
        page: { next_cursor: string | null };
      }>({
        path: `/v1/companies/${company}/product-configuration/options/${source}?${params}`,
        signal,
      });
      if (
        !Array.isArray(page.items) ||
        !page.page ||
        page.items.some(
          (item) =>
            !catalogId.test(item.value) || typeof item.label !== 'string',
        ) ||
        (page.page.next_cursor !== null &&
          typeof page.page.next_cursor !== 'string')
      )
        throw new Error('Product template choices could not be verified.');
      return {
        items: page.items.map((item) => ({
          id: item.value,
          label: item.label,
        })),
        nextCursor: page.page.next_cursor,
      };
    },
  };
}
