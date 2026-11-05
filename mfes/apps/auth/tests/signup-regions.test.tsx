import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { renderScreen } from './helpers';
import Page from '../app/signup/page';

const options = {
  countries: [{ code: 'IN', name: 'India' }, { code: 'US', name: 'United States' }],
  states: [{ code: 'IN-MH', name: 'Maharashtra', country_code: 'IN' },
    { code: 'US-CA', name: 'California', country_code: 'US' }],
};
beforeEach(() => vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({
  enabled: true, mode: 'manual-review', options,
}))));

it('defaults to database-backed India and keeps country/state in the shared row', async () => {
  renderScreen(<Page />);
  const country = await screen.findByRole('combobox', { name: 'Country' });
  const state = screen.getByRole('combobox', { name: 'State' });
  expect(country).toHaveValue('IN');
  expect(state).toHaveValue('');
  expect(country.closest('.janso-form-grid--pair')).not.toBeNull();
  expect(country.closest('.janso-form-grid--pair')).toBe(state.closest('.janso-form-grid--pair'));
  expect(screen.getByRole('option', { name: 'Maharashtra' })).toBeInTheDocument();
  expect(screen.queryByRole('option', { name: 'California' })).not.toBeInTheDocument();
});

it('clears the state when country changes and filters choices from the API', async () => {
  renderScreen(<Page />);
  await screen.findByRole('combobox', { name: 'Country' });
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'State' }), 'IN-MH');
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Country' }), 'US');
  expect(screen.getByRole('combobox', { name: 'State' })).toHaveValue('');
  expect(screen.getByRole('option', { name: 'California' })).toBeInTheDocument();
  expect(screen.queryByRole('option', { name: 'Maharashtra' })).not.toBeInTheDocument();
});

it('requires a valid state and submits only the fixed credential and region fields', async () => {
  renderScreen(<Page />);
  await screen.findByRole('combobox', { name: 'Country' });
  for (const [label, value] of [['Full name', 'New Account'], ['Username', 'new-account'],
    ['Email address', 'new@example.invalid']]) fireEvent.change(screen.getByLabelText(label), { target: { value } });
  const password = crypto.randomUUID();
  for (const label of ['Password', 'Confirm password']) fireEvent.change(screen.getByLabelText(label, { exact: true }), { target: { value: password } });
  await userEvent.click(screen.getByRole('button', { name: 'Create account' }));
  expect(screen.getByRole('combobox', { name: 'State' })).toHaveFocus();
  expect(fetch).toHaveBeenCalledTimes(1);
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'State' }), 'IN-MH');
  vi.mocked(fetch).mockResolvedValueOnce(Response.json({ created: true, status: 'pending-review' }, { status: 201 }));
  await userEvent.click(screen.getByRole('button', { name: 'Create account' }));
  await screen.findByLabelText('Account created');
  const body = JSON.parse(vi.mocked(fetch).mock.calls[1][1]?.body as string);
  expect(body).toMatchObject({ country_code: 'IN', state_code: 'IN-MH' });
  expect(Object.keys(body).sort()).toEqual(['country_code', 'email', 'name', 'password', 'password_repeat', 'state_code', 'username']);
});

it('does not invent India when it is inactive in the database', async () => {
  vi.mocked(fetch).mockResolvedValue(Response.json({ enabled: true, mode: 'manual-review', options: {
    countries: [options.countries[1]], states: [options.states[1]],
  } }));
  renderScreen(<Page />);
  expect(await screen.findByRole('combobox', { name: 'Country' })).toHaveValue('');
  expect(screen.queryByRole('option', { name: /India/ })).not.toBeInTheDocument();
});

it('blocks incomplete reference data and retries without discarding account details', async () => {
  vi.mocked(fetch).mockResolvedValueOnce(Response.json({ enabled: true, mode: 'manual-review', options: { countries: [], states: [] } }));
  renderScreen(<Page />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Create account' })).toBeDisabled());
  await userEvent.click(await screen.findByRole('button', { name: 'Try again' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Create account' })).toBeEnabled());
  expect(screen.getByRole('combobox', { name: 'Country' })).toHaveValue('IN');
});
