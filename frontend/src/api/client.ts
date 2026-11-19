import { fetchAuthSession, signOut } from "aws-amplify/auth";
import createClient, { type Middleware } from "openapi-fetch";

import { apiUrl } from "@/core/config";

import type { paths } from "./schema";


const bearerToken: Middleware = {
  async onRequest({ request }) {
    const { tokens } = await fetchAuthSession();
    if (tokens) {
      request.headers.set("Authorization", `Bearer ${tokens.accessToken.toString()}`);
    }
    return request;
  },
  async onResponse({ response }) {
    if (response.status === 401) {
      await signOut();
    }
    return response;
  },
};

export const api = createClient<paths>({
  baseUrl: apiUrl,
  fetch: (request) => globalThis.fetch(request),
});
api.use(bearerToken);
