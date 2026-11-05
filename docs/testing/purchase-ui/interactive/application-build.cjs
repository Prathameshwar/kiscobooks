// Build the actual Next application while preserving the running dev server's .next.
const path = require('node:path');
const fs = require('node:fs');
const { createRequire } = require('node:module');
const { spawnSync } = require('node:child_process');
const root = path.resolve(__dirname, '../../../..');
const app = path.join(root, 'mfes/apps/console');
const localRequire = createRequire(path.join(app, 'package.json'));
const tsconfigPath = path.join(app, 'tsconfig.json');
const envPath = path.join(app, 'next-env.d.ts');
const originalConfig = fs.readFileSync(tsconfigPath, 'utf8');
const originalEnv = fs.readFileSync(envPath, 'utf8');
process.on('exit', () => {
  const current = JSON.parse(fs.readFileSync(tsconfigPath, 'utf8'));
  const original = JSON.parse(originalConfig);
  current.include = current.include.filter(value => !value.includes('purchase-review/types')).sort();
  original.include.sort();
  if (JSON.stringify(current) === JSON.stringify(original)) fs.writeFileSync(tsconfigPath, originalConfig);
  else console.error('Preserving concurrent tsconfig changes; review generated include manually.');
  const currentEnv = fs.readFileSync(envPath, 'utf8');
  if (currentEnv.replace('./.next/purchase-review/types/routes.d.ts', './.next/types/routes.d.ts') === originalEnv) fs.writeFileSync(envPath, originalEnv);
});
(async () => {
  const hook = path.join(__dirname, 'next-build-config.cjs').replace(/\\/g, '/');
  const result = spawnSync(process.execPath, [localRequire.resolve('next/dist/bin/next'), 'build'], {
    cwd: app, stdio: 'inherit', env: { ...process.env, NODE_OPTIONS: `${process.env.NODE_OPTIONS || ''} --require "${hook}"` },
  });
  if (result.error) throw result.error;
  process.exitCode = result.status ?? 1;
})().catch(error => { console.error(error); process.exitCode = 1; });
