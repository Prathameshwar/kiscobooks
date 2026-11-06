/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Production serves Auth and Console on one origin. The prefix is embedded at
  // build time; the runtime auth.env alone cannot set it for an already-built app.
  // Keep a production default so a bare `next build` cannot emit Console's /_next URLs.
  assetPrefix: process.env.NEXT_ASSET_PREFIX ||
    (process.env.NODE_ENV === 'production' ? '/auth-static' : undefined),
  // @janso/ui ships TypeScript/TSX source, so Next transpiles it in-tree.
  transpilePackages: ['@janso/ui'],
};

export default nextConfig;
