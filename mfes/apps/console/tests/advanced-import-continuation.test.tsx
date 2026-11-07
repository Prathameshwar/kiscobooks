import {render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {beforeEach, expect, it, vi} from 'vitest';
import {ProductImport} from '../app/components/ProductImport';
import {serviceCall} from '../app/lib/service-call';
import {COMPANY, JOB, importResponse, job} from './product-import-fixtures';

vi.mock('../app/lib/service-call', async original => ({
  ...(await original<typeof import('../app/lib/service-call')>()), serviceCall: vi.fn(),
}));
const api = vi.mocked(serviceCall);
beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(null, '', '/masters/items/import');
});

it.each(['VALIDATING', 'IMPORTING'])('continues Advanced %s with its current version and reviewed digest', async state => {
  const current = {...job(state, 5), review_digest: state === 'IMPORTING' ? 'b'.repeat(64) : null};
  api.mockImplementation(async (_, request) => importResponse(request.path,
    request.method === 'POST' ? job(state === 'VALIDATING' ? 'READY' : 'SUCCEEDED', 6) : current) as never);
  render(<ProductImport company={COMPANY} canManage initialJob={JOB} />);
  const button = await screen.findByRole('button', {name: state === 'VALIDATING' ? 'Continue validation' : 'Continue import'});
  expect(screen.queryByRole('button', {name: 'Cancel import'})).not.toBeInTheDocument();
  await userEvent.click(button);
  await waitFor(() => expect(api.mock.calls.some(([,request]) => request.method === 'POST')).toBe(true));
  const request = api.mock.calls.find(([,request]) => request.method === 'POST')![1];
  expect(request.path).toBe('/v1/companies/' + COMPANY + '/import-jobs/' + JOB + (state === 'VALIDATING' ? '/validate' : '/commit'));
  expect(request.body).toEqual({expected_version: 5, ...(state === 'IMPORTING' ? {review_digest: 'b'.repeat(64)} : {})});
  expect(request.key).toBeTruthy();
});

it('does not allow a reader to continue an Advanced import', async () => {
  const current = job('VALIDATING', 5);
  api.mockImplementation(async (_,request) => importResponse(request.path, current) as never);
  render(<ProductImport company={COMPANY} canManage={false} initialJob={JOB} />);
  await screen.findByText('Validation is in progress. Continue checking remaining products below.');
  expect(screen.queryByRole('button', {name: 'Continue validation'})).not.toBeInTheDocument();
});
