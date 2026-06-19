import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allow the FastAPI backend on a different port in development
  async rewrites() {
    return [];
  },
};

export default nextConfig;
