import { describe, expect, it } from 'vitest';
import { normalizedLogin } from '../app/lib/local-auth-shared';

describe('local sign-in identifier', () => {
  it.each([
    [' Tenant1 ', 'tenant1'],
    ['Tenant1@Example.Test ', 'tenant1@example.test'],
    ['bill-admin-' + 'a'.repeat(32), 'bill-admin-' + 'a'.repeat(32)],
    ['admin-' + 'b'.repeat(32), 'admin-' + 'b'.repeat(32)],
    ['a'.repeat(64), 'a'.repeat(64)],
  ])('normalises a valid username or email: %s', (input, expected) => {
    expect(normalizedLogin(input)).toBe(expected);
  });

  it.each([null, undefined, 1, {}, '', 'ab', 'has space', 'bad/name', 'bad@address', 'a'.repeat(65),
    'has\0control', 'a@b.test\0', 'a'.repeat(250) + '@b.test'])('rejects malformed input: %j', input => {
    expect(normalizedLogin(input)).toBeNull();
  });
});
