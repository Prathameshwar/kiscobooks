import type { ReactElement } from 'react';
import { render, type RenderResult } from '@testing-library/react';
import type { DisplayConfig, ThemePreference } from '@janso/ui';
import { Providers } from '../app/providers';
import type { CompanyContext } from '../app/lib/company-context';
import type { Session } from '../app/session';

/**
 * A session fixture, deliberately *not* `getSession()`.
 *
 * `getSession()` resolves a real identity session: it reads the request's next-auth token and
 * calls the identity service over HTTP. There is no request, no token and no service in a
 * component test, so calling it throws "Authentication is not configured" — and a unit test
 * that needs a network is not a unit test. The `Session` type is the contract between the two;
 * this supplies that shape.
 *
 * Permission keys are dot-separated, matching the platform catalogue
 * (docs/roles-permissions.md). `ledger.read`, `role.read` and `stock.read` are absent on
 * purpose: the shell tests assert that those nav items do **not** render.
 */
const FIXTURE: Session = {
  user: { name: 'Prathameshwar Singh', secondary: 'Janso Retail Pvt Ltd', theme: 'system', defaultCompanyId: null },
  organisation: { name: 'Janso Retail', code: 'JANSO-RETAIL' },
  company: { name: 'Janso Retail Pvt Ltd' },
  companySource: 'none',
  stepUpCompanyId: null,
  companyScopes: [],
  role: 'Organization Admin',
  permissions: [
    'invoice.read',
    'invoice.create',
    'payment.read',
    'customer.read',
    'item.read',
    'report.read',
    'tax.read',
    'audit.read',
    'company.read',
  ],
  display: {
    currency: 'INR',
    currencySymbol: '₹',
    amountPrecision: 2,
    quantityPrecision: 3,
    roundingMode: 'half_up',
    dateFormat: 'dd MMM yyyy',
    datetimeFormat: 'dd MMM yyyy, HH:mm',
    digitGrouping: 'indian',
    currencyDisplay: 'symbol',
    timezone: 'Asia/Kolkata',
    locale: 'en-IN',
  },
};

/**
 * The company and financial-year context a page hands the shell. Empty by default: the session
 * fixture has no open company, so the rail's switcher is in its "nothing selected" state unless
 * a test says otherwise.
 */
export const EMPTY_CONTEXT: CompanyContext = {
  companies: [],
  companiesNote: null,
  fiscalYears: [],
  fiscalYear: null,
  fiscalNote: null,
};

export function companyContextFor(overrides: Partial<CompanyContext> = {}): CompanyContext {
  return { ...EMPTY_CONTEXT, ...overrides };
}

export type Options = {
  /** Defaults to the session's full set; pass a narrower list to test a denied path. */
  permissions?: string[];
  display?: Partial<DisplayConfig>;
  /** `null` mounts with no stored preference, as a fresh page load does. */
  theme?: ThemePreference | null;
};

/** The request's session with the test's overrides applied — the shape a page receives. */
export async function sessionFor(options: Options = {}): Promise<Session> {
  const base = FIXTURE;
  return {
    ...base,
    // `light` by default so a test asserting on the painted palette starts from a known one.
    user: { ...base.user, theme: options.theme === undefined ? 'light' : options.theme },
    permissions: options.permissions ?? base.permissions,
    display: options.display ?? base.display,
  };
}

/**
 * Renders a screen inside the **real** `<Providers>` — the component the app actually mounts,
 * with a session resolved the way the page resolves it. Restating the provider tree here would
 * leave `app/providers.tsx` untested: deleting `PermissionProvider` from the app would then
 * still leave every test green, which is the one thing a test suite must never allow.
 *
 * `ui` may be a function of the session, because the shell takes the session as a prop and a
 * test needs the same object the providers were given (CLAUDE.md §7).
 */
export async function renderWithProviders(
  ui: ReactElement | ((session: Session) => ReactElement),
  options: Options = {},
): Promise<RenderResult & { session: Session }> {
  const session = await sessionFor(options);
  const element = typeof ui === 'function' ? ui(session) : ui;

  const result = render(<Providers session={session}>{element}</Providers>);
  return { ...result, session };
}
