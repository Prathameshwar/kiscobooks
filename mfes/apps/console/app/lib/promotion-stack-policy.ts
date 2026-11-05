/** Closed definition-authoring boundary. No evaluation, issuance or redemption writes. */
export function allowedPromotionStackRequest(
  method: string,
  path: string,
): boolean | undefined {
  const [route = "", query = ""] = path.split("?");
  if (
    !/\/promotion-stack-policies(?:\/|$)|\/entities\/catalog[.]promotion_stack_(?:draft(?:_group|_permission)?|policy|group|permission)\/field-set$/.test(
      route,
    )
  )
    return undefined;
  if (path.split("?").length > 2 || /[%\\#]/.test(route)) return false;
  const uuid = "[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}";
  const prefix = "^/v1/companies/" + uuid;
  const params = new URLSearchParams(query),
    keys = [...params.keys()];
  if (keys.length !== new Set(keys).size) return false;
  if (
    new RegExp(
      prefix +
        "/entities/catalog[.]promotion_stack_(?:draft(?:_group|_permission)?|policy|group|permission)/field-set$",
      "i",
    ).test(route)
  )
    return (
      method === "GET" &&
      keys.every(
        (key) =>
          key === "operation" &&
          ["create", "update", "publish"].includes(params.get(key)!),
      )
    );
  if (
    new RegExp(
      prefix + "/promotion-stack-policies/authoring-context$",
      "i",
    ).test(route)
  )
    return method === "GET" && !keys.length;
  const match = new RegExp(
    prefix +
      "/promotion-stack-policies/(drafts|revisions)(?:/(" +
      uuid +
      ")(/publish)?)?$",
    "i",
  ).exec(route);
  if (!match) return false;
  if (match[3])
    return match[1] === "drafts" && method === "POST" && !keys.length;
  if (match[2])
    return (
      ["GET", ...(match[1] === "drafts" ? ["PATCH"] : [])].includes(method) &&
      !keys.length
    );
  if (method === "POST") return match[1] === "drafts" && !keys.length;
  return (
    method === "GET" &&
    keys.every((key) => {
      const value = params.get(key)!;
      return key === "limit"
        ? /^\d+$/.test(value) && +value >= 1 && +value <= 200
        : key === "cursor"
          ? value.length > 0 && value.length <= 4096
          : key === "sort"
            ? ["id", "-id", "code", "-code"].includes(value)
            : key === "q"
              ? value.trim().length >= 2 && value.length <= 200
              : key === "code"
                ? /^[A-Z0-9][A-Z0-9_.-]{0,29}$/.test(value)
                : key === "status" &&
                  match[1] === "drafts" &&
                  ["DRAFT", "PUBLISHED"].includes(value);
    })
  );
}
