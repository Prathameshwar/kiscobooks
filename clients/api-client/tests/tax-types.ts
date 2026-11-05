import type { components } from "../src/catalog.js";

type Schemas = components["schemas"];
const release: Schemas["ReleaseInput"] = {
  expected_generation: 1,
  expected_source_version: 2,
  change_reason: "Reviewed future correction",
  changes: [{
    key: "withdrawFuture",
    kind: "WITHDRAWAL",
    definition: {
      expected_generation: 1,
      expected_source_version: 2,
      resource: "tax_rate",
      target_id: "01980000-0000-7000-8000-000000000001",
      expected_version: 1,
      reason: "Replace future schedule",
      restore_predecessor: true,
    },
  }],
};
const commit: Schemas["ReleaseCommit"] = { ...release, preview_token: "reviewed" };
const classification: Schemas["ClassificationMatch"] = {
  code_system: "HSN", code: "1234", match_kind: "PREFIX",
};
void commit;
void classification;
