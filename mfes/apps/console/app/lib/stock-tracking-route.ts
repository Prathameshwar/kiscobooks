import { trackingId, type TrackingKind } from "./stock-tracking-resources";
/** Reject malformed or unsupported paths before accessing company/session state. */
export function trackingRoute(segments: string[]) {
  if (!["batches", "serials"].includes(segments[0] ?? "")) return null;
  const kind = segments[0] as TrackingKind;
  if (segments.length === 1) return { kind, page: "list" as const };
  if (segments.length === 2 && segments[1] === "new")
    return { kind, page: "new" as const };
  if (kind === 'serials' && segments.length === 2 && segments[1] === 'register')
    return { kind, page: 'register' as const };
  if (!trackingId.test(segments[1] ?? ""))
    throw new Error("Invalid tracking route");
  const id = segments[1]!;
  if (segments.length === 2) return { kind, id, page: "detail" as const };
  if (segments.length === 3 && segments[2] === "edit")
    return { kind, id, page: "edit" as const };
  if (kind === 'serials' && segments.length === 3 && segments[2] === 'replace')
    return { kind, id, page: 'replace' as const };
  if (
    segments[2] === "history" &&
    (segments.length === 3 ||
      (segments.length === 4 && trackingId.test(segments[3]!)))
  )
    return { kind, id, page: "history" as const, eventId: segments[3] };
  throw new Error("Invalid tracking route");
}
