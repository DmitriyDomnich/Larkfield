"use client";

import { useState, type SubmitEvent } from "react";

import { getErrorMessage } from "@/api/errors";
import type { Attendee, ClaimRead } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { FormError } from "@/components/widgets/FormError/FormError";

import { AttendeesFields } from "../AttendeesFields/AttendeesFields";
import {
  getAnswerProblem,
  getAttendeesProblem,
  getPreapprovalProblem,
  toClaimDetails,
} from "../claimFormRules";
import { useAnswerClaim } from "../hooks/useAnswerClaim";

export function AnswerForm({ claim }: { claim: ClaimRead }) {
  if (claim.status !== "needs_info") return null;
  return <AnswerFields claim={claim} />;
}

function AnswerFields({ claim }: { claim: ClaimRead }) {
  const answerClaim = useAnswerClaim(claim.id);
  const [message, setMessage] = useState("");
  const [attendees, setAttendees] = useState<Attendee[]>(claim.attendees);
  const [preapprovalRef, setPreapprovalRef] = useState(claim.preapproval_ref ?? "");
  const [problems, setProblems] = useState<Record<string, string | null>>({});

  function handleSubmit(event: SubmitEvent) {
    event.preventDefault();
    const found = {
      message: getAnswerProblem(message),
      attendees: getAttendeesProblem(attendees),
      preapprovalRef: getPreapprovalProblem(preapprovalRef),
    };
    setProblems(found);
    if (Object.values(found).some(Boolean)) return;
    answerClaim.mutate({ message: message.trim(), ...toClaimDetails(attendees, preapprovalRef) });
  }

  return (
    <form noValidate onSubmit={handleSubmit} className="mt-4 flex flex-col gap-4 border-t pt-4">
      <h2 className="font-medium">Answer the reviewer</h2>
      <div className="flex flex-col gap-1">
        <Label htmlFor="answer-message">Your answer</Label>
        <Textarea
          id="answer-message"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
        />
        <FormError message={problems.message} />
      </div>
      <div className="flex flex-col gap-1">
        <AttendeesFields attendees={attendees} onChange={setAttendees} />
        <FormError message={problems.attendees} />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="answer-preapproval-ref">Pre-approval reference</Label>
        <Input
          id="answer-preapproval-ref"
          value={preapprovalRef}
          onChange={(event) => setPreapprovalRef(event.target.value)}
          placeholder="PA-2026-114"
        />
        <FormError message={problems.preapprovalRef} />
      </div>
      <FormError message={answerClaim.error && getErrorMessage(answerClaim.error)} />
      <Button type="submit" className="self-start" disabled={answerClaim.isPending}>
        {answerClaim.isPending ? "Sending…" : "Send answer"}
      </Button>
    </form>
  );
}
