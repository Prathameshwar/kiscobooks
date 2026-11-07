import { expect, it } from "vitest";
import { trackingBody } from "../app/lib/stock-tracking-command";
const fields = [
  "reason",
  "item_id",
  "code",
  "manufactured_on",
  "expires_on",
].map((key) => ({
  key,
  visible: true,
  writable: true,
  required: ["reason", "item_id", "code"].includes(key),
}));
it("rejects reversed dates and missing reasons before issuing a command", () => {
  expect(
    trackingBody("batches", "prepare", fields, {
      code: "B1",
      item_id: "bad",
      reason: "",
      manufactured_on: "2026-12-01",
      expires_on: "2026-11-01",
    }).errors,
  ).toMatchObject({
    item_id: expect.any(String),
    reason: expect.any(String),
    expires_on: expect.any(String),
  });
});
it("does not let registration submit stock quantity or value", () => {
  const result = trackingBody("batches", "prepare", fields, {
    code: "B1",
    item_id: "01900000-0000-7000-8000-000000000001",
    reason: "Supplier registration",
    quantity: "10",
    value: "100",
  });
  expect(result.body).not.toHaveProperty("quantity");
  expect(result.body).not.toHaveProperty("value");
});
it("does not clear protected or unchanged dates when correcting one date", () => {
  const meta = [
    "reason",
    "expected_version",
    "manufactured_on",
    "expires_on",
  ].map((key) => ({
    key,
    visible: true,
    writable: true,
    required: ["reason", "expected_version"].includes(key),
  }));
  const result = trackingBody(
    "batches",
    "correct",
    meta,
    { reason: "Supplier expiry correction", expires_on: "2027-12-01" },
    3,
    null,
    { manufactured_on: "2026-11-01", expires_on: "2027-11-01" },
  );
  expect(result.body).toEqual({
    reason: "Supplier expiry correction",
    expected_version: 3,
    expires_on: "2027-12-01",
  });
  expect(result.errors).toEqual({});
});
