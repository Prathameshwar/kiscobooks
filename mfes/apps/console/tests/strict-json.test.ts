import { expect, it } from 'vitest';
import { strictJson } from '../app/lib/strict-json';
it('accepts strings, nested arrays and keys repeated in different objects', () => {
  const value = { rows: [{ name: 'a' }, { name: '"{:}\\' }], name: 'parent', numbers: [1, 2] };
  expect(strictJson(JSON.stringify(value))).toEqual(value);
});
it.each(['{"name":1,"name":2}', '{"name":1,"na\\u006de":2}', '[{"nested":{"id":1,"id":2}}]', '{broken'])('rejects invalid or duplicate JSON %s', value => {
  expect(() => strictJson(value)).toThrow();
});
