'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { once } = require('node:events');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

async function runWorker(t, { worker = '1', marker = true, delayedHandler = false } = {}) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'bill-ui-stop-'));
  const stopPath = path.join(directory, 'web-auth.stop');
  const preload = path.resolve(__dirname, '..', 'web-stop.cjs');
  if (marker) fs.writeFileSync(stopPath, 'stop');
  const script = `
    const attach = () => process.on('SIGTERM', () => {
      console.log('cleanup finished'); process.exit(0);
    });
    ${delayedHandler ? 'setTimeout(attach, 600);' : 'attach();'}
    setTimeout(() => process.exit(7), 1400);
  `;
  const child = spawn(process.execPath, ['--require', preload, '-e', script], {
    env: { ...process.env, NEXT_PRIVATE_WORKER: worker, BILL_WEB_STOP_PATH: stopPath },
    windowsHide: true,
  });
  t.after(() => {
    if (child.exitCode === null) child.kill();
    fs.rmSync(directory, { recursive: true, force: true });
  });
  let output = '';
  child.stdout.on('data', chunk => { output += chunk; });
  const [code] = await once(child, 'exit');
  return { code, output };
}

test('stop marker invokes the worker cleanup handler', { timeout: 5000 }, async t => {
  const result = await runWorker(t);
  assert.equal(result.code, 0);
  assert.match(result.output, /cleanup finished/);
});
test('waits for cleanup handlers during initialization', { timeout: 5000 }, async t => {
  const result = await runWorker(t, { delayedHandler: true });
  assert.equal(result.code, 0);
  assert.match(result.output, /cleanup finished/);
});
test('CLI parent does not react to the worker marker', { timeout: 5000 }, async t => {
  const result = await runWorker(t, { worker: '' });
  assert.equal(result.code, 7);
  assert.doesNotMatch(result.output, /cleanup finished/);
});
test('running worker continues without a marker', { timeout: 5000 }, async t => {
  const result = await runWorker(t, { marker: false });
  assert.equal(result.code, 7);
  assert.doesNotMatch(result.output, /cleanup finished/);
});
