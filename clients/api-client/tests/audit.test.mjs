import assert from "node:assert/strict";
import test from "node:test";
import { createAuditClient } from "../src/index.ts";

test("Audit client preserves scope, opaque cursor and exact Decimal evidence", async () => {
  const seen = [];
  const client = createAuditClient({ baseUrl: "https://gateway.test/audit", fetch: async request => {
    seen.push(new URL(request.url));
    return Response.json({ changes: { amount: { from: "1.0000", to: "2.5000" } } });
  } });
  const result = await client.GET("/v1/audit-events/{event_id}", {
    params: { path: { event_id: "event" }, query: { occurred_at: "2026-09-17T00:00:00Z" } },
  });
  assert.equal(result.data.changes.amount.to, "2.5000");
  assert.equal(seen[0].searchParams.get("occurred_at"), "2026-09-17T00:00:00Z");
});
