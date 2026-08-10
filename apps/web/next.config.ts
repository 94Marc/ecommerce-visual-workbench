import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: [
    "@ecommerce-visual-workbench/ui",
    "@ecommerce-visual-workbench/editor",
    "@ecommerce-visual-workbench/templates",
  ],
  webpack(config) {
    // Konva's Node entry optionally loads node-canvas; the editor is browser-only.
    config.resolve.alias.canvas = false;
    return config;
  },
};

export default nextConfig;
