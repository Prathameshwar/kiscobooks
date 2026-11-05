'use strict';

// On Windows an external SIGTERM kills Node immediately. Emit it inside Next's
// worker so its own cleanup handler closes the server and watchers first.
// The official Next CLI inherits --require into its worker (and worker restarts).
const fs = require('node:fs');

if (process.env.NEXT_PRIVATE_WORKER === '1' && process.env.BILL_WEB_STOP_PATH) {
  const timer = setInterval(() => {
    if (!fs.existsSync(process.env.BILL_WEB_STOP_PATH)) return;
    if (process.listenerCount('SIGTERM') === 0) return; // still initializing
    clearInterval(timer);
    console.log('[bill-ui] Running Next.js shutdown handlers.');
    process.emit('SIGTERM');
  }, 200);
  timer.unref();
}
