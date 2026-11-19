import type { UploadForm } from "@/api/types";

export class UploadFailedError extends Error {
  constructor(readonly status: number) {
    super(`S3 refused the upload with status ${status}`);
  }
}

export async function uploadToS3(upload: UploadForm, file: File): Promise<void> {
  const form = new FormData();
  for (const [name, value] of Object.entries(upload.fields)) {
    form.append(name, value);
  }
  form.append("file", file);

  const response = await fetch(upload.url, { method: "POST", body: form });
  if (!response.ok) {
    throw new UploadFailedError(response.status);
  }
}
