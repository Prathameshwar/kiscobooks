// Loaded by the Next CLI and every build worker. A parent-only config-cache
// override does not reach webpack workers; both must use this isolated output.
const path = require('node:path');
const { createRequire } = require('node:module');
const root = path.resolve(__dirname, '../../../..');
const appRequire = createRequire(path.join(root, 'mfes/apps/console/package.json'));
const configPath = appRequire.resolve('next/dist/server/config');
const configModule = require(configPath);
const { PHASE_PRODUCTION_BUILD } = appRequire('next/constants');
require.cache[configPath].exports = {
  __esModule: true,
  ...configModule,
  default: async (...args) => {
    const config = await configModule.default(...args);
    if (args[0] === PHASE_PRODUCTION_BUILD) {
      config.distDir = '.next/purchase-review';
      config.experimental.cpus = 2;
    }
    return config;
  },
};
