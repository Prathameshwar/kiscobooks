# Change password

> **Provider note (2026-10-31).** This page describes the Authentik flow. With `local` (the default) **Change password** opens a form in the Auth app itself: current password, new password twice (6–128 characters, different from the current one). A successful change ends every session and refresh token for the account, so you sign in again with the new password. There is no MFA step. See [local authentication](local-auth.md).

Open the top-right account menu and choose **Change password**, immediately above
the separator and **Sign out**. The branded Auth page opens the authenticated
Authentik flow in the same tab. Enter your current password, complete configured MFA,
then enter the new password twice. Passwords accept 6–128 Unicode characters and
must differ from the current password. Authentik displays the completion message.

Apply `start/win/registration/apply-password-change.bat` once per deployment.
The native flow is `https://localhost:9443/if/flow/bill-password-change/` locally;
production uses the configured trusted Authentik issuer origin. Passwordless or
external accounts manage their credentials through their sign-in provider.

Cancel returns to the application without changing the password. After completion,
return to JANSO and use its protected Sign out, then sign in with the new password.
A password update alone does not promise revocation of already-issued OIDC or
billing tokens. JANSO does not infer success from URL query flags, store the password,
or call a privileged password-reset API.
