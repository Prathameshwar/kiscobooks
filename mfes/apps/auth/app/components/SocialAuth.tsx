import { GoogleIcon, FacebookIcon } from '@janso/ui';

/**
 * Google / Facebook sign-in. Rendered as links to the gateway's OAuth start routes
 * (no client secrets here); the backend handles the handshake. `verb` keeps the label
 * true to the flow — "Sign in" vs "Sign up".
 */
export function SocialAuth({ verb = 'Continue' }: { verb?: string }) {
  return (
    <>
      <div className="auth__hr">or {verb.toLowerCase()} with</div>
      <div className="auth__social">
        <a className="janso-btn janso-btn--social janso-btn--block" href="/oauth/google">
          <GoogleIcon size={18} />
          {verb} with Google
        </a>
        <a className="janso-btn janso-btn--social janso-btn--block" href="/oauth/facebook">
          <FacebookIcon size={18} />
          {verb} with Facebook
        </a>
      </div>
    </>
  );
}
