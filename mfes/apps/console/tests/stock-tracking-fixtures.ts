export const COMPANY = "01900000-0000-7000-8000-000000000001",
  ITEM = "01900000-0000-7000-8000-000000000002",
  RECORD = "01900000-0000-7000-8000-000000000003",
  EVENT = "01900000-0000-7000-8000-000000000004";
export const batchFixture = {
  id: RECORD,
  company_id: COMPANY,
  item_id: ITEM,
  code: "BANJARA-BATCH-001",
  status: "ACTIVE",
  is_held: false,
  row_version: 3,
  manufactured_on: "2026-11-01",
  expires_on: "2027-11-01",
  created_at: "2026-11-01T00:00:00Z",
  updated_at: "2026-11-01T00:00:00Z",
  operational_ready: false,
};
export const serialFixture = {
  id: RECORD,
  company_id: COMPANY,
  item_id: ITEM,
  identifiers: [
    { identifier_type: "SERIAL", slot: 1, value: "BANJARA-SERIAL-001" },
  ],
  status: "ACTIVE",
  is_held: false,
  row_version: 3,
  created_at: "2026-11-01T00:00:00Z",
  updated_at: "2026-11-01T00:00:00Z",
  operational_ready: false,
};
export const sourceFixture = {
  company_id: COMPANY,
  item_id: ITEM,
  as_of: "2026-11-07",
  profile_revision_id: EVENT,
  lot_tracking: true,
  serial_tracking: true,
  expiry_required: true,
  manufacture_date_required: true,
  requirements: [
    {
      identifier_type: "SERIAL",
      namespace_rule: "COMPANY",
      min_count: 1,
      max_count: 1,
      requires_slot: false,
    },
  ],
  normalization_version: 1,
  source_digest: "a".repeat(64),
  base_unit_id: EVENT,
};
export function trackingFixture(request: {
  path: string;
  method?: string;
  body?: unknown;
}) {
  const serial = request.path.includes("/serials"),
    row = serial ? serialFixture : batchFixture;
  if (request.path.includes("/context/")) return sourceFixture;
  if (request.path.includes("/field-set")) {
    const action = new URL(
        request.path,
        "https://fixture.invalid",
      ).searchParams.get("action"),
      keys =
        action === "prepare"
          ? serial
            ? ["reason", "item_id", "lot_id", "identifiers"]
            : [
                "reason",
                "item_id",
                "code",
                "manufactured_on",
                "expires_on",
                "source_party_id",
                "mrp_amount",
                "mrp_currency",
                "mrp_unit_id",
              ]
          : action === "correct"
            ? ["reason", "expected_version", "manufactured_on", "expires_on"]
            : ["reason", "expected_version"];
    return {
      resource: serial ? "stock-serials" : "stock-batches",
      fields: keys.map((key) => ({
        key,
        label: key,
        visible: true,
        readable: true,
        writable: true,
        required: [
          "reason",
          "item_id",
          "code",
          "identifiers",
          "expected_version",
        ].includes(key),
        definition: { type: "string" },
      })),
    };
  }
  if (request.method)
    return { ...row, row_version: 4, ...(request.body as object) };
  if (request.path.endsWith("/history/" + EVENT))
    return {
      id: EVENT,
      action: "correct",
      reason: "Corrected supplier expiry",
      created_at: "2026-11-02T00:00:00Z",
      changes: [
        {
          field: "expires_on",
          before: "2027-10-01",
          after: "2027-11-01",
          changed: true,
        },
      ],
    };
  if (request.path.includes("/history?"))
    return {
      items: [
        {
          id: EVENT,
          action: "prepare",
          reason: "Supplier registration",
          created_at: "2026-11-01T00:00:00Z",
        },
      ],
      page: { limit: 25, has_more: false },
    };
  if (request.path.includes("/" + RECORD)) return row;
  if (request.path.includes("/items/" + ITEM))
    return {
      id: ITEM,
      company_id: COMPANY,
      sku: "SKU-1",
      name: "Banjara product",
      status: "ACTIVE",
    };
  return { items: [row], page: { limit: 25, has_more: false } };
}
