'use client';

import { createContext, useContext, useMemo, type ReactNode } from 'react';

/**
 * ============================================================================
 * PRESENTATION ONLY. THE SERVER IS THE ENFORCEMENT POINT.
 * ============================================================================
 *
 * `useCan` and `<Can>` decide what is *drawn*. They decide nothing about what is *allowed*.
 * Hiding a control is never the control: every route declares its required permission, every
 * object-level scope check runs server-side, and a field denied by `field_policy` must be
 * rejected server-side on the changed-field set — in exports and reports too
 * (CLAUDE.md §5.1–5.2, §6.15, docs/field-permissions.md §6).
 *
 * So: an action gated here must also be gated in the API. If the only thing standing between a
 * user and someone else's invoice is a `<Can>` wrapper, that is a vulnerability with a nice UI.
 *
 * The permission set is resolved server-side and handed to this provider. It is never read from
 * a JWT claim — the token carries `tenant_id` / `user_id` / `user_type` only, so revocation
 * takes effect on the cache TTL rather than the token TTL (CLAUDE.md §5.4).
 */

const NO_PERMISSIONS: readonly string[] = Object.freeze([]);

const PermissionContext = createContext<readonly string[]>(NO_PERMISSIONS);

type PermissionProviderProps = {
  /** The actor's resolved concrete permission keys, e.g. `['invoice.read', 'company.read']`. */
  permissions: readonly string[];
  children: ReactNode;
};

export function PermissionProvider({ permissions, children }: PermissionProviderProps) {
  return (
    <PermissionContext.Provider value={permissions}>{children}</PermissionContext.Provider>
  );
}

/** The raw resolved set, for the rare caller that needs to test several keys at once. */
export function usePermissions(): readonly string[] {
  return useContext(PermissionContext);
}

/**
 * The server catalogue grants concrete keys only. Unknown wildcard strings cannot
 * widen presentation authority beyond the same exact-key contract used by the API.
 */
function satisfies(held: string, required: string): boolean {
  return !held.includes('*') && held === required;
}

/**
 * Deny by default: with no provider, or an empty set, nothing is drawn. An absent set means
 * "unknown", and rendering a money-mutating button on an unknown set is the wrong guess.
 */
export function useCan(key: string): boolean {
  const permissions = usePermissions();
  return useMemo(() => permissions.some((held) => satisfies(held, key)), [permissions, key]);
}

/**
 * A predicate over the resolved set, for filtering a *list* — a menu's items, a table's columns
 * and its row actions. `useCan` takes one key and so cannot be called in a loop; without this a
 * caller either calls a hook conditionally or hand-rolls the exact-key check a second time.
 *
 * An `undefined` key means "not gated" and passes. That is not a hole in deny-by-default: an
 * item with no `permission` is one the caller never claimed to restrict, and the server still
 * enforces whatever the action actually needs.
 */
export function useGranted(): (key: string | undefined) => boolean {
  const permissions = usePermissions();
  return useMemo(
    () => (key: string | undefined) =>
      key === undefined || permissions.some((held) => satisfies(held, key)),
    [permissions],
  );
}

type CanProps = {
  permission: string;
  /** Rendered when denied. Default is nothing — no placeholder, no disabled ghost control. */
  fallback?: ReactNode;
  children: ReactNode;
};

export function Can({ permission, fallback = null, children }: CanProps) {
  return <>{useCan(permission) ? children : fallback}</>;
}
