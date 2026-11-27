import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { UploadFailedError, uploadToS3 } from "./uploadToS3";

const UPLOAD = {
  url: "https://documents.test/",
  fields: { key: "claims/1/doc", policy: "p" },
  expires_at: "2026-11-10T09:10:00Z",
};
const PDF = new File(["%PDF-1.7"], "receipt.pdf", { type: "application/pdf" });

class FakeRequest {
  static last: FakeRequest;
  method = "";
  url = "";
  body: FormData | null = null;
  status = 0;
  upload: { onprogress: ((event: Partial<ProgressEvent>) => void) | null } = { onprogress: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor() {
    FakeRequest.last = this;
  }

  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }

  send(body: FormData) {
    this.body = body;
  }

  progress(loaded: number, total: number, lengthComputable = true) {
    this.upload.onprogress?.({ loaded, total, lengthComputable });
  }

  finish(status: number) {
    this.status = status;
    this.onload?.();
  }
}

describe("uploadToS3", () => {
  beforeEach(() => vi.stubGlobal("XMLHttpRequest", FakeRequest));
  afterEach(() => vi.unstubAllGlobals());

  it("posts every form field, then the file, to the presigned URL", async () => {
    const done = uploadToS3(UPLOAD, PDF);
    const request = FakeRequest.last;
    request.finish(204);
    await done;

    expect([request.method, request.url]).toEqual(["POST", UPLOAD.url]);
    expect([...request.body!.keys()]).toEqual(["key", "policy", "file"]);
    expect(request.body!.get("file")).toBe(PDF);
  });

  it("reports the upload progress in percent, from 0 when sent to 100 when done", async () => {
    const percents: number[] = [];
    const done = uploadToS3(UPLOAD, PDF, (percent) => percents.push(percent));
    const request = FakeRequest.last;
    request.progress(0, 1000);
    request.progress(333, 1000);
    request.progress(500, 1000, false);
    request.progress(1000, 1000);
    request.finish(204);
    await done;

    expect(percents).toEqual([0, 0, 33, 100, 100]);
  });

  it("fails with the status when S3 refuses the upload", async () => {
    const done = uploadToS3(UPLOAD, PDF);
    FakeRequest.last.finish(403);

    await expect(done).rejects.toEqual(new UploadFailedError(403));
  });

  it("fails with status 0 on a network error", async () => {
    const done = uploadToS3(UPLOAD, PDF);
    FakeRequest.last.onerror?.();

    await expect(done).rejects.toEqual(new UploadFailedError(0));
  });
});
