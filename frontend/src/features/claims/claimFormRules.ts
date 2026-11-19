import type { Attendee, FileContentType } from "@/api/types";


const ALLOWED_FILE_TYPES: readonly string[] = ["application/pdf", "image/jpeg", "image/png"];
const MAX_FILE_BYTES = 10 * 1024 * 1024;
const MAX_FILENAME_LENGTH = 255;
const MAX_NAME_LENGTH = 200;
const PURPOSE_LENGTH = { min: 10, max: 500 };
const PREAPPROVAL_REF = /^PA-\d{4}-\d{3}$/;
export const MAX_ANSWER_LENGTH = 1000;
export const FILE_INPUT_ACCEPT = ".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png";

export function isAllowedFileType(type: string): type is FileContentType {
  return ALLOWED_FILE_TYPES.includes(type);
}

export function getFileProblem(file: File | null): string | null {
  if (!file) return "Choose the receipt or invoice file.";
  if (!isAllowedFileType(file.type)) return "Upload a PDF, JPEG or PNG file.";
  if (file.size === 0) return "The file is empty.";
  if (file.size > MAX_FILE_BYTES) return "The file must be 10 MB or smaller.";
  if (file.name.length > MAX_FILENAME_LENGTH) return "The file name is too long.";
  return null;
}

export function getPurposeProblem(purpose: string): string | null {
  const { length } = purpose.trim();
  return length < PURPOSE_LENGTH.min || length > PURPOSE_LENGTH.max
    ? `Describe the business purpose in ${PURPOSE_LENGTH.min} to ${PURPOSE_LENGTH.max} characters.`
    : null;
}

export function getAttendeesProblem(attendees: Attendee[]): string | null {
  const complete = attendees.every(
    ({ name, company }) =>
      [name, company].every((value) => value.trim() && value.trim().length <= MAX_NAME_LENGTH),
  );
  return complete ? null : "Give every attendee a name and a company.";
}

export function getPreapprovalProblem(preapprovalRef: string): string | null {
  const ref = preapprovalRef.trim();
  return ref && !PREAPPROVAL_REF.test(ref) ? "Use the format PA-2026-114." : null;
}

export function getAnswerProblem(message: string): string | null {
  const { length } = message.trim();
  return length === 0 || length > MAX_ANSWER_LENGTH
    ? `Write your answer in 1 to ${MAX_ANSWER_LENGTH} characters.`
    : null;
}

export function toClaimDetails(attendees: Attendee[], preapprovalRef: string) {
  return {
    attendees: attendees.map(({ name, company }) => ({ name: name.trim(), company: company.trim() })),
    preapproval_ref: preapprovalRef.trim() || null,
  };
}
