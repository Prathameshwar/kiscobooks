import assert from "node:assert/strict";
import test from "node:test";
import { createAccountingClient } from "../src/index.ts";

test("Accounting transport preserves decimal amounts, company path and retry identity", async () => {
  const seen = [];
  const client = createAccountingClient({ baseUrl: "https://gateway.example.test/accounting", fetch: async (request) => {
    seen.push({ path: new URL(request.url).pathname,
      key: request.headers.get("Idempotency-Key"), body: await request.json() });
    return new Response(JSON.stringify({ id: "policy", limit_amount: "10000.0000" }),
      { status: 201, headers: { "content-type": "application/json" } });
  }});
  const options = { params: { path: { company_id: "company" }, header: { "Idempotency-Key": "stable-command" } },
    body: { party_id: "party", role: "CUSTOMER", limit_amount: "10000.0000", currency: "INR", valid_from: "2026-09-14" } };
  for (let attempt = 0; attempt < 2; attempt++) {
    const result = await client.POST("/v1/companies/{company_id}/party-credit-policies", options);
    assert.equal(result.data.limit_amount, "10000.0000");
  }
  assert.deepEqual(seen.map(row => row.key), ["stable-command", "stable-command"]);
  assert.equal(seen[0].path, "/accounting/v1/companies/company/party-credit-policies");
  assert.equal(seen[0].body.limit_amount, "10000.0000");
});
