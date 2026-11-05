/**
 * The cursor codec and the limit check the console's list stand-ins share
 * ([api-conventions](../../../../docs/api-conventions.md) §2.1).
 *
 * These are **stand-ins for the server**, not client-side paging: the real cursor is minted and
 * verified by `libs/platform`, HMAC-signed over the resource, the normalized sort and a hash of the
 * filters and scope, and no client will ever encode one. What is worth reproducing faithfully is the
 * property every list screen is written against — a cursor carries the query it was minted for, so a
 * mismatch is a `422` rather than a silently wrong window — and reproducing it *twice*, slightly
 * differently, is how a screen ends up tested against a rule the endpoint does not have.
 *
 * The 422 class stays with each resource, because a screen distinguishes its own recoverable failure
 * from a transport failure by that class. It is passed in.
 */

/**
 * What a cursor carries: a version, the query key it is bound to, and the position.
 *
 * The version is first because a cursor outlives a deploy: an unrecognised `v` is a `422` naming the
 * cursor, which the reader recovers from with the first page of the same query — never a crash, and
 * never a best-effort read of a payload written by a different version of the encoder.
 */
export type CursorPayload = { v: 1; k: string; offset: number };

/** Builds a 422 for a resource. Each list module passes its own class. */
export type Fail = (message: string) => Error;

export function encodeCursor(payload: CursorPayload): string {
  /* `encodeURIComponent` first: `btoa` throws on anything outside Latin-1, and the query key holds
   * whatever was searched for — a customer name or a city is not guaranteed to be ASCII. */
  return btoa(encodeURIComponent(JSON.stringify(payload)));
}

export function decodeCursor(cursor: string, fail: Fail): CursorPayload {
  let parsed: unknown;
  try {
    parsed = JSON.parse(decodeURIComponent(atob(cursor)));
  } catch {
    // Malformed is a 422, never a 500: it is a parameter the server will not use, and the rows are
    // all still there.
    throw fail('cursor is malformed');
  }

  const candidate = parsed as Partial<CursorPayload> | null;
  const { k, offset } = candidate ?? {};
  /* Every field checked, including the version: this is untrusted input in the real endpoint, and a
   * `typeof` test narrows where a cast would only silence the compiler. */
  if (candidate?.v !== 1 || typeof k !== 'string' || typeof offset !== 'number' || !Number.isInteger(offset)) {
    throw fail('cursor is malformed');
  }

  return { v: 1, k, offset };
}

/**
 * The page size, rejected rather than clamped.
 *
 * A server that quietly returns 200 rows for `limit=5000` has answered a different question than the
 * one asked, and the client cannot tell. `useListQuery` clamps on the way *out* so a reader cannot
 * ask for that; this is the other half of the same rule (§2.1).
 */
export function checkLimit(limit: number, max: number, fail: Fail): number {
  if (!Number.isInteger(limit) || limit < 1 || limit > max) {
    throw fail(`limit must be between 1 and ${max}`);
  }
  return limit;
}

/**
 * The position a cursor resumes from, once it is known to belong to this query.
 *
 * The key comparison is the whole point of the cursor: it is bound to the search text, the normalized
 * sort, every filter **and the page size**. A keyset cursor carries the predicate of the row it
 * stopped at, so changing the sort invalidates it exactly as changing a filter does — honouring one
 * across a re-sort would skip and repeat rows rather than fail. `limit` is in for one more reason: the
 * position is expressed in pages of the size it was minted for, so honouring one across a resize
 * returns the wrong window outright.
 */
export function offsetFor(cursor: string | null | undefined, key: string, fail: Fail): number {
  if (cursor === null || cursor === undefined || cursor === '') return 0;
  const decoded = decodeCursor(cursor, fail);
  if (decoded.k !== key) {
    throw fail('cursor was minted for a different query');
  }
  return decoded.offset;
}
