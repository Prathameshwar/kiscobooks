import type { components, paths } from "../src/catalog.js";

type Schemas = components["schemas"];

// A location, and the kind a client may create: transit custody is provisioned by Catalog and is
// absent from this union, so an import cannot ask for one.
const location: Schemas["WarehouseCreate"] = {
  code: "GD1", name: "Godown one", kind: "GODOWN", timezone: "Asia/Kolkata",
};
// @ts-expect-error transit is reserved; only STORE and GODOWN are creatable.
const transit: Schemas["WarehouseCreate"] = { code: "T1", name: "Transit", kind: "INTERNAL_TRANSIT" };

// The eight typed flags are named booleans, never a JSON bag of operation keys, and a publish
// echoes the expectations the preview handed back.
const flags: Schemas["OperationFlagsInput"] = {
  allow_sale_issue: true, allow_purchase_receipt: true, allow_transfer_in: true,
  allow_transfer_out: true, allow_customer_return_receipt: false,
  allow_supplier_return_issue: false, allow_opening_stock: true, allow_adjustment: false,
};
const publish: Schemas["OperationPolicyInput"] = {
  ...flags, expected_generation: 3, expected_source_version: 2,
};

// Company and product activity defaults are explicit nulls rather than omitted keys: "no default"
// is a stated choice, and the resolver falls back to Main only when nothing is configured.
const companyDefaults: Schemas["ActivityDefaultsInput"] = {
  default_sale_warehouse_id: "01980000-0000-7000-8000-000000000001",
  default_purchase_warehouse_id: null,
  default_customer_return_warehouse_id: null,
  default_opening_warehouse_id: null,
  expected_generation: 3,
  expected_source_version: 2,
};
const productPolicy: Schemas["ItemWarehousePolicyInput"] = {
  ...companyDefaults, selection_mode: "ALLOW_LIST",
  locations: [{ warehouse_id: "01980000-0000-7000-8000-000000000001", ...flags }],
};

// Replenishment bands are exact decimal strings end to end; a number here would be a float.
const bands: Schemas["ItemReplenishmentPolicyInput"] = {
  expected_generation: 3,
  expected_source_version: 2,
  scopes: [{
    warehouse_id: null,
    purchase_binding_id: "01980000-0000-7000-8000-000000000002",
    safety_quantity: "5.0000", reorder_quantity: "10.0000", target_quantity: "20.0000",
    min_order_quantity: "10.0000", max_order_quantity: null, order_multiple: "10.0000",
    lead_time_days: 7,
  }],
};
// @ts-expect-error a quantity is a decimal string, never a JavaScript number.
const floatBand: Schemas["ReplenishmentScopeInput"]["target_quantity"] = 20;

// A release states when it takes force and why, and nothing about what it covers: Catalog builds
// the manifest from its own reviewed rows.
const release: Schemas["PolicyReleaseInput"] = {
  effective_date: "2026-10-01", change_reason: "Reviewed store enablement",
  expected_generation: 3, expected_source_version: 2,
};

// There is no route that writes an acknowledgement — those rows arrive only from a signed source
// event — so the release paths are a read, a publish and a read of one older release.
type ReleasePaths = keyof Pick<paths,
  | "/v1/companies/{company_id}/policy-releases"
  | "/v1/companies/{company_id}/policy-releases/{object_id}">;
type AckWrite = paths["/v1/companies/{company_id}/policy-releases/{object_id}"] extends { put: unknown }
  ? never : true;
const readOnlyAcknowledgement: AckWrite = true;
const releasePath: ReleasePaths = "/v1/companies/{company_id}/policy-releases";

// A location's dated primary group is a PUT on the location, and the group rollups answer per date.
type PrimaryGroup =
  paths["/v1/companies/{company_id}/warehouses/{object_id}/primary-group"]["put"];
type MemberQuery =
  paths["/v1/companies/{company_id}/warehouse-groups/{object_id}/members"]["get"]["parameters"]["query"];
const membersAtDate: MemberQuery = { valid_at: "2026-03-31" };
const assignment: NonNullable<PrimaryGroup["requestBody"]>["content"]["application/json"] = {
  group_id: "01980000-0000-7000-8000-000000000003",
  effective_from: "2026-10-01",
  expected_version: 1,
  expected_generation: 3,
};

void location; void transit; void publish; void productPolicy; void bands; void floatBand;
void release; void releasePath; void readOnlyAcknowledgement; void membersAtDate; void assignment;
