import type { components } from "@/api/schema";

export type Role = components["schemas"]["Role"];

const EVERY_ROLE: readonly Role[] = ["employee", "reviewer", "admin"];

const PAGE_ROLES: Partial<Record<string, readonly Role[]>> = {
  "/claims": ["employee", "reviewer"],
  "/claims/new": ["employee", "reviewer"],
  "/claims/view": ["employee", "reviewer"],
  "/review": ["reviewer"],
  "/review/claim": ["reviewer"],
};

const HOME_PATHS: Record<Role, string | null> = {
  employee: "/claims",
  reviewer: "/review",
  admin: null,
};

export function canOpenPage(role: Role, path: string): boolean {
  const allowedRoles = PAGE_ROLES[path] ?? EVERY_ROLE;
  return allowedRoles.includes(role);
}

export function getHomePath(role: Role): string | null {
  return HOME_PATHS[role];
}
