import assert from "node:assert/strict";
import test from "node:test";
import { createCatalogClient } from "../src/index.ts";

test("typed transport preserves decimal strings and caller retry identity", async () => {
  const seen = [];
  const client = createCatalogClient({ baseUrl: "https://gateway.example.test", fetch: async (request) => {
    seen.push({ path: new URL(request.url).pathname,
      key: request.headers.get("Idempotency-Key"), body: await request.json() });
    return new Response(JSON.stringify({ id: "unit", company_id: "company",
      created_at: "2026-09-11T00:00:00Z", updated_at: "2026-09-11T00:00:00Z" }),
      { status: 201, headers: { "content-type": "application/json" } });
  }});
  const options = { params: { path: { company_id: "company" }, header: { "Idempotency-Key": "same-command" } },
    body: { code: "KG", name: "Kilogram", symbol: "kg", dimension: "MASS", decimal_places: 3, quantity_increment: "0.001" } };
  for (let attempt = 0; attempt < 2; attempt++) {
    const result = await client.POST("/v1/companies/{company_id}/units", options);
    assert.equal(result.data.id, "unit");
    assert.equal(Object.hasOwn(result.data, "name"), false);
  }
  assert.deepEqual(seen.map(row => row.key), ["same-command", "same-command"]);
  assert.equal(seen[0].path, "/v1/companies/company/units");
  assert.equal(seen[0].body.quantity_increment, "0.001");
});

test("dependency failure is returned without automatic command retries", async () => {
  let attempts = 0;
  const client = createCatalogClient({ baseUrl: "https://gateway.example.test", fetch: async () => {
    attempts++;
    return new Response(JSON.stringify({ error: { code: "dependency_unavailable", message: "source unavailable" } }),
      { status: 503, headers: { "content-type": "application/json" } });
  }});
  const result = await client.GET("/v1/companies/{company_id}/units", { params: { path: { company_id: "company" } } });
  assert.equal(result.error.error.code, "dependency_unavailable");
  assert.equal(attempts, 1);
});
