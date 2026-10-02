import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // The cockpit is a client for the /api/v1 contract; it never hosts SOS
  // semantics. No custom server, no rewrites that could hide the API base.
};

export default nextConfig;
