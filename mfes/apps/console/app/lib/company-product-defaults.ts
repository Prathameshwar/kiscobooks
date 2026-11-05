import type { components as CatalogComponents } from '@janso/api-client/catalog';
import { companyCall } from './company-api';
import { trackingId } from './stock-tracking-resources';

type Master = CatalogComponents['schemas']['ProductTypeListItem'] & CatalogComponents['schemas']['GroupListItem'];
type Page = { items: Master[] };
type Revision = CatalogComponents['schemas']['TypeRevisionListItem'];
const pending = () => ({ status: 503, code: 'product_defaults_pending', message: 'Default product type and group are still being prepared. Retry the remaining steps.' });
const review = () => ({ status: 409, message: 'Existing product defaults need review in Product types or Product groups. Their configuration has been preserved.' });

/** Verify fixed, scoped worker defaults; setup never impersonates a master author. */
export async function companyProductDefaults(company: string): Promise<{ type: Master; group: Master }> {
  const signal = AbortSignal.timeout(30_000);
  async function read(resource: 'product-types' | 'item-groups') {
    const path = `/v1/companies/${company}/${resource}`;
    const verify = (result: Page, limit: number) => {
      // Native lists are company-scoped by their owning API and omit company_id.
      if (!Array.isArray(result.items) || result.items.length > limit || result.items.some(row => !trackingId.test(row.id) || ('company_id' in row && row.company_id !== company) || typeof row.code !== 'string' || typeof row.name !== 'string')) {
        throw { status: 502, message: 'The product defaults could not be verified for this company.' };
      }
      return result.items;
    };
    const canonical = verify(await companyCall<Page>('catalog', path + '?code=DEFAULT&limit=1', { signal }), 1);
    if (canonical[0]?.code?.toUpperCase() === 'DEFAULT') return canonical[0];
    if (canonical.length) throw { status: 502, message: 'The product default identity could not be verified.' };
    const named = verify(await companyCall<Page>('catalog', path + '?q=Default&limit=50', { signal }), 50);
    return named.filter(row => row.name?.toLowerCase() === 'default').sort((a, b) => a.id.localeCompare(b.id))[0];
  }
  for (let attempt = 0; attempt < 30; attempt++) {
    const [type, group] = await Promise.all([read('product-types'), read('item-groups')]);
    if (type && (type.is_active !== true || type.kind !== 'BOTH') || group && (group.is_active !== true || group.allowed_kind !== 'BOTH')) {
      throw review();
    }
    if (type && group) {
      const revisions = await companyCall<{ items: Revision[] }>('catalog', `/v1/companies/${company}/product-types/${type.id}/revisions?published=true&limit=1`, { signal });
      if (!Array.isArray(revisions.items) || revisions.items.length > 1 || revisions.items.some(row => !trackingId.test(row.id) || row.product_type_id !== type.id || row.kind !== 'BOTH' || typeof row.published_at !== 'string' || !Number.isFinite(Date.parse(row.published_at)))) {
        throw { status: 502, message: 'The published product default revision could not be verified.' };
      }
      if (!revisions.items.length) throw review();
      return { type, group };
    }
    if (signal.aborted || attempt === 29) throw pending();
    await new Promise<void>(resolve => setTimeout(resolve, 1000));
  }
  throw pending();
}
