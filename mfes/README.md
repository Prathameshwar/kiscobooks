# JANSO — web micro-frontends

Web clients for **JANSO** — billing, accounting and inventory software — plus the shared
design system every MFE reuses.

```
mfes/
  packages/
    ui/            @janso/ui — design tokens, the three themes, component primitives, formatting
  apps/
    auth/          @janso/auth    — sign in · create account · recover access
    console/       @janso/console — the authenticated shell and the business dashboard
```

**[docs/design-system.md](../docs/design-system.md) is the contract.** Token names, component
names and props come from there; a name that isn't in it doesn't exist. Read it before adding
anything visual.

Shared vs. app: **primitives, tokens and the app shell live in `packages/ui`; screens, nav
configuration and data adapters stay in the app**. The auth split-screen stays in `apps/auth`
because nothing else will ever want it; the rail and top bar are shared because every
authenticated MFE needs them. Same "mechanism in the shared lib, policy in the service" line
the backend follows.

## Quick start

From the repo root, use the managed Windows launchers ([details](../start/win/README.md#ui-start-and-stop)):

```powershell
.\start\win\start-web.ps1
.\start\win\status-web.ps1
.\start\win\stop-web.ps1
```

```bat
start\win\start-web.bat
start\win\status-web.bat
start\win\stop-web.bat
```

Node.js 20+ is required. Use the pnpm version pinned in `package.json`; the launcher
installs with `--frozen-lockfile` if Next.js is missing. Apps run hidden and detached;
closing the launching terminal leaves them running. Use `stop-web.bat` to stop them.
Repeated starts reuse managed processes. An occupied external port is reported and
left untouched. `start-web.cmd` remains an alias with the same managed behavior.

For foreground development, from this directory:

```bash
pnpm install --frozen-lockfile
pnpm dev             # both apps; Ctrl+C in this terminal stops them
```

`auth` and `console` are **separate applications on separate ports**, so signing in hands the
browser from one to the other. Start only one and the hand-off dies at
`ERR_CONNECTION_REFUSED` — which is why `pnpm dev` runs both:

| | |
|---|---|
| http://localhost:4310/login | `auth` — provider sign-in and identity flows |
| http://localhost:4320 | `console` — the shell and the dashboard |

Individually, if you want one of them on its own: `pnpm dev:auth` / `pnpm dev:console`, or
`start-web.bat auth` / `start-web.ps1 -App auth` (and `console` likewise).
Stop/status accept the same app selector. `start-web.bat -TimeoutSeconds 90` extends
the default 60-second startup wait. `UP` means the managed web server passed its
public favicon HTTP probe; authentication and backend prerequisites remain separate.

## Authentication configuration

This computer's database, Redis and UI settings are now configured. Authentik runtime,
provider and user provisioning remain: [local login setup](../docs/local-login-setup.md).

The active login flow uses NextAuth with Authentik, followed by an Identity-backed
Console session. `/signup` provides branded account registration with Authentik
credentials and manual administrator approval; `/recover` presents the provider
login flow. See [registration and approval](../docs/account-registration.md).
Old demo credentials are not the active login path. Start both apps, open
**http://localhost:4310/login**, and use **Continue** to sign in with your configured provider.

Set local values in the ignored per-app files; restart the apps after editing them:

| File | Required settings |
|---|---|
| `apps/auth/.env.local` | `AUTH_PROVIDER` (`local`, the default, or `authentik`); with `local`: `AUTH_LOCAL_ISSUER`, `AUTH_LOCAL_CLIENT_ID`, `AUTH_LOCAL_CLIENT_SECRET`, `AUTH_LOCAL_BFF_SECRET` (written by `start\win\local-auth.bat`); with `authentik`: `AUTHENTIK_ISSUER` (HTTPS OIDC issuer), `AUTHENTIK_CLIENT_ID`, `AUTHENTIK_CLIENT_SECRET`; always `NEXTAUTH_URL`, `NEXTAUTH_SECRET`, `CONSOLE_URL`, `IDENTITY_URL`, `AUTH_REDIS_URL`; `AUTH_TRUSTED_PROXY_HOPS` (`0`–`3`, default `0`; set `1` behind the shipped nginx so per-address limits apply — never set it when the app is reachable directly) |
| `apps/console/.env.local` | `AUTH_URL`, `IDENTITY_URL`, `NEXTAUTH_SECRET` (same secret as Auth) |

For local development, set Auth `NEXTAUTH_URL=http://localhost:4310`,
`CONSOLE_URL=http://localhost:4320`, and Console `AUTH_URL=http://localhost:4310`.
Register `http://localhost:4310/api/auth/callback/authentik` with the provider.
`IDENTITY_URL` is the direct Identity origin (locally `http://127.0.0.1:8001`);
the app appends `/v1/...`. Set it on Auth as well to enable its Identity session
revocation integration. Secrets stay server-side; never prefix them `NEXT_PUBLIC_`.

Console feature routes also use `CATALOG_GATEWAY_URL`, `VOUCHERS_GATEWAY_URL`,
`ACCOUNTING_GATEWAY_URL`, `REPORTS_GATEWAY_URL`, `NOTIFICATION_GATEWAY_URL`
and `AUDIT_GATEWAY_URL`.
With local nginx on 8090, Catalog, Vouchers, Accounting, Reports and Notification
bases include their service path (for example `http://127.0.0.1:8090/notification`);
Audit uses the gateway origin
`http://127.0.0.1:8090` because its adapter appends `/audit/v1/...`.
Platform notification pages also require `NOTIFICATION_PLATFORM_OWNER_TENANT_ID`
and `NOTIFICATION_PLATFORM_SPACE_ID` in `start/win/env/notification.env`. Use the
completed installation's operating tenant ID as the owner and a distinct, stable
UUIDv7 as the space ID, then restart Notification. Keep both values when restoring
the local environment; regenerating service env files with `-Recreate` removes them.
Keep Authentik and the required APIs running separately.

If the provider handoff fails, Login explains that the sign-in service is unavailable
and offers retry or administrator help. Configuration failures explicitly direct users
to their administrator. Internal exceptions, hosts and credentials are not displayed.

Cross-app browser links use `NEXT_PUBLIC_CONSOLE_URL` and `NEXT_PUBLIC_AUTH_URL`,
defaulting to the local Console origin and Auth login URL respectively. Shared cookie
domains for HTTPS deployments use `AUTH_COOKIE_DOMAIN`; omit it for localhost HTTP.
Without authentication settings, the login screen renders and the Auth API returns a
sanitized 503. Console's error boundary shows retry and sign-in actions after hydration;
failed server rendering still has HTTP status 500.

Set Auth `AUTH_REDIS_URL=redis://127.0.0.1:6379/0` locally and start Redis with
`start\win\start-redis.bat` before refreshing sessions. All Auth instances must use
the same Redis store and session secret. Refresh coordination uses credential HMAC
keys, a 12-second ownership lock and encrypted results that expire after 15 seconds.
Redis 6.3.0 is pinned for this mechanism and uses RESP2 for the bundled Windows Redis.
Use a protected Redis endpoint and `rediss://` when traffic crosses a network.
An unavailable coordinator returns a retryable failure; it never bypasses the lock.

Console API reads refresh once after local session expiry. Mutations retry automatically
only with the same validated idempotency key; other mutations retain the form for a
manual retry. Server navigation and report downloads preserve their return path.
`NEXT_PUBLIC_AUTH_URL` and server `AUTH_URL` must identify the same Auth host; likewise
`NEXT_PUBLIC_CONSOLE_URL` must agree with Auth's `CONSOLE_URL`. Use localhost consistently
for HTTP development, or controlled sibling HTTPS hosts with the shared cookie domain.

Sign out opens Auth's confirmation page, then submits NextAuth's CSRF-protected POST.
It clears session, company-selection and proof cookies and attempts Identity/provider
revocation. Dependency outages do not prevent local cookie deletion. Configure the
provider's access tokens to include the original `auth_time`, retained across refresh.
After Identity revocation, missing/old `auth_time` is rejected even with a new `iat`;
login after revocation or logout requests fresh provider authentication.
Company verification sets an HttpOnly selection cookie; Identity rechecks company
scope and the matching proof during Console bootstrap.

Regression and integration evidence: [login/API remediation](../docs/login-api-fixes-2026-10-20.md).

## See it without installing

Open **`apps/console/preview.html`** (or `apps/auth/preview.html`) straight from disk. Both are
dependency-free and carry the *same* stylesheets the React apps do, so the CSS cannot drift — and
the console preview's theme switcher is live, so all three palettes are reviewable with no build
step. The console preview (the Business overview) is **generated** from the real components by
`apps/console/tests/overview-layout.browser.test.tsx`, so it cannot drift from the screen;
regenerate it with `QA_OVERVIEW_PREVIEW=1 pnpm --filter @janso/console exec vitest run tests/overview-layout.browser.test.tsx`.
Its figures are the test fixture's and exist nowhere in the application. The auth preview's markup
is hand-mirrored, so that part *can* drift; its header comment lists what to re-check.

## Themes

Three palettes and a resolver, switched from the top bar with no reload:

| Preference | Palette | Notes |
|---|---|---|
| Light | `light` | Refined indigo on clean paper — the default |
| Dark | `dark` | Indigo lifted for contrast; separation comes from lines, not shadows |
| Ledger | `ledger` | Warm paper and warm ink — the account-book vernacular |
| System | resolves to `light` or `dark` | Follows the OS live, with no reload |

How it works, in three facts:

1. **Colour lives only in `theme-*.css`.** Every other stylesheet is colour-free and reads
   `--janso-*` tokens. A test fails the build if a hex literal appears anywhere else, because
   one surviving literal is how a theme silently breaks on one screen.
2. **All three palettes define the identical token key set**, also enforced by a test. A
   missing key would fall back to an inherited light value rather than failing loudly.
3. **The preference is stored, the resolved value never is** — a stored `system` follows the
   user's OS to a different machine, a stored `dark` would not. A synchronous pre-paint script
   (`themeScript`) applies `data-theme` before the first frame, so there is no flash of the
   wrong theme; the same resolution rule (`resolveTheme`) backs the script, the provider and
   the tests.

The durable preference is `user.theme` ([identity-schema](../docs/identity-schema.md)); the
cookie and `localStorage` are what make the first paint correct before the session is known.

## Formatting money and dates

`formatMoney` / `formatQuantity` / `formatDate` and friends read the **resolved display
config**, never the browser's locale or timezone — two users must not see different totals for
the same document, and a machine in another region must not change one.

**Amounts and quantities are decimal strings end to end.** No amount is ever a JS `number`:
rounding and grouping are done with `BigInt`, so nothing depends on float behaviour. Grouping
supports `western` (1,234,567) and `indian` (12,34,567), and compact figures follow suit —
K/M/B or K/L/Cr, because a crore rendered as "41.6M" is wrong for the primary market.

An absent amount renders an em-dash, never `0`. In accounting those are different facts.

## Tests

Every shared component and every page ships tests — no UI ships without them.

```bash
pnpm test            # everything
pnpm test:ui         # @janso/ui primitives, tokens, themes, formatting
pnpm test:auth       # the auth screens
pnpm test:console    # the shell, the dashboard, theming end to end
pnpm typecheck
```

Auth's test command includes Node tests against real NextAuth handlers. To include the
native Redis concurrency check in PowerShell, start local Redis and run:

```powershell
$env:TEST_AUTH_REDIS_URL = 'redis://127.0.0.1:6379/15'
pnpm test:auth
Remove-Item Env:TEST_AUTH_REDIS_URL
```

This test uses random credential keys with TTLs and does not flush Redis.

Beyond per-component coverage, the suites assert the system-level rules: token parity across
the three palettes, no colour literals outside them, theme resolution for all four preferences
including a live OS change, permission-gated UI **present for a permitted role and absent for
one without it**, and money formatted from config rather than locale.

## The design in one paragraph

The vernacular is the **ruled account book**: labels flush-left, thin rules as real separators,
tabular numerals wherever figures appear, tight 4–6px radii rather than the soft cards of a
generic console. Colour is a refined **indigo** with signals expressed as
`{ink, tint, line}` triplets — a tinted surface with a matching border and coloured ink, never
coloured text on a plain background, and never colour alone without an icon or label. Type is
**Bricolage Grotesque** (display) + **IBM Plex Sans** (UI, with `tabular-nums`). The console
shell is one CSS grid with a single scroll container, so the rail and top bar never move.
The logomark is a self-contained gradient SVG with `useId()`-namespaced gradient ids, and it is
deliberately identical in all three themes — a brand mark that repaints per palette stops
being a brand mark.


## Product custom fields

The Console route `/products/custom-fields` uses shared `CustomFields` and `CustomFieldEditor`
components. Set `CATALOG_GATEWAY_URL` on the Console server to the bearer-authenticated Catalog
gateway base, alongside `AUTH_URL`, `NEXTAUTH_SECRET` and `IDENTITY_URL`. The route proxy appends
`/v1/companies/...` to that base. Configuration stays server-side; missing settings return 503.
See [custom-fields.md](../docs/custom-fields.md) for authoring, adoption and backend prerequisites.


First-run platform provisioning is available at Auth `/setup`; it reuses `@janso/ui`
themes and Stepper. Console `/platform` lists authorized tenant summaries.
See [platform setup](../docs/platform-setup.md) for preparation and verification.
