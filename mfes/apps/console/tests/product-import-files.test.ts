import { expect, it } from 'vitest';
import {
  assertImportJob,
  assertImportTemplate,
  importFileProblem,
  importMaximumBytes,
  importSourceFiles,
} from '../app/lib/product-import';
import { job, template } from './product-import-fixtures';
it('accepts only bounded supported source files', () => {
  expect(importFileProblem([])).toMatch(/Choose/);
  expect(importFileProblem([new File(['x'], 'legacy.xls')])).toMatch(/Legacy/);
  expect(importFileProblem([new File([], 'empty.csv')])).toMatch(/Empty/);
  expect(
    importFileProblem(
      Array.from({ length: 17 }, (_, i) => new File(['x'], i + '.csv')),
    ),
  ).toMatch(/16/);
  expect(
    importFileProblem([
      new File([new Uint8Array(importMaximumBytes)], 'a.csv'),
      new File(['x'], 'b.csv'),
    ]),
  ).toMatch(/combined/);
});
it.each(['csv', 'tsv', 'xlsx'])(
  'retains exact %s bytes and supplies safe distinct filenames',
  async (suffix) => {
    const files = await importSourceFiles([
      new File([new Uint8Array([0, 1, 2, 255])], 'Product list.' + suffix),
      new File(['other'], 'Product list.' + suffix),
    ]);
    expect(files[0]!.content_base64).toBe('AAEC/w==');
    expect(files[0]!.format).toBe(suffix.toUpperCase());
    expect(files[0]!.filename).toMatch(/^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$/);
    expect(files[0]!.filename).not.toBe(files[1]!.filename);
  },
);
it('does not accept a foreign definition or malformed native receipt', () => {
  expect(() => assertImportJob(job())).not.toThrow();
  expect(() => assertImportTemplate(template)).not.toThrow();
  expect(() => assertImportJob({ ...job(), definition: 'prices' })).toThrow();
  expect(() => assertImportJob({ ...job(), row_version: 0 })).toThrow();
  expect(() => assertImportJob({ ...job(), completed_count: 2 })).toThrow();
  expect(() => assertImportTemplate({ ...template, snapshot: {} })).toThrow();
});
