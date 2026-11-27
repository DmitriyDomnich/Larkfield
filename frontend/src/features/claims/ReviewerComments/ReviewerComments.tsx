"use client";

import type { ReactNode } from "react";

import type { ClaimRead, ClaimReview } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { QueryState } from "@/components/widgets/QueryState/QueryState";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useClaimReview } from "../hooks/useClaimReview";

const DECISION_LABELS = {
  approve: "Approved",
  reject: "Rejected",
  needs_info: "Information requested",
} as const;

type ReviewerCommentsProps = {
  claim: ClaimRead;
  children?: ReactNode;
};

export function ReviewerComments({ claim, children }: ReviewerCommentsProps) {
  const review = useClaimReview(claim.id, claim.status);
  return (
    <QueryState query={review}>
      {(data) => <ReviewRounds rounds={data.rounds}>{children}</ReviewRounds>}
    </QueryState>
  );
}

function ReviewRounds({ rounds, children }: { rounds: ClaimReview["rounds"]; children?: ReactNode }) {
  const decided = rounds.filter((round) => round.decision).reverse();
  if (decided.length === 0) return null;
  const latestIndex = decided.length - 1;
  const marksLatest = decided.length > 1;
  return (
    <section className="flex flex-col gap-3">
      <h2 className="font-medium">Reviewer comments</h2>
      <ol className="flex flex-col gap-3">
        {decided.map(({ proposal_id, decision, answer }, index) => (
          <li
            key={proposal_id}
            className={cn(
              "rounded-lg border p-3 text-sm",
              index === latestIndex
                ? marksLatest && "border-primary bg-muted/40"
                : "text-muted-foreground",
            )}
          >
            {decision && (
              <>
                <p className="flex flex-wrap items-center gap-2 font-medium">
                  {DECISION_LABELS[decision.decision]}
                  <span className="text-muted-foreground font-normal">
                    · {formatDateTime(decision.created_at)}
                  </span>
                  {index === latestIndex && marksLatest && <Badge>Latest</Badge>}
                </p>
                {decision.comment && <p className="whitespace-pre-wrap">{decision.comment}</p>}
              </>
            )}
            {answer && (
              <p className="text-muted-foreground mt-2 whitespace-pre-wrap">
                Your answer: {answer.message}
              </p>
            )}
            {index === latestIndex && children}
          </li>
        ))}
      </ol>
    </section>
  );
}
