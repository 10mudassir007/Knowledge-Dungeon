import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    // Vercel static-build expects the output directory at the repo root.
    outDir: "../dist",
  },
  server: {
    port: 5173,
    proxy: {
      // /api/foo -> http://localhost:8000/foo  (prefix stripped)
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
  },
});