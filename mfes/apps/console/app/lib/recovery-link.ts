/**
 * Which recovery links the console will show an operator.
 *
 * A link is a way into someone's account, so it is displayed only if it is exactly the shape one of
 * the two providers issues — never an arbitrary URL the server (or something in front of it) put in
 * a response: the Authentik flow link, or the local provider's `/reset?token=` link. Plain HTTP is
 * accepted for the local one on a loopback host only, since that traffic never leaves the machine.
 */
const LOOPBACK = new Set(['localhost', '127.0.0.1', '[::1]']);

export function acceptableRecoveryLink(url: URL): boolean {
  if (url.username || url.password || url.hash) return false;
  const keys = [...url.searchParams.keys()].join(',');
  if (url.protocol === 'https:' && url.pathname === '/if/flow/bill-administrator-recovery/' && keys === 'flow_token') {
    return /^[A-Za-z0-9_-]{20,512}$/.test(url.searchParams.get('flow_token') ?? '');
  }
  const secure = url.protocol === 'https:' || (url.protocol === 'http:' && LOOPBACK.has(url.hostname));
  return secure && url.pathname === '/reset' && keys === 'token' && /^[A-Za-z0-9_-]{43}$/.test(url.searchParams.get('token') ?? '');
}
