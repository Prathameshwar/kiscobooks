import { expect, it } from "vitest";
import { allowedPromotionStackRequest } from "../app/lib/promotion-stack-policy";
import { allowedProductRequest } from "../app/lib/product-request-policy";
import {
  stackBody,
  verifyStack,
  type StackValues,
} from "../app/lib/promotion-stacks";
import { masterReturn } from "../app/lib/master-navigation";
const company = "01990000-0000-7000-8000-000000000001",
  id = "01990000-0000-7000-8000-000000000002",
  next = "01990000-0000-7000-8000-000000000003";
const root = `/v1/companies/${company}/promotion-stack-policies`;
it("admits only bounded native definition operations and denies runtime mutation", () => {
  for (const [method, path] of [
    ["GET", "/authoring-context"],
    ["GET", "/drafts?sort=-id&limit=25"],
    ["POST", "/drafts"],
    ["PATCH", "/drafts/" + id],
    ["POST", "/drafts/" + id + "/publish"],
    ["GET", "/revisions/" + id],
  ])
    expect(allowedProductRequest("catalog", method!, root + path)).toBe(true);
  for (const [method, path] of [
    ["POST", "/revisions"],
    ["PATCH", "/revisions/" + id],
    ["POST", "/drafts/" + id + "/activate"],
    ["GET", "/drafts?limit=201"],
    ["GET", "/drafts?limit=25&limit=50"],
    ["GET", "/revisions?status=PUBLISHED"],
    ["GET", "/drafts?other=yes"],
    ["GET", "/drafts?sort=-id#x"],
    ["POST", "/redeem"],
  ])
    expect(allowedPromotionStackRequest(method!, root + path)).toBe(false);
  expect(
    allowedPromotionStackRequest(
      "GET",
      "/v1/companies/no-id/promotion-stack-policies/drafts",
    ),
  ).toBe(false);
});
it("keeps publication references and returns inside the native master routes", () => {
  expect(masterReturn(`/masters/promotion-stack-policies/drafts/${id}`)).toBe(
    `/masters/promotion-stack-policies/drafts/${id}`,
  );
  expect(
    masterReturn(`/masters/promotion-stack-policies/revisions/${id}`),
  ).toBe(`/masters/promotion-stack-policies/revisions/${id}`);
  expect(masterReturn("/masters/promotion-stack-policies/redeem")).not.toBe(
    "/masters/promotion-stack-policies/redeem",
  );
});
it("requires ordered comparable groups, exact forward pairs and integer caps", () => {
  const values: StackValues = {
    code: "SALE",
    change_reason: "Reviewed",
    maximum_applied: "2",
    groups: [
      {
        group_id: id,
        stage: "PRODUCT_SCHEME",
        selection: "PRIORITY",
        changes_basket: true,
      },
      {
        group_id: next,
        stage: "MANUAL",
        selection: "PRIORITY",
        changes_basket: false,
      },
    ],
    permissions: [
      {
        earlier_group_id: id,
        later_group_id: next,
        include_reward_units: false,
      },
    ],
  };
  expect(stackBody(values).errors).toEqual({});
  expect(
    stackBody({ ...values, maximum_applied: "1.5" }).errors.maximum_applied,
  ).toBeDefined();
  expect(
    stackBody({ ...values, groups: [...values.groups].reverse() }).errors
      .groups,
  ).toBeDefined();
  expect(
    stackBody({
      ...values,
      groups: values.groups.map((group) => ({
        ...group,
        selection: "BEST_SINGLE",
      })),
    }).errors.groups,
  ).toBeDefined();
  expect(
    stackBody({
      ...values,
      permissions: [values.permissions[0]!, values.permissions[0]!],
    }).errors.permissions,
  ).toBeDefined();
  expect(() =>
    verifyStack(
      {
        id,
        company_id: company,
        complete: true,
        operational_ready: false,
        code: "SALE",
        version: 1,
        maximum_applied: 2,
        groups: values.groups,
        permissions: [{ earlier_group_id: next, later_group_id: id }],
      },
      company,
      id,
    ),
  ).toThrow();
});

it("does not accept a complete draft with a missing concurrency version", () => {
  expect(() =>
    verifyStack(
      {
        id,
        company_id: company,
        complete: true,
        operational_ready: false,
        policy_generation: 1,
        code: "SALE",
        maximum_applied: 1,
        status: "DRAFT",
        group_count: 0,
        permission_count: 0,
        groups: [],
        permissions: [],
      },
      company,
      id,
    ),
  ).toThrow();
});
