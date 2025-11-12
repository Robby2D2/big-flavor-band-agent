/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  experimental: {
    serverActions: {
      bodySizeLimit: '10mb',
    },
  },
  async rewrites() {
    return [
      {
        source: '/api/agent/:path*',
        destination: `${process.env.AGENT_API_URL}/api/agent/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
