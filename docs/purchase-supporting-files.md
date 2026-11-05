# Purchase supporting files

Decision, 2026-10-31: the user will deploy to a VM and selected private local disk
for Purchase supporting files. This does not select Design's brand-asset storage
or a print renderer. Print remains outside the Purchase API task.

Set `VOUCHERS_SUPPORTING_FILE_ROOT` to an **absolute private directory** on a durable
VM volume, outside nginx and Next public directories. The Vouchers service account
must exclusively own its directories; other local users must not replace paths or
create links there. Back up this volume **together with the Vouchers database**.
An unset root disables uploads. Moving hosts requires restoring both resources;
multiple Vouchers instances need this same private volume or must serve one VM.

The dedicated Console `/api/purchase-files` boundary uses the normal session, origin,
company-step-up and gateway authorization mechanisms. It accepts only exact Purchase
file endpoints; its larger limit does not enlarge the ordinary product proxy.

Uploads require an existing editable Purchase, its current row version, `vouchers.edit`
and readable/writable `attachments`. The server verifies base64, non-empty size up to
10 MiB, media signature (PDF/PNG/JPEG) or UTF-8 text and SHA-256. These are byte and
format checks, **not malware scanning**. Filenames are display metadata; the server
derives tenant/company/voucher/hash paths and refuses links/traversal. A complete
fsynced temporary file is published exclusively; existing content is never overwritten.
Disk work happens before the registration transaction.

Registration and its reference-only audit event are atomic and idempotent. The command
identity includes hash/size, not base64 bytes. An upload stages evidence. Apply details
and save a revision to link it to the bill. Arbitrary new keys, cross-voucher references
and altered hash/type/size are refused. Unchanged legacy foundation metadata is
preserved but grants no byte access through this adapter.

Downloads require a reference in the selected current or historical revision, a fresh
120-second actor/company/permission/revision-bound ticket, and current read authority.
The server checks hash/size again. Responses are private, attachment-only, no-store,
nosniff and sandboxed. The browser also verifies downloaded bytes. No public/static URLs
or filesystem paths are exposed.

Removal changes a later revision only. Registered files and historical links are
retained; there is no hard-delete endpoint. Abandoned uploads can leave staged
registrations or unregistered files. The conservative default retains them; monitor
their disk usage. Until an audited cleanup job is delivered, do not run directory-age
deletion against this store. Inspect orphan candidates during a maintenance window
with uploads stopped, and retain anything referenced by **any** revision or registration.
Automated orphan cleanup remains an explicit follow-up.

## Decision log

- 2026-10-31: User selected VM-local disk for Purchase. Added private configurable
  storage, immutable registrations, revision binding and authorized ticket downloads.
  No malware-scanning service or automated retention deletion was selected/claimed.
