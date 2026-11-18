import type { components } from "@/api/schema";
import { Badge } from "@/components/ui/badge";

type ClaimStatus = components["schemas"]["ClaimStatus"];
type BadgeVariant = "default" | "secondary" | "destructive" | "outline";

const STATUS_BADGES: Record<ClaimStatus, { label: string; variant: BadgeVariant }> = {
  pending_upload: { label: "Waiting for upload", variant: "outline" },
  uploaded: { label: "Uploaded", variant: "outline" },
  extracting: { label: "Reading document", variant: "outline" },
  extracted: { label: "Read", variant: "secondary" },
  in_review: { label: "In review", variant: "secondary" },
  needs_info: { label: "Needs information", variant: "outline" },
  approved: { label: "Approved", variant: "default" },
  rejected: { label: "Rejected", variant: "destructive" },
  failed: { label: "Failed", variant: "destructive" },
};

export function StatusBadge({ status }: { status: ClaimStatus }) {
  const { label, variant } = STATUS_BADGES[status];
  return <Badge variant={variant}>{label}</Badge>;
}
