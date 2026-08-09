import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: { sourcemap: false },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    exclude: ["e2e/**", "node_modules/**", "dist/**"],
    coverage: {
      provider: "v8", reporter: ["text", "json-summary"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/api/generated.ts", "src/test/**", "src/main.tsx", "src/app/providers.tsx", "src/app/router.tsx", "**/*.test.{ts,tsx}"],
      thresholds: { statements: 85, branches: 60, functions: 60, lines: 85 },
    },
  },
});
