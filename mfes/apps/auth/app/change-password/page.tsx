import React from 'react';
import { safeAuthProvider } from '../lib/provider';
import { LocalChangePassword } from './LocalChangePassword';
import { ProviderChangePassword } from './ProviderChangePassword';

// Chosen per request from AUTH_PROVIDER, never at build time.
export const dynamic = 'force-dynamic';

/** `local`: change the password in this app. `authentik`: continue to the provider's own flow. */
export default function ChangePasswordPage() {
  return safeAuthProvider() === 'local' ? <LocalChangePassword /> : <ProviderChangePassword />;
}
