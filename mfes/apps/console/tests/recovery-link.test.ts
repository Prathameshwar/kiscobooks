import { describe, expect, it } from 'vitest';
import { acceptableRecoveryLink } from '../app/lib/recovery-link';

const token = 'A1b2C3d4E5f6G7h8I9j0K-L_mNoPqRsTuVwXyZ01234';
const link = (value: string) => acceptableRecoveryLink(new URL(value));

describe('the sign-in provider’s recovery link', () => {
  it('accepts the Authentik flow link exactly as before', () => {
    expect(link('https://provider.test/if/flow/bill-administrator-recovery/?flow_token=private_recovery_token_that_is_only_in_memory')).toBe(true);
  });

  it('refuses an Authentik link that is plain http, has extra query, a credential or another path', () => {
    for (const value of [
      'http://provider.test/if/flow/bill-administrator-recovery/?flow_token=private_recovery_token_that_is_only_in_memory',
      'https://provider.test/if/flow/bill-administrator-recovery/?flow_token=private_recovery_token_that_is_only_in_memory&next=/x',
      'https://user:pw@provider.test/if/flow/bill-administrator-recovery/?flow_token=private_recovery_token_that_is_only_in_memory',
      'https://provider.test/if/flow/other/?flow_token=private_recovery_token_that_is_only_in_memory',
    ]) expect(link(value), value).toBe(false);
  });

  it('accepts the local provider’s one-time link over https', () => {
    expect(link(`https://bill.example.com/reset?token=${token}`)).toBe(true);
  });

  it('accepts it over plain http only for a loopback host, where nothing leaves the machine', () => {
    expect(link(`http://localhost:4310/reset?token=${token}`)).toBe(true);
    expect(link(`http://127.0.0.1:4310/reset?token=${token}`)).toBe(true);
    expect(link(`http://[::1]:4310/reset?token=${token}`)).toBe(true);
    for (const host of ['bill.example.com', 'localhost.evil.example', '127.0.0.1.evil.example', '10.0.0.5', '0.0.0.0'])
      expect(link(`http://${host}/reset?token=${token}`), host).toBe(false);
  });

  it('refuses a local link that is not exactly /reset with one 43-character token', () => {
    for (const value of [
      `https://bill.example.com/reset?token=${token.slice(1)}`,
      `https://bill.example.com/reset?token=${token}x`,
      `https://bill.example.com/reset?token=${token}&next=https://evil.example`,
      `https://bill.example.com/reset?other=${token}`,
      `https://bill.example.com/reset/?token=${token}`,
      `https://bill.example.com/login?token=${token}`,
      `https://bill.example.com/reset?token=${token}#frag`,
      `https://user:pw@bill.example.com/reset?token=${token}`,
      'https://bill.example.com/reset',
      `ftp://bill.example.com/reset?token=${token}`,
    ]) expect(link(value), value).toBe(false);
  });
});
