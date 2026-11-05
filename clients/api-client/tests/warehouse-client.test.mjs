import assert from "node:assert/strict";
import test from "node:test";
import { createCatalogClient } from "../src/index.ts";

test("replenishment bands keep their exact scale and the retry keeps one command identity", async () => {
  const seen = [];
  const client = createCatalogClient({ baseUrl: "https://gateway.example.test", fetch: async (request) => {
    seen.push({ path: new URL(request.url).pathname,
      key: request.headers.get("Idempotency-Key"), body: await request.json() });
    return new Response(JSON.stringify({ item_id: "item", company_id: "company", generation: 4,
      scopes: [{ warehouse_id: null, safety_quantity: "5.0000", order_multiple: "10.0000" }] }),
      { status: 200, headers: { "content-type": "application/json" } });
  }});
  const options = { params: { path: { company_id: "company", object_id: "item" },
      header: { "Idempotency-Key": "same-command" } },
    body: { expected_generation: 3, expected_source_version: 2,
      scopes: [{ warehouse_id: null, purchase_binding_id: "binding", safety_quantity: "5.0000",
        reorder_quantity: "10.0000", target_quantity: "20.0000", min_order_quantity: "10.0000",
        max_order_quantity: null, order_multiple: "10.0000", lead_time_days: 7 }] } };
  for (let attempt = 0; attempt < 2; attempt++) {
    const result = await client.PUT("/v1/companies/{company_id}/items/{object_id}/replenishment-policy", options);
    assert.equal(result.data.scopes[0].safety_quantity, "5.0000");
  }
  assert.deepEqual(seen.map(row => row.key), ["same-command", "same-command"]);
  assert.equal(seen[0].path, "/v1/companies/company/items/item/replenishment-policy");
  assert.equal(seen[0].body.scopes[0].order_multiple, "10.0000");
  assert.equal(seen[0].body.scopes[0].max_order_quantity, null);
});

test("a missing stock clearance surfaces as pending without a second deactivation attempt", async () => {
  let attempts = 0;
  const client = createCatalogClient({ baseUrl: "https://gateway.example.test", fetch: async () => {
    attempts++;
    return new Response(JSON.stringify({ error: { code: "dependency_unavailable",
      message: "stock clearance pending" } }),
      { status: 503, headers: { "content-type": "application/json" } });
  }});
  const result = await client.POST("/v1/companies/{company_id}/warehouses/{object_id}/deactivate", {
    params: { path: { company_id: "company", object_id: "warehouse" },
      header: { "Idempotency-Key": "retire-once" } },
    body: { expected_version: 1 } });
  assert.equal(result.error.error.code, "dependency_unavailable");
  assert.equal(attempts, 1);
});
