import { useMutation } from "@tanstack/react-query";

import { api } from "@/api/client";
import { unwrap } from "@/api/errors";
import type { Attendee, FileContentType } from "@/api/types";

import { uploadToS3, type UploadProgressListener } from "../uploadToS3";

export type NewClaim = {
  purpose: string;
  attendees: Attendee[];
  preapproval_ref: string | null;
  file: File;
  contentType: FileContentType;
};

export function useSubmitClaim(onUploadProgress?: UploadProgressListener) {
  return useMutation({
    mutationFn: async ({ file, contentType, ...details }: NewClaim) => {
      const createdClaim = await unwrap(
        api.POST("/claims", {
          body: {
            ...details,
            file: { filename: file.name, content_type: contentType, size_bytes: file.size },
          },
        }),
      );
      await uploadToS3(createdClaim.upload, file, onUploadProgress);
      return createdClaim.claim.id;
    },
  });
}
