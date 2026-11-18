import { setupServer } from "msw/node";
import { createOpenApiHttp } from "openapi-msw";

import type { paths } from "@/api/schema";

import { TEST_API_URL } from "./env";

// Handlers typed by the OpenAPI schema: a fixture of an old response shape fails tsc.
export const http = createOpenApiHttp<paths>({ baseUrl: TEST_API_URL });

export const server = setupServer();
