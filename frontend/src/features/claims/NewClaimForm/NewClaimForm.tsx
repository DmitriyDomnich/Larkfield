"use client";

import { useRouter } from "next/navigation";
import { useState, type SubmitEvent } from "react";

import { getErrorMessage } from "@/api/errors";
import type { Attendee } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { FormError } from "@/components/widgets/FormError/FormError";

import { AttendeesFields } from "../AttendeesFields/AttendeesFields";
import {
  FILE_INPUT_ACCEPT,
  getAttendeesProblem,
  getFileProblem,
  getPreapprovalProblem,
  getPurposeProblem,
  isAllowedFileType,
  toClaimDetails,
} from "../claimFormRules";
import { useSubmitClaim } from "../hooks/useSubmitClaim";
import { UploadFailedError } from "../uploadToS3";

const UPLOAD_FAILED =
  "The file could not be uploaded. Check your connection and submit the claim again.";

type FormProblems = Partial<Record<"purpose" | "attendees" | "preapprovalRef" | "file", string | null>>;

export function NewClaimForm() {
  const router = useRouter();
  const submitClaim = useSubmitClaim();
  const [purpose, setPurpose] = useState("");
  const [attendees, setAttendees] = useState<Attendee[]>([]);
  const [preapprovalRef, setPreapprovalRef] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [problems, setProblems] = useState<FormProblems>({});

  function handleSubmit(event: SubmitEvent) {
    event.preventDefault();
    const found: FormProblems = {
      purpose: getPurposeProblem(purpose),
      attendees: getAttendeesProblem(attendees),
      preapprovalRef: getPreapprovalProblem(preapprovalRef),
      file: getFileProblem(file),
    };
    setProblems(found);
    if (Object.values(found).some(Boolean) || !file || !isAllowedFileType(file.type)) {
      return;
    }
    submitClaim.mutate(
      {
        purpose: purpose.trim(),
        ...toClaimDetails(attendees, preapprovalRef),
        file,
        contentType: file.type,
      },
      { onSuccess: (claimId) => router.push(`/claims/view?id=${claimId}`) },
    );
  }

  const submitError =
    submitClaim.error instanceof UploadFailedError
      ? UPLOAD_FAILED
      : submitClaim.error && getErrorMessage(submitClaim.error);

  return (
    <Card className="mx-auto max-w-2xl">
      <CardHeader>
        <CardTitle>New claim</CardTitle>
      </CardHeader>
      <CardContent>
        <form noValidate onSubmit={handleSubmit} className="flex flex-col gap-5">
          <div className="flex flex-col gap-1">
            <Label htmlFor="purpose">Business purpose</Label>
            <Textarea
              id="purpose"
              value={purpose}
              onChange={(event) => setPurpose(event.target.value)}
              placeholder="Dinner with Meridian Health to discuss the 2027 contract"
            />
            <FormError message={problems.purpose} />
          </div>

          <div className="flex flex-col gap-1">
            <AttendeesFields attendees={attendees} onChange={setAttendees} />
            <FormError message={problems.attendees} />
          </div>

          <div className="flex flex-col gap-1">
            <Label htmlFor="preapproval-ref">Pre-approval reference (if you have one)</Label>
            <Input
              id="preapproval-ref"
              value={preapprovalRef}
              onChange={(event) => setPreapprovalRef(event.target.value)}
              placeholder="PA-2026-114"
            />
            <FormError message={problems.preapprovalRef} />
          </div>

          <div className="flex flex-col gap-1">
            <Label htmlFor="file">Receipt or invoice (PDF, JPEG or PNG, up to 10 MB)</Label>
            <Input
              id="file"
              type="file"
              accept={FILE_INPUT_ACCEPT}
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
            <FormError message={problems.file} />
          </div>

          <FormError message={submitError} />
          <Button type="submit" className="self-start" disabled={submitClaim.isPending}>
            {submitClaim.isPending ? "Submitting…" : "Submit claim"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
