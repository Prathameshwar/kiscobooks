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
  trackingFixture,
  sourceFixture,
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
    async (_endpoint, r) =>
      (r.path.includes("/context/")
        ? { ...sourceFixture, lot_tracking: false }
        : trackingFixture(r)) as never,
  );
});
afterEach(cleanup);
const show = (
  page: "list" | "new" | "detail" | "edit" | "history",
  access = { manage: true, hold: true },
) =>
  render(
    <StockTrackingPage
      company={COMPANY}
      kind="serials"
      id={page === "list" || page === "new" ? undefined : RECORD}
      page={page}
      itemId={ITEM}
      access={access}
    />,
  );
it("lists physical units and opens immutable identity details", async () => {
  const view = show("list");
  expect(
    await screen.findByRole("link", { name: "View details" }),
  ).toHaveAttribute("href", "/inventory/serials/" + RECORD);
  view.unmount();
  show("detail");
  expect(await screen.findByRole("heading", { name: "BANJARA-SERIAL-001" })).toBeVisible();
  expect(vi.mocked(serviceCall).mock.calls.some(([, r]) => r.method)).toBe(
    false,
  );
});
it("exposes hold changes without offering identifier edits", async () => {
  show("edit", { manage: false, hold: true });
  expect(await screen.findByLabelText("Reason")).toBeEnabled();
  expect(
    screen.getByText(/Serial identifiers and batch assignment are immutable/),
  ).toBeVisible();
  expect(screen.queryByLabelText("SERIAL 1")).toBeNull();
  fireEvent.change(screen.getByLabelText("Reason"), {
    target: { value: "Quality inspection" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save change" }));
  await screen.findByText("Change saved.");
  expect(
    vi.mocked(serviceCall).mock.calls.find(([, r]) => r.method)![1],
  ).toMatchObject({
    method: "POST",
    path: `/v1/companies/${COMPANY}/stock-tracking/serials/${RECORD}/hold`,
    body: { expected_version: 3, reason: "Quality inspection" },
  });
});
it("registers configured identifiers with a reason and no invented stock", async () => {
  show("new");
  fireEvent.change(await screen.findByLabelText("SERIAL 1"), {
    target: { value: "SERIAL-TEST-1" },
  });
  fireEvent.change(screen.getByLabelText("Reason"), {
    target: { value: "Supplier serial registration" },
  });
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Register serial" }),
    ).not.toBeDisabled(),
  );
  fireEvent.click(screen.getByRole("button", { name: "Register serial" }));
  await screen.findByText("Tracking record registered.");
  expect(
    vi.mocked(serviceCall).mock.calls.find(([, r]) => r.method)![1],
  ).toMatchObject({
    method: "POST",
    body: {
      item_id: ITEM,
      identifiers: [
        { identifier_type: "SERIAL", slot: 1, value: "SERIAL-TEST-1" },
      ],
    },
  });
});
it("uses profile IMEI slots and rejects invalid checksums", async () => {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, r) =>
    r.path.includes("/context/")
      ? ({
          ...sourceFixture,
          lot_tracking: false,
          requirements: [
            {
              identifier_type: "IMEI",
              namespace_rule: "COMPANY",
              min_count: 1,
              max_count: 2,
              requires_slot: true,
            },
          ],
        } as never)
      : (trackingFixture(r) as never),
  );
  show("new");
  fireEvent.change(await screen.findByLabelText("IMEI 1"), {
    target: { value: "123456789012345" },
  });
  fireEvent.change(screen.getByLabelText("Reason"), {
    target: { value: "Supplier registration" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Register serial" }));
  await screen.findAllByText(
    "Enter a valid 15-digit IMEI with a correct checksum.",
  );
  expect(vi.mocked(serviceCall).mock.calls.some(([, r]) => r.method)).toBe(
    false,
  );
});
it("permits a controlled retirement with native version checks", async () => {
  show("edit");
  await screen.findByLabelText("Reason");
  fireEvent.change(screen.getByLabelText("Change to make"), {
    target: { value: "retire" },
  });
  await waitFor(() =>
    expect(screen.getByLabelText("Reason")).not.toBeDisabled(),
  );
  fireEvent.change(screen.getByLabelText("Reason"), {
    target: { value: "Duplicate supplier registration" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save change" }));
  await screen.findByText("Change saved.");
  expect(
    vi.mocked(serviceCall).mock.calls.find(([, r]) => r.method)![1].path,
  ).toContain("/retire");
});
it("retains the exact serial registration when a response is lost", async () => {
  let writes = 0;
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, r) => {
    if (r.method && ++writes === 1)
      throw { status: 503, message: "Response lost" };
    return (
      r.path.includes("/context/")
        ? { ...sourceFixture, lot_tracking: false }
        : trackingFixture(r)
    ) as never;
  });
  show("new");
  fireEvent.change(await screen.findByLabelText("SERIAL 1"), {
    target: { value: "SERIAL-TEST-1" },
  });
  fireEvent.change(screen.getByLabelText("Reason"), {
    target: { value: "Supplier serial registration" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Register serial" }));
  fireEvent.click(
    await screen.findByRole("button", { name: "Retry same save" }),
  );
  await screen.findByText("Tracking record registered.");
  const requests = vi
    .mocked(serviceCall)
    .mock.calls.filter(([, r]) => r.method);
  expect(requests[0]![1].key).toBe(requests[1]![1].key);
  expect(requests[0]![1].body).toEqual(requests[1]![1].body);
});
it("opens serial history with a scoped event link", async () => {
  show("history");
  expect(
    await screen.findByRole("link", { name: "View event" }),
  ).toHaveAttribute(
    "href",
    "/inventory/serials/" +
      RECORD +
      "/history/01900000-0000-7000-8000-000000000004",
  );
});
it('requires the configured batch before serial registration',async()=>{
 vi.mocked(serviceCall).mockImplementation(async(_endpoint,r)=>trackingFixture(r)as never);show('new');fireEvent.change(await screen.findByLabelText('SERIAL 1'),{target:{value:'BATCH-SERIAL-1'}});fireEvent.change(screen.getByLabelText('Reason'),{target:{value:'Supplier serial registration'}});fireEvent.click(screen.getByRole('button',{name:'Register serial'}));await screen.findAllByText('Choose the batch required by this product.');expect(vi.mocked(serviceCall).mock.calls.some(([,r])=>r.method)).toBe(false);
});
