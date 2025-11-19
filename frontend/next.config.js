/** @type {import('next').NextConfig} */
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
        destination: `${process.env.AGENT_API_URL}/api/agent/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
