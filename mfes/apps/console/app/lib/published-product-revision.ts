'use client';
import { useServiceRead } from './service-resource';
import { masterRequest } from './catalog-master-api';
import {
  catalogBase,
  catalogId,
  catalogReceipt,
} from './product-classification';
import type { MasterRow } from './catalog-masters';

/** Resolve a published revision's owner through the existing authorised option catalogue. */
export function usePublishedProductRevision(
  company: string,
  source:
    | 'product-type-revisions'
    | 'inventory-template-revisions'
    | 'attribute-set-revisions',
  value: unknown,
  enabled: boolean,
) {
  const id =
    typeof value === 'string' && catalogId.test(value) ? value : undefined;
  const options = useServiceRead<{
    items: { value: string; parent_id: string | null }[];
  }>(
    enabled && id
      ? catalogBase(company, 'product-configuration/options/' + source) +
          '?value=' +
          id
      : undefined,
    masterRequest,
    (result) => {
      if (
        !Array.isArray(result.items) ||
        !result.items.some(
          (option) =>
            option.value === id &&
            !!option.parent_id &&
            catalogId.test(option.parent_id),
        )
      )
        throw {
          status: 502,
          message: 'Published revision choices could not be verified.',
        };
    },
  );
  const owner = options.data?.items.find(
    (option) => option.value === id,
  )?.parent_id;
  const read = useServiceRead<MasterRow>(
    enabled && id && owner && catalogId.test(owner)
      ? catalogBase(
          company,
          (source === 'product-type-revisions'
            ? 'product-types/'
            : source === 'attribute-set-revisions'
              ? 'attribute-sets/'
              : 'inventory-templates/') +
            owner +
            '/revisions/' +
            id,
        )
      : undefined,
    masterRequest,
    (row) => catalogReceipt(row, company, id),
  );
  return {
    ...read,
    ownerId: owner,
    data:
      read.data && read.data.id === id && read.data.company_id === company
        ? read.data
        : null,
    loading: options.loading || read.loading,
    failure: options.failure ?? read.failure,
    refresh: () => {
      options.refresh();
      read.refresh();
    },
  };
}
