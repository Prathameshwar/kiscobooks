import { beforeEach, expect, it, vi } from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { PromotionStacks } from "../app/components/PromotionStacks";
import { serviceCall } from "../app/lib/service-call";
import type { MasterField } from "../app/lib/catalog-masters";
import nativeFields from "./promotion-stack-fields.json";
vi.mock("../app/lib/service-call", async (original) => ({
  ...(await original<typeof import("../app/lib/service-call")>()),
  serviceCall: vi.fn(),
}));
vi.mock("../app/lib/navigate", () => ({
  goTo: vi.fn(),
  signInUrl: () => "/sign-in",
}));
const api = vi.mocked(serviceCall),
  company = "01990000-0000-7000-8000-000000000001",
  id = "01990000-0000-7000-8000-000000000002",
  group = "01990000-0000-7000-8000-000000000003",
  publication = "01990000-0000-7000-8000-000000000004";
let enabled: boolean,
  published: boolean,
  incomplete: boolean,
  uncertain: boolean,
  metadata: Record<string, MasterField[]>;
const doc = () => ({
  id,
  company_id: company,
  code: "SALE",
  maximum_applied: 2,
  change_reason: "Reviewed",
  row_version: published ? 2 : 1,
  status: published ? "PUBLISHED" : "DRAFT",
  published_policy_id: published ? publication : null,
  policy_generation: 1,
  complete: !incomplete,
  operational_ready: false,
  group_count: 1,
  permission_count: 0,
  ...(incomplete
    ? {}
    : {
        groups: [
          {
            group_id: group,
            stage: "PRODUCT_SCHEME",
            selection: "PRIORITY",
            changes_basket: true,
          },
        ],
        permissions: [],
      }),
});
beforeEach(() => {
  vi.clearAllMocks();
  enabled = true;
  published = false;
  incomplete = false;
  uncertain = false;
  metadata = structuredClone(nativeFields) as Record<string, MasterField[]>;
  api.mockImplementation(async (_endpoint, request) => {
    const url = new URL(request.path, "https://test.invalid"),
      path = url.pathname;
    if (path.endsWith("/field-set"))
      return {
        company_id: company,
        entity_type: path.split("/").at(-2),
        fields:
          metadata[
            path.split("/").at(-2)!.replace("catalog.", "") +
              ":" +
              (url.searchParams.get("operation") ?? "read")
          ],
      } as never;
    if (path.endsWith("/authoring-context"))
      return {
        company_id: company,
        enabled,
        operational_ready: false,
      } as never;
    if (path.endsWith("/publish")) {
      published = true;
      return doc() as never;
    }
    if (path.endsWith("/drafts/" + id)) return doc() as never;
    if (path.endsWith("/revisions/" + publication))
      return {
        ...doc(),
        id: publication,
        version: 1,
        source_sha256: "a".repeat(64),
        published_at: "2026-10-27T00:00:00Z",
      } as never;
    if (path.endsWith("/drafts") && request.method === "POST") {
      if (uncertain) {
        uncertain = false;
        throw { status: 503, message: "Save result uncertain" };
      }
      return doc() as never;
    }
    if (path.endsWith("/drafts") || path.endsWith("/revisions"))
      return {
        items: [doc()],
        page: { limit: 25, has_more: false, next_cursor: null },
      } as never;
    throw { status: 404, message: "Unexpected request" };
  });
});
const access = { manage: true, publish: true };
it("creates a draft with shared controls and preserves the exact uncertain retry", async () => {
  uncertain = true;
  render(
    <PromotionStacks
      company={company}
      detail
      published={false}
      access={access}
    />,
  );
  fireEvent.change(
    await screen.findByRole("textbox", { name: "Policy code" }),
    { target: { value: "SALE" } },
  );
  fireEvent.change(screen.getByRole("textbox", { name: "Change reason" }), {
    target: { value: "Reviewed" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Add offer group" }));
  fireEvent.click(screen.getByRole("button", { name: "Save policy draft" }));
  fireEvent.click(await screen.findByRole("button", { name: "Retry save" }));
  expect(
    await screen.findByRole("link", { name: "Open saved draft" }),
  ).toHaveAttribute("href", "/masters/promotion-stack-policies/drafts/" + id);
  const writes = api.mock.calls
    .map((call) => call[1])
    .filter((request) => request.method === "POST");
  expect(writes).toHaveLength(2);
  expect(writes[0]!.key).toBe(writes[1]!.key);
  expect(writes[0]!.body).toEqual(writes[1]!.body);
});
it("requires explicit confirmation and retains the published policy link after refresh", async () => {
  render(
    <PromotionStacks
      company={company}
      detail
      id={id}
      published={false}
      access={access}
    />,
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "Review and publish" }),
  );
  expect(api.mock.calls.some((call) => call[1].path.endsWith("/publish"))).toBe(
    false,
  );
  fireEvent.click(
    within(screen.getByRole("dialog")).getByRole("button", {
      name: "Publish policy",
    }),
  );
  expect(
    await screen.findByRole("link", { name: "Open published policy" }),
  ).toHaveAttribute(
    "href",
    "/masters/promotion-stack-policies/revisions/" + publication,
  );
  await waitFor(() =>
    expect(screen.getByRole("textbox", { name: "Policy code" })).toBeDisabled(),
  );
  expect(
    screen.getByRole("link", { name: "Open published policy" }),
  ).toBeVisible();
});
it("keeps read-denied child collections protected rather than replacing them with empty arrays", async () => {
  incomplete = true;
  render(
    <PromotionStacks
      company={company}
      detail
      id={id}
      published={false}
      access={access}
    />,
  );
  expect(
    await screen.findByText(/complete native policy cannot be reviewed/),
  ).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Save policy draft" }),
  ).toBeDisabled();
  expect(
    screen.queryByRole("button", { name: "Add offer group" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Review and publish" }),
  ).not.toBeInTheDocument();
});
it("renders published content without mutable actions", async () => {
  published = true;
  render(
    <PromotionStacks
      company={company}
      detail
      id={publication}
      published
      access={access}
    />,
  );
  expect(
    await screen.findByText(/Published policy content is immutable/),
  ).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Save policy draft" }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Add offer group" }),
  ).toBeDisabled();
});
it("keeps history readable and new drafts unavailable when the feature is off", async () => {
  enabled = false;
  render(
    <PromotionStacks
      company={company}
      detail={false}
      published={false}
      access={access}
    />,
  );
  expect(
    await screen.findByText(/Enable Sales promotion definitions/),
  ).toBeVisible();
  expect(
    screen.queryByRole("link", { name: "New policy draft" }),
  ).not.toBeInTheDocument();
  expect(
    await screen.findByRole("table", { name: "Policy drafts" }),
  ).toBeVisible();
});
