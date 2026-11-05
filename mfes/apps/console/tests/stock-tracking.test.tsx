import { expect, it } from 'vitest';
import { allowedStockTrackingRequest } from '../app/lib/stock-tracking-policy';
const company = '01990000-0000-7000-8000-000000000001', item = '01990000-0000-7000-8000-000000000002', lot = '01990000-0000-7000-8000-000000000003', unit = '01990000-0000-7000-8000-000000000004';
const root = `/v1/companies/${company}/stock-tracking`;
it.each([
  ['GET', '/batches'], ['POST', '/batches'], ['GET', '/serials?item_id=' + item], ['POST', '/serials'],
  ['GET', '/context/' + item], ['GET', '/batches/field-set?action=hold'], ['PATCH', '/batches/' + lot],
  ['GET', '/context/' + item + '?resource=stock'], ['GET', '/serials?receipt_eligible=true'],
  ['GET', '/serials?never_received=false'], ['GET', '/serials?source_movement_id=' + unit],
  ['POST', '/serials/' + unit + '/hold'], ['GET', '/batches/' + lot + '/history?limit=25'],
])('allows the exact tracking route %s %s', (method, path) => expect(allowedStockTrackingRequest(method, root + path)).toBe(true));
it.each([
  ['DELETE', '/batches/' + lot], ['PATCH', '/serials/' + unit], ['POST', '/batches?x=1'],
  ['GET', '/serials?expires_before=2026-12-01'], ['POST', '/serials/' + unit + '/post'],
  ['GET', '/batches?limit=25&limit=50'], ['GET', '/batches/field-set?action=post'],
  ['GET', '/batches/%2e%2e/serials'], ['GET', '/batches/' + lot + '/history?reason=secret'],
  ['GET', '/context/' + item + '?resource=ledger'], ['GET', '/serials?receipt_eligible=yes'],
  ['GET', '/serials?never_received=1'], ['GET', '/serials?source_movement_id=invalid'],
  ['GET', '/batches?receipt_eligible=true'], ['GET', '/serials?receipt_eligible=true&receipt_eligible=false'],
])('rejects a different or unsafe route %s %s', (method, path) => expect(allowedStockTrackingRequest(method, root + path)).toBe(false));