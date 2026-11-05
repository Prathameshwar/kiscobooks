import type { components } from "../src/catalog.js";

type Preview = components["schemas"]["DraftPreview"];
const requirements: Preview["transaction_requirements"] = ["TAX_CONTEXT", "MEASURED_QUANTITY"];
const finalCheck: Preview["final_guard_validation_required"] = true;
// @ts-expect-error Catalog cannot certify final transaction guard validation.
const skipFinalCheck: Preview["final_guard_validation_required"] = false;
// @ts-expect-error Only declared transaction requirements are accepted.
const inventedContext: Preview["transaction_requirements"] = ["NOMINAL_ALLOCATION"];
const issue: components["schemas"]["PricingIssue"] = {
  code: "SOURCE_COVERAGE_GAP", as_of: "2090-02-01", message: "Reference coverage has ended",
};
void [requirements, finalCheck, skipFinalCheck, inventedContext, issue];
