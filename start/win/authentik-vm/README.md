# Authentik Ubuntu VM

VM name: **Bill-Authentik-Ubuntu**. Ubuntu 24.04, 4 GB fixed RAM, two CPUs,
32 GB disk. The Default Switch provides internet access; the separate internal
**Bill-HostLink** switch provides a fixed connection to Windows. Application APIs,
MySQL and Redis stay on Windows.

| Link | Windows address | VM address |
|---|---|---|
| Internal `Bill-HostLink` | `192.168.247.1/30` | `192.168.247.2/30` |
| Default Switch | Managed by Windows | DHCP, used for internet access |

SSH and the Authentik tunnel use `192.168.247.2`. The public local issuer remains
`https://localhost:9443`; browser URLs, certificates and OAuth callbacks stay the same.
The internal link has no gateway or DNS configuration and does not depend on the
laptop's Wi-Fi/Ethernet address. No extra NAT or external switch is created.

Local connection details are in `connection.json`. Username is **billvm**.
Its console password and the separate Authentik `akadmin` password are in the ignored
`credentials.env`. These files and both SSH key files are excluded from Git.
Keep the private key private. SSH uses the key; password-based SSH remains disabled.

Run `start.bat`, `stop.bat` or `status.bat` from an administrator terminal.
Stop requests guest shutdown; it preserves the disk. Open Hyper-V Manager and choose
**Bill-Authentik-Ubuntu > Connect** for console login. Run `ssh.bat` for SSH once ready.
The scripts prefer the fixed adapter and preserve its saved address during VM boot.
Changes to the Default Switch's DHCP address no longer change the saved SSH destination.

For a new/existing VM that has not had the fixed link configured, run once from an
administrator PowerShell at the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File start/win/authentik-vm.ps1 -Action configure-network
```

Setup creates the internal switch and host address, adds the dedicated static-MAC VM
adapter, and installs `/etc/netplan/99-bill-host-link.yaml` with mode 600. It needs the
existing working SSH configuration for bootstrap. An unused dynamically assigned host-link
adapter is recreated with its allocated MAC fixed at creation, allowing a running VM
to be configured. The existing internet adapter is retained.

The existing pinned VM SSH key is reused for the fixed address; strict host-key checks
remain enabled. Conflicting routes, keys and guest profiles are reported and preserved.
The saved connection changes only after pinned-key SSH verifies the fixed guest address.
A DHCP-session disconnect during netplan application is followed by fixed-link verification.
An already-correct fixed-link profile is verified without reapplying guest networking.
If an old tunnel was running during initial setup, stop and start `tunnel.bat` afterward
using `stop-tunnel.bat` first.

The downloaded image, cloud-init source/ISO and disk are in `.tools/authentik-vm/`.
The original official Ubuntu download was SHA-256 verified. Its Azure-only datasource
was corrected to use the attached NoCloud ISO. `seed-corrected.iso` includes the console
password hash and correct container file ownership for future creation. Cloud-init installs Docker
and Authentik inside Ubuntu. This is separate from Docker Desktop or WSL on Windows.
Creation now prefers `seed-setup-updated.iso` when available. It preserves those
corrections and includes the Bill OAuth grants and verified-email mapping needed
by the first-run wizard. Use `../platform-setup/apply-authentik.bat` to update an
existing local provider; verify the intended person's email separately.

`start-all.bat` automatically starts or reuses the tunnel while the VM is running.
You can also run `tunnel.bat` to open a managed, detached SSH tunnel to the guest's loopback Authentik
ports at `https://localhost:9443` and `http://localhost:9000` on Windows. The localhost
issuer, certificate and browser callback work through this tunnel. `stop-tunnel.bat`
closes only the managed tunnel. Backend stop and VM stop are separate.

The managed process supervises its pinned SSH child. After a disconnect or
transient launch failure it retries after 1, 2, 4, 8 and at most 15 seconds;
the delay resets after a connection lasts 30 seconds. A retry refuses ports
occupied by another listener. `status.bat` reports VM status; use
`powershell.exe -NoProfile -ExecutionPolicy Bypass -File start/win/authentik-vm/tunnel.ps1 -Action status`
from the repository root to distinguish listening forwarding from a running
supervisor that is reconnecting. Listening ports do not establish provider readiness.
`stop-tunnel.bat` requests supervisor shutdown and closes only its managed child,
with the existing owned-process fallback if graceful shutdown exceeds five seconds.
The VM, storage, saved connection and pinned keys are retained.

The guest clock uses chrony with Hyper-V's `/dev/ptp_hyperv` reference clock.
Its `makestep 1 -1` policy corrects jumps over one second, including after laptop
sleep/resume. A stale guest clock causes OAuth callback errors because newly issued
tokens appear expired. Run `sync-time.bat` to step the guest to its trusted time
source, then start a fresh browser sign-in. Token expiry checks remain enabled.

SSH access was verified as `billvm` after correcting the datasource. Docker is installed
inside Ubuntu; all Authentik containers are healthy. The OAuth provider applied and
HTTPS discovery/RSA JWKS verification passed. The `akadmin` password was verified. The
guest needed the host network's trusted Cloud Services root CA for image downloads;
TLS verification remains enabled.
Full application login still needs an activated Identity user/tenant and local grants.
Check containers with `sudo docker compose --project-directory /opt/bill-authentik ps`.
`cloud-init status` retains the initial download error; recovery completed setup. The
active Authentik database is `authentik_ready`; failed fresh databases were preserved.
Do not delete Hyper-V checkpoints or disk files manually.
Full provider/user and TLS setup: [local login setup](../../../../docs/local-login-setup.md).

## Verification and decision record

2026-10-29: Supervise the managed pinned SSH forwarder so a disconnected child
does not silently end forwarding during a long test run. Four supervision tests
and five startup/reuse tests passed. A live check interrupted only the owned SSH
child: the same supervisor launched a replacement and both localhost ports
became ready. Evidence is in the ignored
`.test_artifacts/tenant-admin-fixes-batch1/tunnel-reconnect.json` file. This check
does not establish VM reboot or laptop suspend/resume behavior. Regression command:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Invoke-Pester -Script @('start/win/tests/tunnel-supervision.Tests.ps1','start/win/tests/start-all.Tests.ps1') -EnableExit"
```

2026-10-23: Use a dedicated internal adapter for stable host access, while retaining
the Default Switch for internet access. Follow Microsoft's
[internal-switch configuration](https://learn.microsoft.com/en-us/windows-server/virtualization/hyper-v/get-started/create-a-virtual-switch-for-hyper-v-virtual-machines)
and Netplan's [MAC matching and static addressing](https://netplan.readthedocs.io/en/stable/netplan-yaml/).
Existing project paths and the localhost OIDC issuer are preserved.

Native checks verified the fixed SSH address, trusted HTTPS discovery, OAuth redirect
with PKCE/state/nonce, and the provider login page while the VM's internet adapter was
administratively DOWN. Its original adapter and default route were restored afterward.
The persistent guest profile and Windows address stores were checked. A laptop reboot
or actual Wi-Fi network change was not performed. Evidence is in the ignored
`.tools/authentik-vm/host-link-verification.json` file.

Regression checks:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Invoke-Pester -Script start/win/tests/authentik-network.Tests.ps1 -EnableExit"
```

Manual simplification and security review found no additional issue; SSH/TLS verification
and authentication enforcement remain enabled. The named `/simplify` and `/security-review`
commands were unavailable in this session.
