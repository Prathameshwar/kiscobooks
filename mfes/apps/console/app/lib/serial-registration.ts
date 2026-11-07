import { trackingId } from './stock-tracking-resources';
import type { SerialIdentifier } from './serial-identity';

export type RegistrationBody = {
  item_id: string; lot_id?: string; identifiers: SerialIdentifier[]; reason: string;
  replaces_unit_id?: string; expected_replaced_version?: number;
};
export type RegistrationUnit = { key: string; body: RegistrationBody; id?: string; rejected?: boolean };
export type RegistrationQueue = { units: RegistrationUnit[] };
export type Replacement = { id: string; row_version: number; item_id: string; lot_id?: string | null };

/** A retained queue is confined to one actor/company/product/batch and native create route. */
export function readRegistrationQueue(storage: Pick<Storage, 'getItem'>, key: string,
  item: string, lot?: string, replacement?: Replacement): RegistrationQueue | null {
  const raw = storage.getItem(key);
  if (!raw) return null;
  const invalid = () => { throw Error('The retained serial queue could not be verified. Check serial history before starting another registration.'); };
  if (raw.length > 1048576) return invalid();
  let queue: RegistrationQueue;
  try { queue = JSON.parse(raw) as RegistrationQueue; } catch { return invalid(); }
  if (!queue || !Array.isArray(queue.units) || !queue.units.length || queue.units.length > (replacement ? 1 : 200)) return invalid();
  const keys = new Set<string>(), ids = new Set<string>();
  for (const unit of queue.units) {
    const body = unit?.body;
    if (!unit || typeof unit.key !== 'string' || !trackingId.test(unit.key) || keys.has(unit.key)
      || !body || body.item_id !== item || (body.lot_id ?? '') !== (lot ?? '')
      || body.replaces_unit_id !== replacement?.id || (body.expected_replaced_version !== replacement?.row_version && !(replacement && unit.rejected === true && Number.isSafeInteger(body.expected_replaced_version) && body.expected_replaced_version! >= 1))
      || unit.rejected !== undefined && typeof unit.rejected !== 'boolean' || unit.id !== undefined && unit.rejected === true
      || typeof body.reason !== 'string' || body.reason.length < 3 || body.reason.length > 500
      || Object.keys(body).some(field => !['item_id', 'lot_id', 'identifiers', 'reason', 'replaces_unit_id', 'expected_replaced_version'].includes(field))
      || !Array.isArray(body.identifiers) || !body.identifiers.length || body.identifiers.length > 16
      || body.identifiers.some(value => !value || !['SERIAL', 'IMEI'].includes(value.identifier_type)
        || typeof value.value !== 'string' || [...value.value].length > 120
        || !Number.isInteger(value.slot ?? 1) || (value.slot ?? 1) < 1 || (value.slot ?? 1) > 8)
      || unit.id !== undefined && (typeof unit.id !== 'string' || !trackingId.test(unit.id) || ids.has(unit.id))) return invalid();
    keys.add(unit.key); if (unit.id) ids.add(unit.id);
  }
  return queue;
}

export const serialQueueKey = (scope: string, company: string, item: string, lot?: string, replacement?: Replacement) =>
  `serial-registration:${scope}:${company}:${item}:${lot ?? ''}:${replacement?.id ?? 'new'}`;
