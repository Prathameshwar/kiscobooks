import type { MasterRow } from './catalog-masters';
import { profileId } from './product-profiles';
export const definitionResources = ['promotion-limits'] as const;
export type DefinitionResource = (typeof definitionResources)[number];
export const isDefinitionResource = (value: string): value is DefinitionResource => (definitionResources as readonly string[]).includes(value);
export const definitionSpec = {
  'promotion-limits': { entity: 'catalog.promotion_limit_definition', revisionEntity: 'catalog.promotion_limit_revision', parent: 'definition_id', permission: 'promotion_limit',
    headerKeys: ['code', 'name', 'scope_kind', 'metric', 'period_basis', 'timezone', 'currency', 'unit_id'],
    immutable: ['code', 'scope_kind', 'metric', 'period_basis', 'timezone', 'currency', 'unit_id'],
    revisionKeys: ['maximum_count', 'maximum_quantity', 'maximum_amount', 'change_reason'],
    explanation: 'Publish requested count, reward-quantity or net-benefit caps. A new version keeps the same quota identity. Publication does not apply a live cap, reset usage or reserve budget.',
  },
} as const;
export const definitionBase = (company: string, resource: DefinitionResource) => `/v1/companies/${company}/${resource}`;
export const capKey = (parent: MasterRow) => parent.metric === 'BUDGET' ? 'maximum_amount' : parent.metric === 'REWARD_UNITS' ? 'maximum_quantity' : 'maximum_count';
export function definitionRevisionBody(resource: DefinitionResource, values: Record<string, unknown>, parent: MasterRow) {
  const errors: Record<string, string> = {}, selected = capKey(parent);
  const body: Record<string, unknown> = { maximum_count: null, maximum_quantity: null, maximum_amount: null, change_reason: values.change_reason };
  const value = values[selected]; body[selected] = value;
  if (!['TOTAL_USES', 'PER_CUSTOMER_USES', 'PER_ORDER_USES', 'REWARD_UNITS', 'BUDGET'].includes(String(parent.metric))) errors.metric = 'The quota measure is protected or unavailable. Reload the definition.';
  if (selected === 'maximum_count') {
    if (typeof value !== 'string' || !/^\d{1,19}$/.test(value) || BigInt(value) < 1n || BigInt(value) > 9223372036854775807n) errors[selected] = 'Enter a whole count from 1 to 9223372036854775807.';
  } else if (typeof value !== 'string' || !/^\d{1,15}(?:\.\d{1,4})?$/.test(value) || !/[1-9]/.test(value)) errors[selected] = 'Enter a positive exact cap with up to four decimal places.';
  if (typeof values.change_reason !== 'string' || !values.change_reason.trim() || values.change_reason.length > 500 || /[\x00-\x1f\x7f]/.test(values.change_reason)) errors.change_reason = 'Enter a printable change reason with up to 500 characters.';
  return { body, errors };
}
export function verifyDefinitionRevision(row: MasterRow, company: string, parent: string, resource: DefinitionResource, id?: string) {
  if (row.company_id !== company || !profileId.test(row.id) || id && row.id !== id || row[definitionSpec[resource].parent] !== parent || typeof row.complete !== 'boolean' || row.operational_ready !== false) throw { status: 502, message: 'This definition revision could not be verified for the company and parent.' };
  if (row.complete && (!Number.isSafeInteger(row.row_version) || Number(row.row_version) < 1 || !Number.isSafeInteger(row.revision) || Number(row.revision) < 1 || !('published_at' in row) || row.published_at !== null && (typeof row.published_at !== 'string' || !Number.isFinite(Date.parse(row.published_at))) || definitionSpec[resource].revisionKeys.some(key => !(key in row)))) throw { status: 502, message: 'The complete definition or its concurrency version is unavailable.' };
}
