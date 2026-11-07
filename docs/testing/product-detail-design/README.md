# Product detail validation

From the repository root:

```powershell
node docs/testing/product-detail-design/regressions.cjs
python docs/testing/product-detail-design/prepare-browser.py
```

The first command runs actual React components with fixture services, verifies read-only access and signed edit saves, and renders nine HTML fixtures. The second compresses their shared CSS and markup for the browser.

`browser.cjs` reads `browser-input.b64` from stdin and returns JSON measurements and six base64 screenshots. It checks horizontal overflow and native keyboard section navigation at five widths. Set `PLAYWRIGHT_MODULE` and `CHROMIUM_PATH` to the test environment's installed Playwright module and Chromium; defaults target the existing VM test tools. A local Linux invocation is:

```sh
node docs/testing/product-detail-design/browser.cjs < .test_artifacts/product-detail-design/browser-input.b64 > .test_artifacts/product-detail-design/browser-results.json
```

On this Windows workstation `prepare-browser.py` also writes an encoded script with the fixtures embedded for Bitvise's stdin transport:

```powershell
$taskScript = Get-Content .test_artifacts/product-detail-design/vm-browser-script.b64 -Raw
$taskResult = $taskScript | & 'C:\Program Files (x86)\Bitvise SSH Client\sexec.exe' -profile='C:\Users\Administrator\Documents\hostinger-vm.tlp' -exitZero -inputEOL=lf -cmd='base64 -d | node'
[IO.File]::WriteAllText((Join-Path (Get-Location) '.test_artifacts/product-detail-design/browser-results.json'), ($taskResult -join "`n"))
```

Verify the returned JSON contains 45 measurements and no `error` property; the Bitvise exit code alone is not an assertion of test success. This run executes the script in memory. It does not publish the application, change company data or install browser tools. The saved profile and authentication details stay outside the repository.
