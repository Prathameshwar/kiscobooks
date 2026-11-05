import { COMPANY, FRESH, SOURCE, response, fields } from './product-classification-fixtures';
import type { MasterField } from '../app/lib/catalog-masters';
import type { ServiceRequest } from '../app/lib/service-call';

export const page = { limit: 50, has_more: false, next_cursor: null };
export const groupPath = `/v1/companies/${COMPANY}/item-groups`;
export function drawerResponse(request: ServiceRequest): unknown {
  if (request.path.includes('/products/field-set')) return {
    company_id: COMPANY, source_version: 8, authoring_version: 1, native_bindings: {},
    fields: [...fields('catalog.item', 'create').filter(field => ['sku', 'name', 'base_unit_id', 'sellable', 'purchasable'].includes(field.key)).map(field => ({ ...field, key: field.key === 'sku' ? 'code' : field.key, label: field.key === 'sku' ? 'Product code' : field.key === 'name' ? 'Product name' : field.label })), ...fields('catalog.product_family', 'create').filter(field => ['kind', 'product_type_revision_id'].includes(field.key))],
  };
  if (request.path.includes('/entities/catalog.item_group/field-set')) return { company_id: COMPANY, entity_type: 'catalog.item_group', source_version: 8, fields: ['code', 'name', 'allowed_kind'].map((key, order) => ({ key, order, label: key, source: 'native', visible: true, writable: true, required: true, conditional_access: false } satisfies MasterField)) };
  if (request.path === groupPath && request.method === 'POST') return { ...request.body as object, id: FRESH, company_id: COMPANY, is_active: true, row_version: 1 };
  if (request.path === groupPath + '/' + FRESH) return { id: FRESH, company_id: COMPANY, name: 'Tea group', code: 'TEA', allowed_kind: 'GOODS', is_active: true, row_version: 1 };
  if (request.path.startsWith(groupPath)) return { items: [], page };
  if (request.path.includes('/product-configuration/options/product-type-revisions')) {
    const value = new URL(request.path, 'https://api.invalid').searchParams.get('value') ?? SOURCE;
    return { items: [{ value, parent_id: value === FRESH ? FRESH : SOURCE, label: 'Tea type · revision 1', code: 'TEA' }], page };
  }
  return response(request);
}
