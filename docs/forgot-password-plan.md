# Forgot password

1. Check the existing login and recovery pages and the deployed Authentik stages. Keep administrator-issued recovery separate from anonymous self-service.
2. Add a visible login link and a dedicated recovery page using the shared Auth shell, controls and navigation. Preserve approved return destinations. Explain administrator assistance while SMTP is absent.
3. Install an Authentik-owned self-service flow: email identification, email ownership proof, existing MFA, validated password confirmation and a return to JANSO sign-in. Keep passwords, tokens and account lookup outside the billing UI/API. Hide account existence, deny unsupported/inactive accounts, prevent account creation and limit requests.
4. Prepare configuration that enables self-service and administrator email only after SMTP is configured, preserving existing administrator links and unrelated provider flows.
5. Review security and UX, fix findings, run UI/server/deployment/native-provider checks, inspect desktop/mobile themes, build and reload Auth locally.

No billing database or API schema change is needed. Authentik owns password recovery. Email delivery remains untested until SMTP is supplied.

Completed all phases locally. See [forgot-password.md](forgot-password.md) for the flow, activation command, review corrections and validation evidence.
