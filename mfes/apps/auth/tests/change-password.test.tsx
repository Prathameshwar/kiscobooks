import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { renderScreen } from './helpers';
import Page from '../app/change-password/page';
const { navigate } = vi.hoisted(() => ({ navigate: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ consoleUrl: () => 'http://localhost:4320', goTo: navigate }));
beforeEach(() => { vi.stubEnv('AUTH_PROVIDER', 'authentik'); navigate.mockReset(); vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ destination: 'https://localhost:9443/if/flow/bill-password-change/' }))); });
it('checks session before connecting, provides back navigation and ignores success query flags', async () => {
 window.history.replaceState({}, '', '/change-password?success=1'); renderScreen(<Page />);
 await userEvent.click(screen.getByRole('button', { name: 'Continue to change password' }));
 expect(navigate).toHaveBeenCalledWith('https://localhost:9443/if/flow/bill-password-change/');
 expect(screen.getByRole('link', { name: 'Back to your workspace' })).toBeInTheDocument();
 expect(screen.queryByText('Password changed')).not.toBeInTheDocument();
});
it.each([401,503])('shows safe errors on %s', async status => {
 vi.mocked(fetch).mockResolvedValue(Response.json({}, { status })); renderScreen(<Page />);
 await userEvent.click(screen.getByRole('button', { name: 'Continue to change password' }));
 expect(await screen.findByRole('alert')).toBeInTheDocument(); expect(navigate).not.toHaveBeenCalled();
 if (status===401) expect(screen.getByRole('link', { name: 'Sign in again' })).toBeInTheDocument();
});
it('shows connecting and handles invalid provider destinations', async () => {
 vi.mocked(fetch).mockResolvedValue(Response.json({ destination: 'http://evil.invalid/' })); renderScreen(<Page />);
 await userEvent.click(screen.getByRole('button', { name: 'Continue to change password' }));
 expect(await screen.findByRole('alert')).toHaveTextContent('temporarily unavailable'); expect(navigate).not.toHaveBeenCalled();
});
