import type { NextConfig } from "next";

// Where the FastAPI from api/ listens. The browser never talks to it
// directly: /api/v1/* is rewritten to it (same origin, no CORS change needed)
// and proxy.ts adds the bearer token from the httpOnly session cookie.
const apiUrl = (process.env.SAR_API_URL ?? "http://127.0.0.1:8100").replace(/\/$/, "");

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async redirects() {
    return [{ source: "/", destination: "/overview", permanent: false }];
  },
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${apiUrl}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
