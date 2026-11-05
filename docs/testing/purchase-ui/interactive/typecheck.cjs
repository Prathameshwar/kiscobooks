const path = require('node:path');
const { createRequire } = require('node:module');
const root = path.resolve(__dirname, '../../../..');
const app = path.join(root, 'mfes/apps/console');
process.chdir(app);
const ts = createRequire(path.join(app, 'package.json'))('typescript');
const configPath = path.join(app, 'tsconfig.json');
const { config, error } = ts.readConfigFile(configPath, ts.sys.readFile);
if (error) throw Error(ts.flattenDiagnosticMessageText(error.messageText, '\n'));
const { options, errors } = ts.parseJsonConfigFileContent(config, ts.sys, app);
// The harness lives outside the pnpm app tree; resolve its React types from that app.
options.paths = { ...options.paths, react: [path.join(app, 'node_modules/@types/react/index.d.ts')], 'react/*': [path.join(app, 'node_modules/@types/react/*')], 'react-dom/*': [path.join(app, 'node_modules/@types/react-dom/*')] };
const files = ['next-env.d.ts', 'vitest.setup.tsx', 'app/lib/purchase-workspace.ts', 'app/components/PurchaseWorkspace.tsx', 'app/components/PurchaseWorkspaceHeader.tsx', 'app/components/PurchaseWorkspaceGrid.tsx', 'app/components/PurchaseWorkspaceTotals.tsx', 'app/vouchers/new/purchase-preview/page.tsx', 'tests/purchase-workspace.test.tsx', 'tests/purchase-preview-route.test.tsx', 'tests/purchase-workspace-details.test.ts', 'tests/purchase-workspace-panels.test.tsx', 'tests/purchase-workflow-model.test.ts', 'tests/purchase-workflow.test.tsx', 'tests/draft-navigation.test.tsx'];
files.push('tests/purchase-mobile.test.tsx', 'tests/purchase-workspace-quality.test.tsx');
const program = ts.createProgram([...files.map(file => path.join(app, file)), path.join(__dirname, 'review-fixtures.ts'), path.join(__dirname, 'main.tsx')], { ...options, incremental: false, tsBuildInfoFile: undefined });
const diagnostics = [...errors, ...ts.getPreEmitDiagnostics(program)];
if (diagnostics.length) {
  console.error(ts.formatDiagnosticsWithColorAndContext(diagnostics, { getCanonicalFileName: file => file, getCurrentDirectory: () => root, getNewLine: () => '\n' }));
  process.exitCode = 1;
} else console.log('PASS: Purchase source, preview route, tests and their transitive dependencies typecheck. This is not the whole-console build.');
