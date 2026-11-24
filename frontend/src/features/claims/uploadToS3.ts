import type { UploadForm } from "@/api/types";

export class UploadFailedError extends Error {
  constructor(readonly status: number) {
    super(`S3 refused the upload with status ${status}`);
  }
}

export type UploadProgressListener = (percent: number) => void;

export function uploadToS3(
  upload: UploadForm,
  file: File,
  onProgress?: UploadProgressListener,
): Promise<void> {
  const form = new FormData();
  for (const [name, value] of Object.entries(upload.fields)) {
    form.append(name, value);
  }
  form.append("file", file);

  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", upload.url);
    request.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) {
        onProgress?.(Math.round((event.loaded / event.total) * 100));
      }
    };
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) {
        onProgress?.(100);
        resolve();
      } else {
        reject(new UploadFailedError(request.status));
      }
    };
    request.onerror = () => reject(new UploadFailedError(0));
    request.send(form);
    onProgress?.(0);
  });
}
