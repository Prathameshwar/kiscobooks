// Exercise real pure UI policies without spawning Vite/esbuild workers.
// These probes assert observed defects, not the desired fixed behavior.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../../..');
const ts = require(path.join(root, 'mfes/apps/console/node_modules/typescript'));
require.extensions['.ts'] = (module, filename) => {
  const result = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    fileName: filename,
  });
  module._compile(result.outputText, filename);
};
const lib = path.join(root, 'mfes/apps/console/app/lib');
const { newWork } = require(path.join(lib, 'advanced-product-draft.ts'));
const { emptyBusiness, putBusiness, businessErrors } = require(path.join(lib, 'advanced-product-business.ts'));
const { emptyOpening, putOpening, openingErrors } = require(path.join(lib, 'advanced-product-opening.ts'));
const options = {
  today: '2026-11-07', books_begin_date: '2026-11-07', inventory_enabled: true,
  batch: { available: true, required: false, expiry_enabled: true },
  serial: { enabled: false }, selected_type: { inventory_modes: ['STOCK'] },
  defaults: { configuration: { pricing: {
    sale_price_mode: 'REQUIRED', purchase_reference_mode: 'REQUIRED', mrp_mode: 'REQUIRED',
  }}},
  sale_price_levels: [{ plan_id: 'plan', price_level_id: 'level', name: 'Retail', required: true }],
};
let work = newWork();
work = putBusiness(work, work.skus[0], { ...emptyBusiness(), batch_enabled: true });
work = putOpening(work, work.skus[0], {
  ...emptyOpening(), decision: 'OPEN', opening_date: options.today,
  batches: [{ key: 'row', code: 'LOT1', opening_quantity: '1', purchase_price: '10',
    sale_prices: { level: '12' }, mrp: '15', manufactured_on: '', expires_on: '2028-01-01', serials: [] }],
});
assert.deepEqual(openingErrors(work, options), {});
assert.equal(Object.keys(businessErrors(work, options)).length, 3);
console.log('PASS: complete batch prices still require three redundant SKU price fields.');
let zeroWork = newWork();
zeroWork = putOpening(zeroWork, zeroWork.skus[0], {
  ...emptyOpening(), decision: 'OPEN', opening_date: options.today,
  opening_quantity: '1', purchase_price: '0',
});
assert.deepEqual(openingErrors(zeroWork, { ...options, batch: { available: false }, sale_price_levels: [] }), {});
console.log('PASS: zero purchase cost passes Advanced opening UI validation.');
