import { describe, expect, it } from 'vitest';
import { allowedDesignAssetUpload } from '../app/lib/design-asset-upload-policy';

const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const path = '/v1/companies/' + id(1) + '/assets';

describe('the brand-asset upload route serves exactly one path', () => {
  it('allows uploading an asset for this one service and path only', () => {
    expect(allowedDesignAssetUpload('design', 'POST', path)).toBe(true);
  });

  it.each([
    ['another service', 'vouchers', 'POST', path],
    ['the wrong method', 'design', 'GET', path],
    ['a query string', 'design', 'POST', path + '?extra=true'],
    ['a sibling path', 'design', 'POST', path + '/' + id(2)],
    ['a dot-segment traversal', 'design', 'POST', path + '/../other'],
    ['an encoded dot segment', 'design', 'POST', path + '/%2e%2e/other'],
    ['an encoded slash', 'design', 'POST', '/v1/companies/' + id(1) + '%2fassets'],
    ['a path outside /v1', 'design', 'POST', '/v2/companies/' + id(1) + '/assets'],
    ['an escaped origin', 'design', 'POST', '//evil.invalid' + path],
    ['a control character', 'design', 'POST', path + '\x00'],
  ])('refuses %s', (_, service, method, candidate) => {
    expect(allowedDesignAssetUpload(service, method, candidate)).toBe(false);
  });
});
