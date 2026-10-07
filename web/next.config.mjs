const apiUrl = process.env.API_URL || "http://localhost:8001";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // The browser only ever calls same-origin /api/*; Next proxies it to the API.
  // No CORS middleware anywhere.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};

export default nextConfig;
