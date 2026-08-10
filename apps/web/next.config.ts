import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: [
    "@ecommerce-visual-workbench/ui",
    "@ecommerce-visual-workbench/editor",
    "@ecommerce-visual-workbench/templates",
  ],
};

export default nextConfig;
