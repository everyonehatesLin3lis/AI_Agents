import type { NextConfig } from "next";

// The Python API (uv run python -m api.server). The browser only ever talks to this
// Node.js server; requests under /api are forwarded from here.
const API_URL = process.env.REVIEW_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
};

export default nextConfig;
