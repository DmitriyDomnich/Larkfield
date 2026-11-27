import type { Decision } from "@/api/types";

export const DECISION_LABELS: Record<Decision, string> = {
  approve: "Approve",
  reject: "Reject",
  needs_info: "Request information",
};
