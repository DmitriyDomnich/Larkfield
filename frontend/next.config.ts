import type { NextConfig } from "next";

const REQUIRED_ENV = [
  "NEXT_PUBLIC_API_URL",
  "NEXT_PUBLIC_COGNITO_REGION",
  "NEXT_PUBLIC_COGNITO_USER_POOL_ID",
  "NEXT_PUBLIC_COGNITO_APP_CLIENT_ID",
  "NEXT_PUBLIC_DOCUMENTS_ORIGIN",
];

const missingEnv = REQUIRED_ENV.filter((name) => !process.env[name]);
if (missingEnv.length > 0) {
  throw new Error(
    `Missing environment variables: ${missingEnv.join(", ")} (copy .env.example to .env.local)`,
  );
}

const nextConfig: NextConfig = {
  output: "export",
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
