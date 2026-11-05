const path = require('node:path');
const { createRequire } = require('node:module');
const { pathToFileURL } = require('node:url');
const root = path.resolve(__dirname, '../../../..');
const localRequire = createRequire(path.join(root, 'mfes/apps/console/package.json'));
(async () => {
  const pluginRequire = createRequire(localRequire.resolve('@vitejs/plugin-react'));
  const { createServer } = await import(pathToFileURL(path.join(path.dirname(pluginRequire.resolve('vite')), 'dist/node/index.js')).href);
  const { default: react } = await import(pathToFileURL(localRequire.resolve('@vitejs/plugin-react')).href);
  const server = await createServer({ configFile: false, root: __dirname, plugins: [react()],
    resolve: { alias: { '@janso/ui': path.join(root, 'mfes/packages/ui/src/index.ts'), react: path.dirname(localRequire.resolve('react/package.json')), 'react-dom': path.dirname(localRequire.resolve('react-dom/package.json')) } },
    server: { host: '127.0.0.1', port: 4417, strictPort: true, fs: { allow: [root] } } });
  await server.listen(); server.printUrls();
})().catch(error => { console.error(error); process.exitCode = 1; });
