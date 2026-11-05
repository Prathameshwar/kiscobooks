import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { useServiceCommand } from '../app/lib/service-resource';
import type { ServiceRequest } from '../app/lib/service-call';

it('retains the exact request and key when the native command reports a busy lock', async () => {
  const reader = vi
    .fn()
    .mockRejectedValueOnce({
      status: 409,
      code: 'conflict',
      message: 'request is busy; retry with the same idempotency key',
    })
    .mockResolvedValue({ id: 'saved' });
  const request: ServiceRequest = {
    path: '/product-families',
    method: 'POST',
    body: { code: 'PRODUCT' },
  };
  function Harness() {
    const command = useServiceCommand(reader);
    return (
      <>
        <button onClick={() => void command.execute(request, () => {})}>
          Submit
        </button>
        <output>{command.uncertain ? 'Retry same save' : 'Ready'}</output>
      </>
    );
  }
  render(<Harness />);
  await userEvent.click(screen.getByRole('button', { name: 'Submit' }));
  expect(await screen.findByText('Retry same save')).toBeVisible();
  await userEvent.click(screen.getByRole('button', { name: 'Submit' }));
  expect(await screen.findByText('Ready')).toBeVisible();
  expect(reader.mock.calls[1]![0]).toEqual(reader.mock.calls[0]![0]);
});

/**
 * A write left uncertain by a server error pins the hook to *that* request, so the same one can be
 * replayed under its key. Something else has to be able to move on — `clear()` is how — and it has to
 * work in the same click: a screen that clears and then issues a different write must not find its
 * write silently refused by the `uncertain` it has just cleared.
 */
function uncertainHarness() {
  const reader = vi.fn().mockRejectedValueOnce({ status: 503, message: 'The service did not answer.' }).mockResolvedValue({ id: 'saved' });
  const first: ServiceRequest = { path: '/rules/a', method: 'PATCH', body: { is_active: false } };
  const other: ServiceRequest = { path: '/rules/b', method: 'PATCH', body: { is_active: false } };
  function Harness() {
    const command = useServiceCommand(reader);
    return (
      <>
        <button onClick={() => void command.execute(first, () => {})}>First</button>
        <button onClick={() => void command.execute(other, () => {})}>Other</button>
        <button
          onClick={() => {
            command.clear();
            void command.execute(other, () => {});
          }}
        >
          Clear then other
        </button>
        <output>{command.uncertain ? 'Uncertain' : 'Ready'}</output>
      </>
    );
  }
  return { reader, Harness };
}

it('lets a different write go in the same click that clears an uncertain one', async () => {
  const { reader, Harness } = uncertainHarness();
  render(<Harness />);
  await userEvent.click(screen.getByRole('button', { name: 'First' }));
  expect(await screen.findByText('Uncertain')).toBeVisible();

  await userEvent.click(screen.getByRole('button', { name: 'Clear then other' }));

  expect(await screen.findByText('Ready')).toBeVisible();
  expect(reader).toHaveBeenCalledTimes(2);
  expect(reader.mock.calls[1]![0]).toMatchObject({ path: '/rules/b' });
});

it('still refuses a different write while one is uncertain and nobody has cleared it', async () => {
  const { reader, Harness } = uncertainHarness();
  render(<Harness />);
  await userEvent.click(screen.getByRole('button', { name: 'First' }));
  expect(await screen.findByText('Uncertain')).toBeVisible();

  await userEvent.click(screen.getByRole('button', { name: 'Other' }));

  expect(reader).toHaveBeenCalledTimes(1);
  expect(screen.getByText('Uncertain')).toBeVisible();
});
