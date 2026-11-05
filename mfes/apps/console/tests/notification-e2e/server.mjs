// Test-only browser host. Runs the production Next notification proxy with a fixture
// HttpOnly session. Identity/gateway credentials and keys stay on the server.
import react from '@vitejs/plugin-react';
import { resolve, dirname } from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { randomBytes } from 'node:crypto';
const require = createRequire(import.meta.url);
const { encode, decode } = require('next-auth/jwt');
const fromVitest = createRequire(require.resolve('vitest/package.json'));
const { createServer } = await import(pathToFileURL(resolve(dirname(fromVitest.resolve('vite/package.json')), 'dist/node/index.js')).href);
import { NextRequest } from 'next/server.js';

const root = process.cwd();
const port = Number(process.env.NOTIFICATION_E2E_WEB_PORT);
const api = 'http://127.0.0.1:' + process.env.NOTIFICATION_E2E_API_PORT;
process.env.NEXTAUTH_SECRET = randomBytes(32).toString('hex');
process.env.AUTH_URL = 'http://127.0.0.1:' + port;
process.env.NOTIFICATION_GATEWAY_URL = api + '/notification';
const server = await createServer({
  configFile: false, root,
  plugins: [react()],
  resolve: { alias: [{ find: /^@janso\/ui$/, replacement: resolve(root, '../../packages/ui/src/index.ts') }] },
  server: { host: '127.0.0.1', port, strictPort: true, fs: { allow: [resolve(root, '../../..'), resolve(root, '../../../clients')] } },
  appType: 'custom',
  optimizeDeps: { include: ['react-dom/client', '@janso/api-client'] },
});
server.middlewares.use(async (req, res, next) => {
  try {
    if (req.url === '/api/notifications' && req.method === 'POST') {
      const chunks = []; for await (const chunk of req) chunks.push(chunk);
      const { POST } = await server.ssrLoadModule('/app/api/notifications/route.ts');
      const response = await POST(new NextRequest('http://127.0.0.1:' + port + req.url, { method: 'POST', headers: req.headers, body: Buffer.concat(chunks).toString() }));
      res.writeHead(response.status, Object.fromEntries(response.headers)); res.end(await response.text()); return;
    }
    if (req.method !== 'GET' || !req.headers.accept?.includes('text/html')) return next();
    const url = new URL(req.url, 'http://127.0.0.1:' + port);
    const cookie = req.headers.cookie?.match(/(?:^|; )next-auth.session-token=([^;]+)/)?.[1];
    const previous = cookie ? await decode({ token: cookie, secret: process.env.NEXTAUTH_SECRET }) : null;
    const profile = url.searchParams.get('profile') === 'reader' ? 'reader' : url.searchParams.get('profile') === 'admin' ? 'admin' : previous?.fixtureProfile ?? 'admin';
    const token = await encode({ secret: process.env.NEXTAUTH_SECRET, token: { accessToken: 'fixture-' + profile, accessTokenExpires: Date.now() + 3600000, fixtureProfile: profile } });
    res.setHeader('Set-Cookie', 'next-auth.session-token=' + token + '; Path=/; HttpOnly; SameSite=Lax');
    const config = JSON.stringify({ profile, companyId: '019a0000-0000-7000-8000-000000000006' });
    const html = await server.transformIndexHtml(req.url, `<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script>window.__NOTIFICATION_FIXTURE__=${config}</script><script type="module" src="/tests/notification-e2e/main.tsx"></script></body></html>`);
    res.setHeader('Content-Type', 'text/html'); res.end(html);
  } catch (error) { console.error(error.stack); res.statusCode = 500; res.end('Fixture server error: ' + error.message); }
});
await server.listen();
console.log('Notification browser fixture ready on ' + port);
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, async () => { await server.close(); process.exit(0); });
