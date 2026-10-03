import type { NextConfig } from "next";

/**
 * The cockpit is a client for the /api/v1 contract; it never hosts SOS
 * semantics. No custom server.
 *
 * PUB-04 wiring: the `/api/v1/*` surface is proxied SAME-ORIGIN to the API
 * (default `http://127.0.0.1:8099` for LOCAL; override with the server-side
 * `SOS_API_PROXY_TARGET` on Vercel/preview). This keeps the OAuth flow and
 * the session cookies on ONE origin — `NEXT_PUBLIC_API_BASE` stays set-but-
 * EMPTY (`""`) in this topology so the typed client keeps using relative
 * URLs. The API base is still operator configuration, never code; only
 * `NEXT_PUBLIC_*` values ever reach the browser (security gate S1).
 */
const API_PROXY_TARGET = (
  process.env.SOS_API_PROXY_TARGET ?? "http://127.0.0.1:8099"
).replace(/\/+$/, "");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${API_PROXY_TARGET}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
