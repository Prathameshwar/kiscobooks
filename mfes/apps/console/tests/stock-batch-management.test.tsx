import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { StockTrackingPage } from "../app/components/StockTrackingPage";
import { serviceCall } from "../app/lib/service-call";
import {
  COMPANY,
  ITEM,
  RECORD,
  EVENT,
  trackingFixture,
} from "./stock-tracking-fixtures";
vi.mock("../app/components/ProductModeProvider", () => ({
  useProductMode: () => ({ data: { product_family_sku_enabled: true } }),
}));
vi.mock("../app/lib/service-call", async (original) => ({
  ...(await original<typeof import("../app/lib/service-call")>()),
  serviceCall: vi.fn(),
}));
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(serviceCall).mockImplementation(
    async (_endpoint, request) => trackingFixture(request) as never,
  );
});
afterEach(cleanup);
const show = (
  page: "list" | "new" | "detail" | "edit" | "history",
  access = { manage: true, hold: true },
  eventId?: string,
) =>
  render(
    <StockTrackingPage
      company={COMPANY}
      kind="batches"
      id={page === "list" || page === "new" ? undefined : RECORD}
      page={page}
      itemId={ITEM}
      access={access}
      eventId={eventId}
    />,
  );
it("lists records with accessible links and stock registration guidance", async () => {
  show("list");
  expect(
    await screen.findByRole("link", { name: "View details" }),
  ).toHaveAttribute("href", "/inventory/batches/" + RECORD);
  expect(screen.getByRole("link", { name: "Register batch" })).toBeVisible();
});
it("opens persisted details without issuing a write", async () => {
  show("detail");
  await screen.findByText("BANJARA-BATCH-001");
  expect(
    screen.getByText(/Registration alone does not create stock/),
  ).toBeVisible();
  expect(vi.mocked(serviceCall).mock.calls.some(([, r]) => r.method)).toBe(
    false,
  );
});
it("corrects dates with current version and a recorded reason", async () => {
  show("edit");
  fireEvent.change(await screen.findByLabelText("Expiry date"), {
    target: { value: "2027-12-01" },
  });
  fireEvent.change(screen.getByLabelText("Reason"), {
    target: { value: "Supplier expiry correction" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save change" }));
  await screen.findByText("Change saved.");
  expect(
    vi.mocked(serviceCall).mock.calls.find(([, r]) => r.method)![1],
  ).toMatchObject({
    method: "PATCH",
    path: `/v1/companies/${COMPANY}/stock-tracking/batches/${RECORD}`,
    body: {
      expected_version: 3,
      reason: "Supplier expiry correction",
      expires_on: "2027-12-01",
    },
  });
  expect(
    vi.mocked(serviceCall).mock.calls.find(([, r]) => r.method)![1].body,
  ).not.toHaveProperty("manufactured_on");
});
it("registers a batch without stock quantities or stock value", async () => {
  show("new");
  fireEvent.change(await screen.findByLabelText("Batch code"), {
    target: { value: "SUPPLIER-B1" },
  });
  fireEvent.change(screen.getByLabelText("Manufacture date"), {
    target: { value: "2026-11-01" },
  });
  fireEvent.change(screen.getByLabelText("Expiry date"), {
    target: { value: "2027-11-01" },
  });
  fireEvent.change(screen.getByLabelText("Reason"), {
    target: { value: "Supplier registration" },
  });
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Register batch" }),
    ).not.toBeDisabled(),
  );
  fireEvent.click(screen.getByRole("button", { name: "Register batch" }));
  await screen.findByText("Tracking record registered.");
  const body = vi.mocked(serviceCall).mock.calls.find(([, r]) => r.method)![1]
    .body;
  expect(body).not.toHaveProperty("quantity");
  expect(body).not.toHaveProperty("value");
});
it("retains input and focuses invalid dates", async () => {
  show("edit");
  fireEvent.change(await screen.findByLabelText("Expiry date"), {
    target: { value: "2020-11-01" },
  });
  fireEvent.change(screen.getByLabelText("Reason"), {
    target: { value: "Supplier expiry correction" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save change" }));
  await waitFor(() =>
    expect(screen.getByLabelText("Expiry date")).toHaveFocus(),
  );
  expect(vi.mocked(serviceCall).mock.calls.some(([, r]) => r.method)).toBe(
    false,
  );
});
it("denies date writes when the native field is protected", async () => {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, r) => {
    const result = trackingFixture(r);
    if (r.path.includes("/field-set"))
      return {
        ...(result as object),
        fields: (
          result as { fields: { key: string; writable: boolean }[] }
        ).fields.map((field) => ({
          ...field,
          writable: field.key !== "expires_on",
        })),
      } as never;
    return result as never;
  });
  show("edit");
  expect(await screen.findByLabelText("Expiry date")).toBeDisabled();
});
it("renders both paged audit history and a single event", async () => {
  const view = show("history");
  expect(
    await screen.findByRole("link", { name: "View event" }),
  ).toHaveAttribute(
    "href",
    "/inventory/batches/" + RECORD + "/history/" + EVENT,
  );
  view.unmount();
  show("history", undefined, EVENT);
  expect(await screen.findByRole("heading", { name: "correct" })).toBeVisible();
  expect(screen.getByText("2027-10-01 → 2027-11-01")).toBeVisible();
});
it("keeps retry key and body unchanged after a lost response", async () => {
  let count = 0;
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, r) => {
    if (r.method && ++count === 1)
      throw { status: 503, message: "Response lost" };
    return trackingFixture(r) as never;
  });
  show("edit");
  fireEvent.change(await screen.findByLabelText("Reason"), {
    target: { value: "Supplier expiry correction" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save change" }));
  const retry = await screen.findByRole("button", { name: "Retry same save" });
  expect(screen.getByLabelText("Reason")).toBeDisabled();
  fireEvent.click(retry);
  await screen.findByText("Change saved.");
  const writes = vi.mocked(serviceCall).mock.calls.filter(([, r]) => r.method);
  expect(writes[0]![1].key).toBe(writes[1]![1].key);
  expect(writes[0]![1].body).toEqual(writes[1]![1].body);
});
it("does not offer edits to read-only users", async () => {
  show("detail", { manage: false, hold: false });
  await screen.findByText("BANJARA-BATCH-001");
  expect(screen.queryByRole("link", { name: "Edit batch" })).toBeNull();
});

it("blocks a stale save and requires review before another attempt", async () => {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, r) => {
    if (r.method) throw { status: 409, message: "Record version changed" };
    return trackingFixture(r) as never;
  });
  show("edit");
  fireEvent.change(await screen.findByLabelText("Reason"), {
    target: { value: "Supplier expiry correction" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save change" }));
  await screen.findByText(/Record version changed/);
  expect(screen.getByRole("button", { name: "Save change" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Reload and review" }));
  expect(await screen.findByRole("dialog")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.getByLabelText("Reason")).toHaveValue(
    "Supplier expiry correction",
  );
});
it("uses the company currency and verified base unit for initial MRP", async () => {
  show("new");
  fireEvent.change(await screen.findByLabelText("Batch code"), {
    target: { value: "MRP-B1" },
  });
  fireEvent.change(screen.getByLabelText("Manufacture date"), {
    target: { value: "2026-11-01" },
  });
  fireEvent.change(screen.getByLabelText("Expiry date"), {
    target: { value: "2027-11-01" },
  });
  fireEvent.change(screen.getByLabelText("Reason"), {
    target: { value: "Supplier batch registration" },
  });
  await waitFor(() =>
    expect(screen.getByLabelText("MRP amount")).not.toBeDisabled(),
  );
  fireEvent.change(screen.getByLabelText("MRP amount"), {
    target: { value: "12.3456" },
  });
  expect(screen.getByLabelText("MRP currency")).toHaveValue("INR");
  fireEvent.click(screen.getByRole("button", { name: "Register batch" }));
  await screen.findByText("Tracking record registered.");
  expect(
    vi.mocked(serviceCall).mock.calls.find(([, r]) => r.method)![1].body,
  ).toMatchObject({
    mrp_amount: "12.3456",
    mrp_currency: "INR",
    mrp_unit_id: EVENT,
  });
});
