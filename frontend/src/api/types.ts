import type { components } from "./schema";

type Schemas = components["schemas"];

export type Attendee = Schemas["Attendee"];
export type ClaimRead = Schemas["ClaimRead"];
export type ClaimStatus = Schemas["ClaimStatus"];
export type ClaimReview = Schemas["ClaimReview"];
export type FileLink = Schemas["FileLink"];
export type FileContentType = Schemas["FileSpec"]["content_type"];
export type UploadForm = Schemas["UploadForm"];
export type Decision = Schemas["Decision"];
export type ExtractionRead = Schemas["ExtractionRead"];
export type ReviewRound = Schemas["ReviewRound"];
export type ProposalRead = Schemas["ProposalRead"];
