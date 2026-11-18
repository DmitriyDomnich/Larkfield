import type { components } from "@/api/schema";

import { http, server } from "./server";

type Role = components["schemas"]["Role"];

export function mockMe(role: Role) {
  server.use(
    http.get("/me", ({ response }) =>
      response(200).json({ sub: `${role}-1`, email: `${role}@example.com`, role }),
    ),
  );
}
