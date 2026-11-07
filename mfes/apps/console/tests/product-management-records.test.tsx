import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { serviceCall } from "../app/lib/service-call";
import {
  SimpleProductRecord,
  simpleRecordPatch,
  verifySimpleRecord,
} from "../app/components/SimpleProductRecord";
import { ProductRecordExperience } from "../app/components/ProductRecordExperience";
import { masterConfig } from "../app/lib/catalog-masters";
import {
  fields,
  record,
  response,
  access,
  COMPANY,
  RECORD,
  SOURCE,
} from "./product-classification-fixtures";
import type { components } from "@janso/api-client/catalog";

vi.mock("../app/lib/service-call", async (original) => ({
  ...(await original<typeof import("../app/lib/service-call")>()),
  serviceCall: vi.fn(),
}));
const modeState = vi.hoisted(() => ({ advanced: false, version: 1 }));
vi.mock("../app/components/ProductModeProvider", () => ({
  useProductMode: () => ({
    company: COMPANY,
    data: {
      company_id: COMPANY,
      row_version: modeState.version,
      policy_generation: 1,
      product_family_sku_enabled: modeState.advanced,
    },
    loading: false,
    failure: null,
    refresh: vi.fn(),
  }),
}));
const product = {
  ...record("items"),
  code: "STANDARD",
  name: "Original product",
  kind: "GOODS",
  revision: "signed-product-revision",
  authoring_version: 1,
  policy_generation: 1,
  shared_custom_fields: {},
} as components["schemas"]["SimpleProductDetail"];
const metadata = [
  ...fields("catalog.item", "update").map((field) => ({
    ...field,
    key: field.key === "sku" ? "code" : field.key,
  })),
  ...fields("catalog.product_family", "update").filter(
    (field) => field.key === "description",
  ),
];
const writes = () =>
  vi
    .mocked(serviceCall)
    .mock.calls.filter(([, request]) => request.method === "PATCH");
beforeEach(() => {
  modeState.advanced = false; modeState.version = 1;
  vi.clearAllMocks();
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
    if (request.path.includes("/products/field-set"))
      return {
        company_id: COMPANY,
        authoring_version: 1,
        fields: metadata,
      } as never;
    if (request.path.includes("/products/" + RECORD))
      return {
        ...product,
        ...(request.method === "PATCH" ? (request.body as object) : {}),
      } as never;
    return response(request) as never;
  });
});
const mount = (editing = false, completed = false, canManage = true) =>
  render(
    <SimpleProductRecord
      company={COMPANY}
      config={masterConfig("items")!}
      id={RECORD}
      access={access}
      canManage={canManage}
      editing={editing}
      completed={completed}
    />,
  );

it("reads product detail and does not mutate when opening an old completion URL", async () => {
  mount(false, true);
  expect(
    await screen.findByRole("heading", { name: "Product saved" }),
  ).toBeVisible();
  expect(
    await screen.findByText(/Stock and tax effects are recorded/),
  ).toBeVisible();
  expect(writes()).toHaveLength(0);
});
it("edits the combined Simple product with its retained revision and authoring version", async () => {
  mount(true);
  const input = await screen.findByRole("textbox", { name: "Name" });
  fireEvent.change(input, { target: { value: "Revised product" } });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await screen.findByText("Changes saved.");
  expect(writes()[0]![1].path).toBe(
    `/v1/companies/${COMPANY}/products/${RECORD}`,
  );
  expect(writes()[0]![1].body).toEqual({
    name: "Revised product",
    revision: product.revision,
    authoring_version: 1,
  });
});
it("keeps an uncertain save frozen and retries with the same body and idempotency key", async () => {
  const api = vi.mocked(serviceCall),
    original = api.getMockImplementation()!;
  let attempt = 0;
  api.mockImplementation(async (endpoint, request, subject) => {
    if (request.method === "PATCH" && attempt++ === 0)
      throw { status: 503, message: "Temporary outage" };
    return original(endpoint, request, subject);
  });
  mount(true);
  fireEvent.change(await screen.findByRole("textbox", { name: "Name" }), {
    target: { value: "Recovered product" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  const retry = await screen.findByRole("button", { name: "Retry same save" });
  expect(screen.getByRole("textbox", { name: "Name" })).toBeDisabled();
  fireEvent.click(retry);
  await screen.findByText("Changes saved.");
  expect(writes()[0]![1].body).toEqual(writes()[1]![1].body);
  expect(writes()[0]![1].key).toBeTruthy();
  expect(writes()[0]![1].key).toBe(writes()[1]![1].key);
});
it("retains entries after server validation and focuses client validation failures", async () => {
  mount(true);
  const input = await screen.findByRole("textbox", { name: "Name" });
  fireEvent.change(input, { target: { value: "" } });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() => expect(input).toHaveFocus());
  expect(writes()).toHaveLength(0);
});
it("does not offer editing to a read-only viewer", async () => {
  mount(false, false, false);
  await screen.findByRole("region", { name: "Record details" });
  expect(screen.queryByRole("link", { name: "Edit product" })).toBeNull();
});
it("groups trading controls together without changing their saved boolean values", async () => {
  mount(true);
  const trading = await screen.findByRole("group", { name: "Trading" });
  const controls = within(trading).getAllByRole("checkbox");
  expect(controls).toHaveLength(2);
  controls.forEach(control => expect(control).toBeChecked());
});
it("does not silently turn a family into a Simple product", () => {
  render(
    <ProductRecordExperience
      company={COMPANY}
      config={masterConfig("product-families")!}
      id={RECORD}
      access={access}
      canManage
    />,
  );
  expect(screen.getByText(/Product Profiles are available/)).toBeVisible();
});
it("rejects a foreign company or foreign product receipt", () => {
  expect(() =>
    verifySimpleRecord({ ...product, company_id: SOURCE }, COMPANY, RECORD),
  ).toThrow();
  expect(() =>
    verifySimpleRecord({ ...product, id: SOURCE }, COMPANY, RECORD),
  ).toThrow();
});
it("does not send protected fields or an invented native version", () => {
  const limited = metadata.map((field) =>
    field.key === "code" ? { ...field, writable: false } : field,
  );
  const result = simpleRecordPatch(
    masterConfig("items")!,
    limited,
    { ...product, code: "PROTECTED", name: "Changed" },
    product,
  );
  expect(result.body).toEqual({
    name: "Changed",
    revision: product.revision,
    authoring_version: 1,
  });
});
it('retains and freezes an Advanced draft if the company switches to Simple mode', async () => {
 modeState.advanced=true;
 const props={company:COMPANY,config:masterConfig('items')!,id:RECORD,access,canManage:true,editing:true};
 const view=render(<ProductRecordExperience {...props}/>);
 fireEvent.change(await screen.findByLabelText('Name'),{target:{value:'Retained Advanced draft'}});
 modeState.advanced=false;modeState.version=2;view.rerender(<ProductRecordExperience {...props}/>);
 expect(screen.getByLabelText('Name')).toHaveValue('Retained Advanced draft');expect(screen.getByLabelText('Name')).toBeDisabled();expect(screen.getByRole('button',{name:'Save changes'})).toBeDisabled();expect(screen.getByText(/Product mode changed/)).toBeVisible();expect(writes()).toHaveLength(0);
});
