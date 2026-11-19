import type { components } from "./schema";

type Schemas = components["schemas"];

export type Attendee = Schemas["Attendee"];
export type ClaimRead = Schemas["ClaimRead"];
export type ClaimStatus = Schemas["ClaimStatus"];
export type ClaimReview = Schemas["ClaimReview"];
export type FileContentType = Schemas["FileSpec"]["content_type"];
export type UploadForm = Schemas["UploadForm"];
