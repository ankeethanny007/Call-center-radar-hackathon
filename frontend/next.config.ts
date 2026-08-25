import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Keep standalone tracing scoped to this application when a developer has an
  // unrelated lockfile higher up in their home directory.
  outputFileTracingRoot: path.resolve(__dirname),
};

export default nextConfig;
