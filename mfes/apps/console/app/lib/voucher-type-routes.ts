/**
 * Where voucher types live in the console, as plain values.
 *
 * Not a client module: the page that resolves `/masters/voucher-types/<segment>` runs on the server,
 * and a function exported from a `'use client'` file is a client reference there, not something a
 * Server Component can call.
 */
export const TYPES_ROOT = '/masters/voucher-types';
export const typeHref = (id: string) => `${TYPES_ROOT}/${id}`;

const UUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
/** Whether a URL segment can be a voucher type's id. Anything else is a 404, never a guess. */
export const isTypeId = (value: string) => UUID.test(value);
