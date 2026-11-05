# Local RabbitMQ for Identity verification

RabbitMQ was absent (services, registry, executable and port checks, 2026-09-12).
The user authorized installing it. Workspace binaries and runtime state live in
ignored `.tools/`; the installed Windows services were left unchanged.

- RabbitMQ 4.3.5: official [Windows archive](https://github.com/rabbitmq/rabbitmq-server/releases/download/v4.3.5/rabbitmq-server-windows-4.3.5.zip).
  SHA256 `462e626e276f1d670c0c45e96b36298e20c13d3efdd0f3f35e879e9868b4c9ab`.
  Extract to `.tools/rabbitmq/`.
- Erlang 27.3.4.17: official [portable archive](https://github.com/erlang/otp/releases/download/OTP-27.3.4.17/otp_win64_27.3.4.17.zip).
  SHA256 `d0c9f030909eed5484a803f8a9e9e3a2d2275d3e531a4e0891cb61fd1f88697f`.
  Extract to `.tools/erlang/`.
- [Supported Erlang versions](https://www.rabbitmq.com/docs/which-erlang).

Run from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File start/win/rabbitmq-local.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File start/win/rabbitmq-local.ps1 -Action status
powershell -NoProfile -ExecutionPolicy Bypass -File start/win/test-rabbitmq-audit.ps1 -Restart
powershell -NoProfile -ExecutionPolicy Bypass -File start/win/rabbitmq-local.ps1 -Action stop
```

Only the launched PowerShell process uses the explicit execution policy. Machine
execution policy and global PATH are unchanged. The script handles duplicate inherited
PATH casing and the portable OTP configuration directory without changing user HOME.
It launches a hidden process and preserves data across restarts.

Node: `bill_identity@localhost`; AMQP `127.0.0.1:5672`; distribution
`127.0.0.1:25672`; vhost `bill_identity_test`. No management UI is exposed.
Generated credentials/cookie remain in `.tools/rabbitmq-runtime/`. Dot-source the
script with `-Action environment` to export test connection variables in a local
PowerShell process; never paste the values into chat or tracked files.

The test creates unique queues/exchanges, authenticates HMAC and RabbitMQ user identity,
checks publisher confirmation, retries a missing route, closes an unacked channel,
checks redelivery/inbox dedupe and rejects forged messages to the durable dead-letter
queue. Audit database persistence in this particular test uses its isolated SQLite
fixture; it is not evidence for the separate MySQL or Authentik release gates.

`-Restart` is restricted to this local node and tests durable delivery across a full stop/start.
