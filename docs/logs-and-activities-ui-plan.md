# Logs and activities UI delivery

Authorized: one Administer entry opening two cards, plus proper Audit logs and
Activities layout, controls and shared styles. Preserve independent company and
field authorization, signed paging, protected exports and immutable evidence.

1. Add a company-bound hub and permission-aware cards. Consolidate navigation;
   retain direct audit/activity URLs, correct active navigation and back links.
2. Improve the list surfaces, filter alignment, readable long identifiers and
   responsive audit detail/diff display in shared CSS. Add refresh and consistent
   empty/error/loading feedback without changing native data or query contracts.
3. Run page, navigation, audit/activity, shared UI and type checks; inspect actual
   components at desktop/mobile widths in all themes; review and fix findings.
   Record reusable findings/results, preserve concurrent authentication work.

- [x] Hub, scoped card access and navigation.
- [x] Audit/Activities presentation and shared CSS fixes.
- [x] Regression, browser and final security/simplification review.

Completed 2026-10-30. See [review and reusable checks](logs-and-activities-ui-review.md)
and [CSV results](testing/tenant-admin/logs-and-activities-ui-results.csv).

No API, database, grant or application-data changes are planned. Live VM login
is unavailable; browser fixtures exercise real components/styles separately
from the existing native authorization tests.
