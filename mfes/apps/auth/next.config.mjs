/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // @janso/ui ships TypeScript/TSX source, so Next transpiles it in-tree.
  transpilePackages: ['@janso/ui'],
};

export default nextConfig;
