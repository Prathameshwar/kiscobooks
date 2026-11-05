'use client';
import {
  accountingBack,
  accountingLink,
  accountingResource,
} from './accounting-configuration-resources';
import { catalogBack } from './product-classification';
import type { SearchSelectLoader } from '@janso/ui';
import { downloadProductImport, productImportRequest } from './product-import';
import {
  downloadPartyImport,
  partyImportRequest,
  partyImportResources,
} from './party-import';

export const productImportProfile = {
  definition: 'products',
  title: 'Import products',
  label: 'Product',
  plural: 'products',
  singular: 'product',
  path: '/masters/items/import',
  directory: '/masters/items',
  directoryLabel: 'Products',
  defaultResource: 'product_family',
  resources: [
    { value: 'product_family', label: 'Products with their first SKU' },
    { value: 'item', label: 'Update existing SKUs' },
  ],
  request: productImportRequest,
  download: downloadProductImport,
  back: catalogBack,
  templateParameter: 'kind',
  defaultParameter: 'GOODS',
  parameterLabel: 'Product kind',
  parameters: [
    { value: 'GOODS', label: 'Goods' },
    { value: 'SERVICE', label: 'Services' },
  ],
  parameterResource: 'product_family',
  createOnlyResources: [] as readonly string[],
  detailsRequireManage: false,
  readOnlyMessage:
    'Read-only import access. You can review your history and download available files. Starting or changing an import requires product import management access.',
  preparation:
    'Use one stable row key and group key per product. A new product family includes its first SKU. Additional SKU imports refer to an existing family.',
  lifecycle: 'New products keep their normal draft and activation workflow.',
  success:
    'Product import completed successfully. Review the results below or return to the product directory.',
  destination: (_resource: string, _id: string, _back: string): string | null =>
    null,
};
export type MasterImportProfile = typeof productImportProfile & {
  readyProducts?: boolean;
  historyDefinitions?: readonly string[];
  updateOnlyResources?: readonly string[];
  /** Resources whose file may also carry optional opening-balance columns. */
  openingResources?: readonly string[];
  templateContext?: {
    defaults: Record<string, string>;
    loadOptions: (
      company: string,
      field: string,
      values: Record<string, string>,
      args: Parameters<SearchSelectLoader>[0],
    ) => ReturnType<SearchSelectLoader>;
  };
};

export const simpleProductImportProfile: MasterImportProfile = {
  ...productImportProfile,
  definition: 'simple_products',
  defaultResource: 'simple_product_create',
  resources: [{ value: 'simple_product_create', label: 'New products' }],
  parameterResource: 'simple_product_create',
  parameterLabel: 'Type',
  createOnlyResources: ['simple_product_create'],
  readyProducts: true,
  historyDefinitions: ['simple_products', 'products'],
  preparation:
    'One product per row. Enter a name and base unit code. Leave product code blank to generate a 10-character code. Blank group uses Default. Use separate Goods and Services templates; prices, tax, Brand, Model, Barcode and opening columns follow your current configuration. Enter barcode values as text to preserve leading zeroes; a blank format uses CODE128.',
  lifecycle:
    'Products become active automatically. Goods opening stock is posted using purchase price × opening quantity. Services have no opening stock.',
  success:
    'Import complete. All products are active and ready, and any opening stock has been posted.',
};

export function partyImportProfile(supplier: boolean): MasterImportProfile {
  const plural = supplier ? 'suppliers' : 'parties';
  return {
    definition: 'parties',
    title: 'Import ' + plural,
    label: supplier ? 'Supplier' : 'Party',
    plural,
    singular: supplier ? 'supplier' : 'party',
    path: '/accounting/' + plural + '/import',
    directory: '/accounting/' + plural,
    directoryLabel: supplier ? 'Suppliers' : 'Parties',
    // A party is only ever created with its role and ledger account, so the page opens on the ready resources.
    defaultResource: supplier ? 'supplier' : 'customer',
    resources: partyImportResources.filter(
      (resource) => !supplier || resource.value !== 'customer',
    ),
    request: partyImportRequest,
    download: downloadPartyImport,
    back: accountingBack,
    templateParameter: 'role',
    defaultParameter: supplier ? 'SUPPLIER' : 'CUSTOMER',
    parameterLabel: 'Party role',
    parameters: supplier
      ? [{ value: 'SUPPLIER', label: 'Supplier' }]
      : [
          { value: 'CUSTOMER', label: 'Customer' },
          { value: 'SUPPLIER', label: 'Supplier' },
        ],
    parameterResource: 'party_role',
    createOnlyResources: ['customer', 'supplier'],
    // A plain party row can no longer be created (a party always arrives with its role and ledger account).
    updateOnlyResources: ['party'],
    openingResources: ['customer', 'supplier'],
    detailsRequireManage: true,
    readOnlyMessage:
      'Read-only import access. You can review retained import summaries. Detailed records, downloads and changes require party management access as well as Accounting import access.',
    preparation:
      'Use one stable row key and group key per party. Ready-to-use suppliers and customers create and activate the identity, its matching role and its ledger account together. Related records can reference staged party IDs with $ref.',
    lifecycle:
      'Ready-to-use suppliers and customers become active together with their role and ledger account. Plain party rows can only update, activate or deactivate an existing identity; activating a party role also creates its ledger account. Related-record imports retain their normal lifecycle.',
    success:
      'Party import completed successfully. Review each imported identity and its roles. Opening balances in the file are held for Account and party openings; nothing is posted.',
    destination: (resource, id, back) => {
      const path = ['supplier', 'customer'].includes(resource)
        ? 'parties'
        : resource === 'party'
          ? 'parties'
          : resource
              .replaceAll('_', '-')
              .replace(/y$/, 'ie')
              .replace(/address$/, 'addresse') + 's';
      return accountingResource(path)
        ? accountingLink('/accounting/' + path + '/' + id, back)
        : null;
    },
  };
}
