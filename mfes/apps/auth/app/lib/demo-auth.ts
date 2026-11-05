/**
 * A stand-in for `identity`, so the sign-in → dashboard path can be walked before the API
 * exists.
 *
 * =========================================================================================
 * THIS IS NOT AUTHENTICATION. It is a fixture with a keyboard in front of it.
 *
 * The credentials below are compiled into the client bundle, so anyone can read them — which
 * is exactly why they are printed on the screen when this is on. A credential you publish is
 * not a secret, and that is the only honest way to ship one in a repo (CLAUDE.md §5.9). When
 * `identity` is wired, this module is deleted rather than adapted: there is no version of it
 * that becomes safe.
 *
 * It is **off in a production build** unless someone explicitly turns it on, so it cannot
 * reach a real deployment by being forgotten.
 * =========================================================================================
 */

const flag = process.env.NEXT_PUBLIC_DEMO_SIGN_IN;

/** On in development; in a production build only when asked for by name. */
export const DEMO_SIGN_IN_ENABLED =
  flag === 'true' ? true : flag === 'false' ? false : process.env.NODE_ENV !== 'production';

/** Either accepted form — the field takes an email or a mobile number, so both work. */
export const DEMO_EMAIL = 'owner@janso.test';
export const DEMO_MOBILE = '9876543210';
export const DEMO_PASSWORD = 'janso-demo';

/** Digits only, so "98765 43210" and "+91 98765 43210" both match the demo mobile. */
function digits(value: string): string {
  return value.replace(/\D/g, '');
}

export function checkDemoCredentials(identifier: string, password: string): boolean {
  if (!DEMO_SIGN_IN_ENABLED) return false;
  if (password !== DEMO_PASSWORD) return false;

  const entered = identifier.trim().toLowerCase();
  if (entered === DEMO_EMAIL) return true;

  const asDigits = digits(entered);
  // Tolerate a country code, but only India's — this is a demo, not a phone-number library.
  return asDigits === DEMO_MOBILE || asDigits === `91${DEMO_MOBILE}`;
}
