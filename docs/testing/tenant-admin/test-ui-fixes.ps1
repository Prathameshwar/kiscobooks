param([string]$Phase = (Get-Date -Format 'yyyyMMdd-HHmmss'))
$ErrorActionPreference = 'Stop'
if ($Phase -notmatch '^[A-Za-z0-9_-]+$') { throw 'Phase must contain only letters, digits, underscore or hyphen.' }
$taskRoot = (Get-Item -LiteralPath (Join-Path $PSScriptRoot '../../..')).FullName
$artifactRoot = Join-Path $taskRoot '.test_artifacts'
New-Item -ItemType Directory -Path $artifactRoot -Force | Out-Null
$consoleTests = @(
  'activity-feed.test.tsx', 'audit-events.test.tsx', 'company-overview.test.tsx',
  'invoice-designer-controls.test.tsx', 'invoice-designer-native-restore.test.tsx',
  'invoice-designer-panels.test.tsx', 'money-entry-form.test.tsx',
  'purchase-entry-contract.test.ts', 'purchase-entry-form.test.tsx',
  'purchase-entry-save.test.tsx', 'purchase-validation.test.tsx',
  'report-card-connection.test.tsx', 'report-references.test.tsx',
  'report-source-summary.test.tsx', 'report-workspace.test.tsx',
  'voucher-detail-page.test.tsx', 'voucher-directory.test.tsx',
  'voucher-draft-edit.test.tsx', 'voucher-draft-pages.test.tsx',
  'voucher-entry-stock.test.tsx', 'voucher-money.test.tsx',
  'voucher-summary.test.tsx', 'voucher-workflow.test.tsx',
  'voucher-reference-labels.test.ts', 'vouchers-page.test.tsx'
)
$uiTests = @(
  'filter-bar-layout.browser.test.tsx', 'search-select.test.tsx',
  'search-select-focus.test.tsx', 'search-select-review.test.tsx',
  'select.test.tsx', 'field-structure.test.tsx'
)
function Invoke-Checks([string]$directory, [string]$suite, [string[]]$testNames) {
  Push-Location -LiteralPath (Join-Path $taskRoot $directory)
  try {
    $testPaths = @($testNames | ForEach-Object { 'tests/' + $_ })
    foreach ($testPath in $testPaths) {
      if (-not (Test-Path -LiteralPath $testPath)) { throw "Missing regression: $testPath" }
    }
    $reportPath = Join-Path $artifactRoot "ui-fixes-$Phase-$suite.json"
    & node node_modules/vitest/vitest.mjs run @testPaths --maxWorkers=1 --minWorkers=1 --reporter=json "--outputFile=$reportPath"
    if ($LASTEXITCODE -ne 0) { throw "$suite regression suite failed; see $reportPath" }
  } finally { Pop-Location }
}
# Browser suites are sequential to avoid Edge teardown contention.
Invoke-Checks 'mfes/packages/ui' 'controls' $uiTests
Invoke-Checks 'mfes/apps/console' 'components' $consoleTests
Invoke-Checks 'mfes/apps/console' 'geometry' @('invoice-designer-layout.browser.test.tsx', 'review-layout.browser.test.tsx')
foreach ($directory in @('mfes/packages/ui', 'mfes/apps/console')) {
  Push-Location -LiteralPath (Join-Path $taskRoot $directory)
  try {
    & node node_modules/typescript/bin/tsc --noEmit --pretty false
    if ($LASTEXITCODE -ne 0) { throw "TypeScript failed in $directory" }
  } finally { Pop-Location }
}
Write-Output "Local UI checks passed. Evidence: .test_artifacts/ui-fixes-$Phase-*.json. Live acceptance is separate."
