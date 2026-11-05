import { describe, expect, it } from 'vitest';
import { checkLimit, decodeCursor, encodeCursor, offsetFor } from '../app/lib/list-cursor';

/**
 * The cursor and limit rules both list stand-ins share (`app/lib/list-cursor`).
 *
 * They are covered end to end through the two list suites; these are the rules stated once, on their
 * own, because they are now the single place either endpoint's contract is expressed and a change here
 * changes both screens.
 */

class Refused extends Error {
  readonly status = 422;
}

const fail = (message: string): Error => new Refused(message);

describe('the cursor codec', () => {
  it('round-trips a payload through an opaque string', () => {
    const cursor = encodeCursor({ v: 1, k: 'key', offset: 50 });

    // Opaque to the caller — a screen that read a position out of it would be paging itself.
    expect(cursor).not.toContain('50');
    expect(decodeCursor(cursor, fail)).toEqual({ v: 1, k: 'key', offset: 50 });
  });

  it('survives a query key that is not ASCII', () => {
    /* `btoa` throws on anything outside Latin-1, and the key holds whatever was searched for — a
     * customer name or a city. The encoder percent-encodes first for exactly this. */
    const cursor = encodeCursor({ v: 1, k: '["नागपुर","name",25]', offset: 25 });
    expect(decodeCursor(cursor, fail).k).toBe('["नागपुर","name",25]');
  });

  it('refuses a malformed cursor as a 422, never as a crash', () => {
    for (const cursor of [
      'not-base64-at-all!!',
      btoa('{"nope":true}'),
      btoa(encodeURIComponent(JSON.stringify({ v: 2, k: 'key', offset: 0 }))),
      btoa(encodeURIComponent(JSON.stringify({ v: 1, k: 'key' }))),
      btoa(encodeURIComponent(JSON.stringify({ v: 1, k: 7, offset: 0 }))),
      btoa(encodeURIComponent(JSON.stringify({ v: 1, k: 'key', offset: 1.5 }))),
      btoa(encodeURIComponent(JSON.stringify(null))),
    ]) {
      expect(() => decodeCursor(cursor, fail), cursor).toThrow(Refused);
    }
  });

  it('rejects an unknown version rather than reading it anyway', () => {
    /* A cursor outlives a deploy. A best-effort read of a payload written by a different encoder is
     * how a reader gets a window from the wrong query with no error to explain it. */
    const future = btoa(encodeURIComponent(JSON.stringify({ v: 2, k: 'key', offset: 0 })));
    expect(() => decodeCursor(future, fail)).toThrow('cursor is malformed');
  });
});

describe('resuming from a cursor', () => {
  it('starts at the head when there is no cursor', () => {
    // The first page has no cursor, so an absent one is not an error — it is the head of the walk.
    expect(offsetFor(null, 'key', fail)).toBe(0);
    expect(offsetFor(undefined, 'key', fail)).toBe(0);
    expect(offsetFor('', 'key', fail)).toBe(0);
  });

  it('resumes where the cursor left off, for the query it belongs to', () => {
    expect(offsetFor(encodeCursor({ v: 1, k: 'key', offset: 75 }), 'key', fail)).toBe(75);
  });

  it('refuses a cursor minted for a different query', () => {
    /* The rule the whole list surface is written against: a keyset cursor carries the predicate of the
     * row it stopped at, so honouring it after the sort, a filter, the search or the page size changed
     * would skip and repeat rows instead of failing (api-conventions §2.1). */
    const cursor = encodeCursor({ v: 1, k: '["","name",25]', offset: 25 });
    expect(() => offsetFor(cursor, '["","-invoiced",25]', fail)).toThrow(
      'cursor was minted for a different query',
    );
    expect(() => offsetFor(cursor, '["","name",50]', fail)).toThrow(Refused);
  });
});

describe('the page size', () => {
  it('accepts a size inside the endpoint’s bounds', () => {
    expect(checkLimit(25, 200, fail)).toBe(25);
    expect(checkLimit(1, 200, fail)).toBe(1);
    expect(checkLimit(200, 200, fail)).toBe(200);
  });

  it('refuses rather than clamps', () => {
    /* A server that quietly answers `limit=5000` with 200 rows has answered a different question and
     * the client cannot tell. `useListQuery` clamps on the way out; this is the other half. */
    for (const limit of [0, -1, 201, 5000, 1.5, Number.NaN, Number.POSITIVE_INFINITY]) {
      expect(() => checkLimit(limit, 200, fail), String(limit)).toThrow(
        'limit must be between 1 and 200',
      );
    }
  });
});
