/** @type {import('next').NextConfig} */
// Internal base URL of the FastAPI backend. Set by Docker (compose / Dockerfile)
// to http://backend:8000; falls back to localhost so `next build`/dev works when
// the frontend runs outside Docker and the var is unset. Mirrors the same
// fallback used by the server-side BFF routes under app/api/.
const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

const nextConfig = {
  reactStrictMode: true,
  output: 'standalone', // For Docker deployment
  experimental: {
    serverActions: {
      bodySizeLimit: '10mb',
    },
  },
  async rewrites() {
    return [
      {
        source: '/api/agent/:path*',
        destination: `${AGENT_API_URL}/api/agent/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
