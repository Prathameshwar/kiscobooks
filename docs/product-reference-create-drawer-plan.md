# Product group/type creation from product entry

User approved + New beside both selectors and a popup from the right, reusing the
existing creation UI/implementation. This refines the previously approved UI choice.

1. Reproduce missing inline create actions. Add the company-scoped type-management
   access flag and a reusable reference action wrapper using the shared Drawer.
   Reuse native master forms through an optional embedded contract; keep standalone
   routes, field metadata, custom fields, idempotency and server authorisation.
2. Group creation returns the compatible active group to the original selector.
   Type creation continues through the existing requirements form and explicit
   publication confirmation. Select only a verified published option matching the
   company, parent and product kind. Preserve the product draft on success/cancel;
   warn before discarding side-panel edits and block closing during pending or
   uncertain writes. Keep created masters as native independent records.
3. Test both product authoring modes, ordinary master/revision routes, permission
   hiding, protected fields, validation/retry, cancellation/focus, auto-selection,
   responsive alignment and three themes. Run TypeScript and review security/style.
   Record reusable tests/results; live authenticated acceptance depends on services.

No new backend route/model, migration, financial execution or permission key is
needed. The existing product-fields boundary and owning Catalog APIs remain in use.

## Todo

- [x] Inspect existing reference selectors, master editors and Drawer.
- [x] Fail-first inline-action regression: both actions absent before implementation.
- [x] Optional embedded forms and group/type Drawer workflows.
- [x] Both product modes and compatible auto-selection; isolated portal submit events.
- [x] 229 focused regression cases, TypeScript and 18 browser layout combinations;
      final manual simplification/security review and dated results.
- [ ] Live authenticated company acceptance: Identity API remains offline after
      VM shutdown. Component/geometry checks do not establish live E2E delivery.
