"use client";

import type { ClaimRead, ClaimReview } from "@/api/types";
import { QueryState } from "@/components/widgets/QueryState/QueryState";
import { formatDateTime } from "@/lib/format";

import { useClaimReview } from "../hooks/useClaimReview";

const DECISION_LABELS = {
  approve: "Approved",
  reject: "Rejected",
  needs_info: "Information requested",
} as const;

export function ReviewerComments({ claim }: { claim: ClaimRead }) {
  const review = useClaimReview(claim.id, claim.status);
  return <QueryState query={review}>{(data) => <ReviewRounds rounds={data.rounds} />}</QueryState>;
}

function ReviewRounds({ rounds }: { rounds: ClaimReview["rounds"] }) {
  const decided = rounds.filter((round) => round.decision);
  if (decided.length === 0) return null;
  return (
    <section className="flex flex-col gap-3">
      <h2 className="font-medium">Reviewer comments</h2>
      <ol className="flex flex-col gap-3">
        {decided.map(({ proposal_id, decision, answer }) => (
          <li key={proposal_id} className="rounded-lg border p-3 text-sm">
            {decision && (
              <>
                <p className="font-medium">
                  {DECISION_LABELS[decision.decision]}
                  <span className="text-muted-foreground font-normal">
                    {" "}
                    · {formatDateTime(decision.created_at)}
                  </span>
                </p>
                {decision.comment && <p className="whitespace-pre-wrap">{decision.comment}</p>}
              </>
            )}
            {answer && (
              <p className="text-muted-foreground mt-2 whitespace-pre-wrap">
                Your answer: {answer.message}
              </p>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
