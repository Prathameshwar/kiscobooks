import { fields } from "./product-classification-fixtures";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ProductAttributeAuthoring } from "../app/components/ProductAttributeAuthoring";
import { serviceCall } from "../app/lib/service-call";
const state = vi.hoisted(() => ({ advanced: true }));
vi.mock("../app/components/ProductModeProvider", () => ({
  useProductMode: () => ({
    data: { product_family_sku_enabled: state.advanced, row_version: 1 },
    loading: false,
    failure: null,
  }),
}));
vi.mock("../app/lib/service-call", async (original) => ({
  ...(await original<typeof import("../app/lib/service-call")>()),
  serviceCall: vi.fn(),
}));
const company = "01900000-0000-7000-8000-000000000001",
  item = "01900000-0000-7000-8000-000000000002",
  family = "01900000-0000-7000-8000-000000000003",
  definition = "01900000-0000-7000-8000-000000000004";
import { attributeFixture } from "./product-authoring-fixtures";
beforeEach(() => {
  state.advanced = true;
  vi.clearAllMocks();
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) =>
    request.path.includes("/field-set")
      ? ({
          company_id: company,
          entity_type: "catalog.item",
          fields: fields("catalog.item", "create"),
        } as never)
      : request.path.endsWith("/attribute-form")
        ? (attributeFixture as never)
        : request.method
          ? ({
              family_id: family,
              family_version: 8,
              item_id: item,
              item_version: 5,
              changed_ids: [],
              policy_generation: 1,
            } as never)
          : ({ items: [], page: { limit: 50, has_more: false } } as never),
  );
});
afterEach(cleanup);
const show = (canManage = true) =>
  render(
    <ProductAttributeAuthoring
      company={company}
      itemId={item}
      canManage={canManage}
      canCreate={true}
    />,
  );
it("shows typed false values and disables all writes for read-only access", async () => {
  show(false);
  expect(await screen.findByLabelText("Warranty eligible")).toHaveValue(
    "false",
  );
  expect(screen.getByLabelText("Warranty eligible")).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "Save attributes" }),
  ).toBeDisabled();
});
it("saves native SKU specifications with the current item version", async () => {
  show();
  fireEvent.change(await screen.findByLabelText("Warranty eligible"), {
    target: { value: "true" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save attributes" }));
  await screen.findByText("Attributes saved.");
  const write = vi
    .mocked(serviceCall)
    .mock.calls.find(([, request]) => request.method === "PUT")![1];
  expect(write.path).toContain("/items/" + item + "/attributes");
  expect(write.body).toEqual({
    expected_version: 4,
    attributes: [
      { definition_id: definition, value_type: "BOOLEAN", value_boolean: true },
    ],
  });
});
it("configures declarations with both Profile and default SKU versions", async () => {
  show();
  await screen.findByLabelText("Warranty eligible");
  fireEvent.click(
    screen.getByRole("button", { name: "Configure Profile attributes" }),
  );
  fireEvent.click(screen.getByLabelText("Required before activation"));
  fireEvent.click(screen.getByRole("button", { name: "Save attributes" }));
  await screen.findByText("Attributes saved.");
  expect(
    vi
      .mocked(serviceCall)
      .mock.calls.find(([, request]) => request.method === "PUT")![1].body,
  ).toMatchObject({
    expected_version: 7,
    expected_default_item_version: 4,
    default_item_attributes: [
      {
        definition_id: definition,
        value_type: "BOOLEAN",
        value_boolean: false,
      },
    ],
  });
});
it("creates an additional draft variant through the native family endpoint", async () => {
  show();
  await screen.findByLabelText("Warranty eligible");
  fireEvent.click(screen.getByRole("button", { name: "Add variant" }));
  await waitFor(() => expect(screen.getByLabelText("SKU")).not.toBeDisabled());
  fireEvent.change(screen.getByLabelText("SKU"), {
    target: { value: "VARIANT-1" },
  });
  fireEvent.change(screen.getByLabelText("Variant name"), {
    target: { value: "Alternate product" },
  });
  fireEvent.change(screen.getByLabelText("Warranty eligible"), {
    target: { value: "false" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save variant" }));
  await screen.findByText("Variant saved.");
  expect(
    vi
      .mocked(serviceCall)
      .mock.calls.find(([, request]) => request.method === "POST")![1],
  ).toMatchObject({
    path: `/v1/companies/${company}/product-families/${family}/variants`,
    body: {
      expected_version: 7,
      item: {
        sku: "VARIANT-1",
        name: "Alternate product",
        base_unit_id: definition,
      },
    },
  });
});
it("replays an interrupted write with exactly the same key and body", async () => {
  let attempts = 0;
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
    if (request.method) {
      if (++attempts === 1) throw { status: 503, message: "Unavailable" };
      return {
        family_id: family,
        family_version: 8,
        item_id: item,
        item_version: 5,
      } as never;
    }
    return attributeFixture as never;
  });
  show();
  fireEvent.change(await screen.findByLabelText("Warranty eligible"), {
    target: { value: "true" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save attributes" }));
  fireEvent.click(
    await screen.findByRole("button", { name: "Retry same save" }),
  );
  await screen.findByText("Attributes saved.");
  const writes = vi.mocked(serviceCall).mock.calls.filter(([, r]) => r.method);
  expect(writes[0]![1].key).toBe(writes[1]![1].key);
  expect(writes[0]![1].body).toEqual(writes[1]![1].body);
});
it("rejects a form returned for another product", async () => {
  vi.mocked(serviceCall).mockResolvedValue({
    ...attributeFixture,
    item_id: family,
  } as never);
  show();
  await screen.findByText("The attribute form did not match this product.");
  expect(screen.queryByLabelText("Warranty eligible")).toBeNull();
});
it('uses the Simple aggregate guard for ordinary attribute authoring',async()=>{
 state.advanced=false;const simple={id:item,name:'Simple product',status:'DRAFT',base_unit_id:definition,base_unit_label:'Piece',can_configure:true,revision:'simple-revision',authoring_version:1,fields:attributeFixture.fields};
 vi.mocked(serviceCall).mockImplementation(async(_endpoint,r)=>r.method?{id:item,company_id:company,revision:'saved-revision',authoring_version:1}as never:simple as never);
 show();fireEvent.change(await screen.findByLabelText('Warranty eligible'),{target:{value:'true'}});fireEvent.click(screen.getByRole('button',{name:'Save attributes'}));await screen.findByText('Attributes saved.');const write=vi.mocked(serviceCall).mock.calls.find(([,r])=>r.method)![1];expect(write.path).toBe(`/v1/companies/${company}/products/${item}/attributes`);expect(write.body).toMatchObject({revision:'simple-revision',authoring_version:1,values:[{definition_id:definition,value_type:'BOOLEAN',value_boolean:true}]});expect(write.body).not.toHaveProperty('expected_version');
});
