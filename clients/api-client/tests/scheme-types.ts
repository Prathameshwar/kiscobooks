import type { components, paths } from "../src/catalog.js";

type Schemas = components["schemas"];
const transition: Schemas["SchemeTransition"] = {
  expected_version: 1, membership_mode: "MULTIPLE", is_required: true, is_active: true,
};
const commit: Schemas["SchemeTransitionCommit"] = { ...transition, preview_token: "reviewed" };
const membership: Schemas["CategoryAssignmentInput"] = {
  expected_version: 2,
  valid_from: "2090-02-01",
  preview_token: "reviewed",
  categories: [{ scheme_id: "scheme-id", category_id: "category-id", is_primary: true }],
};
type Preview = paths["/v1/companies/{company_id}/product-families/{object_id}/category-preview"]["post"];
const response: Preview["responses"][200]["content"]["application/json"] = {
  family_id: "family-id", expected_version: 2, valid_from: "2090-02-01",
  membership_count: 1, closing_count: 1, policy_generation: 3, source_version: 2,
  preview_token: "reviewed",
};
void commit;
void membership;
void response;
