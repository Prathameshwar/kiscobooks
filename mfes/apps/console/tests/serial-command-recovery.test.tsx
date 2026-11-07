import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useServiceCommand, type ServiceReader } from '../app/lib/service-resource';

const path = '/v1/companies/11111111-1111-4111-8111-111111111111/stock-tracking/serials';
const storageKey = 'tracking-command:tenant:actor:company:serials:new';
function Harness({ reader, keyName = storageKey }: { reader: ServiceReader; keyName?: string }) {
  const command = useServiceCommand(reader, 'serial', { storageKey: keyName, targetPath: path });
  return <><button onClick={() => void command.execute({ path, method: 'POST', body: { identifiers: [{ identifier_type: 'SERIAL', value: 'S1' }] } }, () => {})}>Save</button><button onClick={() => void command.retry(() => {})}>Retry</button><span>{command.uncertain ? 'uncertain' : 'ready'}</span>{command.failure && <span>{command.failure.message}</span>}</>;
}
afterEach(() => { cleanup(); sessionStorage.clear(); });
it('recovers the original body/key after reload and clears verified completion', async () => {
  const reader = vi.fn().mockRejectedValueOnce({ status: 503, message: 'Lost response' }).mockResolvedValue({ id: 'saved' });
  const view = render(<Harness reader={reader} />);
  fireEvent.click(screen.getByText('Save'));
  await screen.findByText('uncertain');
  view.unmount(); render(<Harness reader={reader} />);
  await screen.findByText('uncertain');
  fireEvent.click(screen.getByText('Retry'));
  await screen.findByText('ready');
  expect(reader.mock.calls[1]![0]).toEqual(reader.mock.calls[0]![0]);
  expect(sessionStorage.getItem(storageKey)).toBeNull();
});
it('does not load another actor scope or overwrite a damaged receipt', async () => {
  sessionStorage.setItem(storageKey, '{broken');
  const reader = vi.fn().mockResolvedValue({});
  const view = render(<Harness reader={reader} keyName="another-actor" />);
  expect(screen.getByText('ready')).toBeVisible();
  view.unmount(); render(<Harness reader={reader} />);
  await screen.findByText(/could not be verified/);
  await act(async () => fireEvent.click(screen.getByText('Save')));
  expect(reader).not.toHaveBeenCalled();
  expect(sessionStorage.getItem(storageKey)).toBe('{broken');
});
it('retains an uncertain key when read permission is revoked during recovery', async () => {
  const reader = vi.fn().mockRejectedValueOnce({ status: 503, message: 'Lost response' }).mockRejectedValueOnce({ status: 403, message: 'Access revoked' }).mockResolvedValue({});
  render(<Harness reader={reader} />); fireEvent.click(screen.getByText('Save'));
  await screen.findByText('uncertain'); fireEvent.click(screen.getByText('Retry'));
  await screen.findByText('Access revoked'); fireEvent.click(screen.getByText('Retry'));
  await waitFor(() => expect(reader).toHaveBeenCalledTimes(3));
  expect(reader.mock.calls[2]![0]).toEqual(reader.mock.calls[0]![0]);
});
