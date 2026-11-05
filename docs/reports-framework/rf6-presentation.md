# RF6 presentation: implementation and verification record

Status: Windows implementation and packaging complete; default admission remains disabled.
User confirmed Windows deployment first on 2026-10-15. Linux native validation remains a
separate prerequisite before Linux activation.

Identity resolves browser/report display through one helper. The signed Reports company
context carries the company label, exact precision/rounding, date patterns, separators,
grouping and user-resolved display preferences. New runs require and freeze that configuration;
retained runs keep it after company/user settings change. Non-Reports signed contexts omit
the extension for older strict readers. Deploy Reports readers before the Identity issuer.
The shared mechanism is billing-platform 0.34.0; all 11 library/consumer locks are updated.

The Python formatter and browser formatter consume the same 15 fixtures: large exact values,
half-even/down rounding, negative zero, Indian/western grouping, quoted date tokens and
timezone conversion. Browser session mapping now preserves separators, currency symbol and
negative conventions. The original placeholder report display and incomplete browser mapping
were reproduced with failing regressions before fixes.

## Assets and renderers

`mfes/packages/ui/src/styles/report.css` is the presentation source alongside shared light
palette/type tokens. `python -m tools.build_report_assets` generates a deterministic offline
bundle; `--check` rejects drift. External CSS imports are removed and asset fetches rejected.
Excel header/body styles derive from that bundle. CSV/XLSX are canonical data exports: exact
stored decimals/ISO dates, identifiers as text and large Excel numbers as exact text. XLSX
includes retained company/period/source metadata and states that HTML/PDF apply company display
rounding; spreadsheet applications can localize their own native number separators. This
preserves exact data without delegating financial rounding to Excel.

HTML uses streamed trusted Jinja2 templates with autoescaping, a restrictive standalone CSP,
embedded fonts, semantic tables and exact `data-value` attributes. Register, statement,
summary and reconciliation layouts share typography and table semantics. PDF uses ReportLab
4.5.1 plus uharfbuzz 0.55.0 for Devanagari shaping. Business strings are escaped before the
trusted paragraph markup boundary; no user images, templates, URLs or fetchers are accepted.
Wide PDFs use labelled column bands and repeat the identity column and every source row.

Noto Sans and Noto Sans Devanagari regular/bold fonts are packaged locally, unchanged, with
their SIL OFL 1.1 licence. Source revision and SHA-256 values live in `presentation-v1.json`.
[Official pinned font source](https://github.com/notofonts/noto-fonts/tree/ffebf8c1ee449e544955a7e813c54f9b73848eac).
Unsupported glyphs reject PDF rendering explicitly; this bundle does not claim every script.
Runtime downloads are not needed. Workbook fonts depend on the spreadsheet application's
installed fonts; PDF/HTML embed their font files.

PDF layout runs in an expendable child with no database or signing credentials in its
environment. Windows Job Objects enforce a 1 GiB process-memory cap; the parent kills and
joins a timed-out child. Input is bounded to 64 MiB, 5,000 rows/200,000 cells, 200 pages and
60 seconds. HTML is capped at 20,000 rows/200,000 cells. No partial output is published.
The renderer identity hashes normalized source/templates/assets and dependency versions;
queued exports fail closed when that retained renderer is unavailable. Finished artifact
downloads remain independent of renderer availability and admission flags.

## Evidence

- Initial presentation/export API gate: 17 passed after correcting the Windows child protocol.
  Native Windows libraries can emit diagnostics on stdout; completion now uses the child's
  exit status instead of expecting a pristine stdout marker.
- Additional real timeout/unsupported-glyph/display checks: 10 passed. Real child allocation
  beyond its memory cap is rejected. Python display/process tests: 43 passed, 94.04% focused
  coverage; display formatter coverage is 100%. The full platform suite subsequently passed
  1,093 tests with 97.81% coverage.
- Browser formatter corpus: 119 passed; browser session regression: 1 passed.
- Final Reports strict mypy: 98 source modules passed. Generated presentation assets and
  OpenAPI checks pass.
- PDF raster inspected on Windows: table alignment, explicit values, literal escaped markup,
  footer and shaped Hindi text. Wide/empty visual fixtures and XLSX metadata checks passed.
- A final wheel was built and installed into an isolated environment. A two-row functional
  fixture rendered all four formats, including a real Windows PDF child, from installed
  package assets. Final native schema and suite results are in [execution.md](execution.md).

The historical RF5 renderer performance measurements predate the shared workbook styling.
They are not substituted for end-to-end database-to-export or production SLO evidence.
