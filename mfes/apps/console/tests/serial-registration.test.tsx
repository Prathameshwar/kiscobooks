import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { SerialRegistration } from '../app/components/SerialRegistration';
import { serviceCall } from '../app/lib/service-call';
import { readRegistrationQueue, serialQueueKey } from '../app/lib/serial-registration';
import { trackingRoute } from '../app/lib/stock-tracking-route';
import { allowedStockTrackingRequest } from '../app/lib/stock-tracking-policy';
import { COMPANY, ITEM, RECORD, serialFixture, sourceFixture, trackingFixture } from './stock-tracking-fixtures';

vi.mock('../app/lib/service-call', async original => ({
  ...(await original<typeof import('../app/lib/service-call')>()), serviceCall: vi.fn(),
}));
const show = () => render(<SerialRegistration company={COMPANY} item={ITEM} recoveryScope="tenant:user" />);
const scan = (value: string) => {
  fireEvent.change(screen.getByLabelText('Scan or enter identifier'), { target: { value } });
  fireEvent.keyDown(screen.getByLabelText('Scan or enter identifier'), { key: 'Enter' });
};
beforeEach(() => {
  sessionStorage.clear(); vi.clearAllMocks();
  vi.mocked(serviceCall).mockImplementation(async (_, request) => {
    if (request.path.includes('field-set')) return trackingFixture(request) as never;
    if (request.path.includes('/context/')) return { ...sourceFixture, lot_tracking: false } as never;
    return { ...serialFixture, id: crypto.randomUUID(), lot_id: null } as never;
  });
});
afterEach(() => { cleanup(); sessionStorage.clear(); });

it('scans multiple units and rejects canonical duplicates before registration', async () => {
  show(); await screen.findByRole('button', { name: 'Add serial unit' });
  scan('SS'); scan('ß');
  fireEvent.change(screen.getByLabelText('Registration reason'), { target: { value: 'Supplier registration' } });
  fireEvent.click(screen.getByRole('button', { name: 'Register 2 units' }));
  await screen.findByText('This identifier is already entered for another unit.');
  expect(vi.mocked(serviceCall).mock.calls.filter(([, request]) => request.method)).toHaveLength(0);
});

it('retains each unit key and resumes a partially registered queue after reload', async () => {
  let writes = 0;
  const receipts = new Map<string, object>();
  vi.mocked(serviceCall).mockImplementation(async (_, request) => {
    if (!request.method) return (request.path.includes('field-set') ? trackingFixture(request) : { ...sourceFixture, lot_tracking: false }) as never;
    writes++;
    if (!receipts.has(request.key!)) receipts.set(request.key!, { ...serialFixture, id: crypto.randomUUID(), lot_id: null });
    if (writes === 2) throw { status: 503, message: 'Lost native receipt' };
    return receipts.get(request.key!) as never;
  });
  show(); await screen.findByRole('button', { name: 'Add serial unit' }); scan('A'); scan('B');
  fireEvent.change(screen.getByLabelText('Registration reason'), { target: { value: 'Supplier registration' } });
  fireEvent.click(screen.getByRole('button', { name: 'Register 2 units' }));
  await screen.findByText('1 of 2 units registered.');
  await screen.findByText(/result of this change could not be confirmed/); cleanup(); show();
  fireEvent.click(await screen.findByRole('button', { name: 'Retry remaining registrations' }));
  await screen.findByText('2 of 2 units registered.');
  const requests = vi.mocked(serviceCall).mock.calls.filter(([, request]) => request.method).map(([, request]) => request);
  expect(requests).toHaveLength(3);
  expect(requests[2]!.key).toBe(requests[1]!.key);
  expect(requests[2]!.body).toEqual(requests[1]!.body);
  expect(receipts.size).toBe(2);
});

it('refuses a corrupt retained queue without replacing it or dispatching a write', async () => {
  const key = serialQueueKey('tenant:user', COMPANY, ITEM);
  sessionStorage.setItem(key, '{invalid');
  show(); await screen.findByText(/retained serial queue could not be verified/);
  expect(screen.getByRole('button', { name: 'Register 0 units' })).toBeDisabled();
  expect(sessionStorage.getItem(key)).toBe('{invalid');
  expect(vi.mocked(serviceCall).mock.calls.filter(([, request]) => request.method)).toHaveLength(0);
});

it('confines retained queues and browser routes to their actor/company/product scope', () => {
  const key = serialQueueKey('tenant:user', COMPANY, ITEM);
  const unit = { key: crypto.randomUUID(), body: { item_id: ITEM, reason: 'Prepare receipt', identifiers: [{ identifier_type: 'SERIAL', slot: 1, value: 'A' }] } };
  sessionStorage.setItem(key, JSON.stringify({ units: [unit] }));
  expect(readRegistrationQueue(sessionStorage, key, ITEM)?.units).toHaveLength(1);
  expect(readRegistrationQueue(sessionStorage, serialQueueKey('tenant:other', COMPANY, ITEM), ITEM)).toBeNull();
  expect(readRegistrationQueue(sessionStorage, serialQueueKey('tenant:user', RECORD, ITEM), ITEM)).toBeNull();
  expect(() => readRegistrationQueue(sessionStorage, key, RECORD)).toThrow(/verified/);
  expect(trackingRoute(['serials', 'register'])?.page).toBe('register');
  expect(trackingRoute(['serials', RECORD, 'replace'])?.page).toBe('replace');
  expect(() => trackingRoute(['batches', RECORD, 'replace'])).toThrow();
  const query = `/v1/companies/${COMPANY}/stock-tracking/serials?id=${RECORD}&receipt_eligible=true&limit=1`;
  expect(allowedStockTrackingRequest('GET', query)).toBe(true);
  expect(allowedStockTrackingRequest('GET', query.replace(RECORD, 'bad-id'))).toBe(false);
});

it('requires an actor scope before any serial registration', async () => {
  render(<SerialRegistration company={COMPANY} item={ITEM} />);
  await act(async () => { await Promise.resolve(); });
  expect(screen.getByText('Refresh your signed-in session before registering serials.')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Register 0 units' })).toBeDisabled();
});
