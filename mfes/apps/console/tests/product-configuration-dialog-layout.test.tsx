/**
 * The publication review dialog — layout.
 *
 * It shows a page's worth of settings (a comparison per product kind, then every section's
 * effective values) and used to do it in the narrow 30rem confirmation panel: the cards touched
 * each other, and Cancel / Publish sat at the very end of one long scroll. jsdom cannot judge
 * pixels, so these pin the structure the stylesheet's sizing and spacing depend on.
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { DisplayConfigProvider } from '@janso/ui';
import { ProductConfigurationDetail } from '../app/components/ProductConfigurationDetail';
import { serviceCall } from '../app/lib/service-call';
import { COMPANY, DRAFT, response } from './product-configuration-fixtures';
vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/signin' }));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(serviceCall).mockImplementation(async (_, request) => response(request.path, request.method) as never);
});

async function openReview() {
  render(<DisplayConfigProvider config={{ timezone: 'Asia/Kolkata' }}><ProductConfigurationDetail company={COMPANY} id={DRAFT} canManage canPublish timezone="Asia/Kolkata" /></DisplayConfigProvider>);
  await userEvent.click(await screen.findByRole('button', { name: 'Review publication' }));
  return screen.findByRole('dialog', { name: 'Publish these product defaults?' });
}

it('opens the review in the large panel, not the narrow confirmation one', async () => {
  expect(await openReview()).toHaveAttribute('data-size', 'lg');
});

it('lays each product kind’s comparison out as its own spaced column, so its cards cannot touch', async () => {
  const dialog = await openReview();
  const goods = within(dialog).getByRole('heading', { name: 'Goods' });
  expect(goods.parentElement).toHaveClass('janso-flow');
  // The sections that follow the comparison are children of that column, not loose siblings.
  expect(goods.parentElement!.querySelector('.janso-card')).not.toBeNull();
});

it('keeps Cancel and Publish revision outside the scrolling body of a long review', async () => {
  const dialog = await openReview();
  const body = dialog.querySelector('.janso-dialog__body')!;
  expect(body).toContainElement(within(dialog).getByRole('heading', { name: 'Goods' }));
  expect(body).not.toContainElement(within(dialog).getByRole('button', { name: 'Publish revision' }));
  expect(body).not.toContainElement(within(dialog).getByRole('button', { name: 'Cancel' }));
});
