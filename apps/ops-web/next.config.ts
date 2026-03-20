import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  env: {
    CONTROL_API_URL: process.env.CONTROL_API_URL ?? 'http://localhost:8000',
  },
  experimental: {
    typedRoutes: true,
  },
};

export default nextConfig;
