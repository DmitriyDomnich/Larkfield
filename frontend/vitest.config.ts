import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

import { TEST_ENV } from "./src/test/env";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    env: TEST_ENV,
    // needed for vi.mock("aws-amplify/auth") to reach Amplify UI's own imports
    server: { deps: { inline: [/@aws-amplify\//] } },
  },
});
