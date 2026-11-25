import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, delay, http as s3Http } from "msw";
import { describe, expect, it, vi } from "vitest";

import { GENERIC_ERROR } from "@/api/errors";
import { CLAIM_ID, makeClaim } from "@/test/fixtures";
import { renderWithClient } from "@/test/render";
import { http, server } from "@/test/server";

import { NewClaimForm } from "./NewClaimForm";

const navigation = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: navigation.push }) }));

const UPLOAD_URL = "https://documents.test/";
const UPLOAD_FIELDS = { key: `claims/${CLAIM_ID}/doc`, "Content-Type": "application/pdf", policy: "p" };
const PDF = new File(["%PDF-1.7"], "receipt.pdf", { type: "application/pdf" });

function mockCreateClaim() {
  const bodies: unknown[] = [];
  server.use(
    http.post("/claims", async ({ request, response }) => {
      bodies.push(await request.json());
      return response(201).json({
        claim: makeClaim({ status: "pending_upload" }),
        upload: { url: UPLOAD_URL, fields: UPLOAD_FIELDS, expires_at: "2026-11-10T09:10:00Z" },
      });
    }),
  );
  return bodies;
}

// The bucket's CORS rule: the XHR upload reads the response and, with a progress listener,
// sends a preflight first
const S3_CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST",
  "Access-Control-Allow-Headers": "*",
};

function allowS3Preflight() {
  server.use(s3Http.options(UPLOAD_URL, () => new HttpResponse(null, { headers: S3_CORS })));
}

function mockS3(status = 204) {
  const fieldOrder: string[][] = [];
  allowS3Preflight();
  server.use(
    s3Http.post(UPLOAD_URL, async ({ request }) => {
      fieldOrder.push([...(await request.formData()).keys()]);
      return new HttpResponse(null, { status, headers: S3_CORS });
    }),
  );
  return fieldOrder;
}

async function fillValidForm(user = userEvent.setup()) {
  await user.type(screen.getByLabelText("Business purpose"), "Dinner with Meridian Health");
  await user.click(screen.getByRole("button", { name: "Add attendee" }));
  await user.type(screen.getByLabelText("Attendee 1 name"), "J. Weber");
  await user.type(screen.getByLabelText("Attendee 1 company"), "Meridian Health");
  await user.type(screen.getByLabelText(/Pre-approval reference/), "PA-2026-114");
  await user.upload(screen.getByLabelText(/Receipt or invoice/), PDF);
  return user;
}

describe("NewClaimForm", () => {
  it("checks the fields before sending anything", async () => {
    const bodies = mockCreateClaim();
    const user = userEvent.setup({ applyAccept: false });
    renderWithClient(<NewClaimForm />);

    await user.type(screen.getByLabelText("Business purpose"), "Too short");
    await user.click(screen.getByRole("button", { name: "Add attendee" }));
    await user.type(screen.getByLabelText(/Pre-approval reference/), "PA-26-1");
    await user.upload(
      screen.getByLabelText(/Receipt or invoice/),
      new File(["GIF89a"], "photo.gif", { type: "image/gif" }),
    );
    await user.click(screen.getByRole("button", { name: "Submit claim" }));

    expect(screen.getByText(/business purpose in 10 to 500 characters/)).toBeInTheDocument();
    expect(screen.getByText("Give every attendee a name and a company.")).toBeInTheDocument();
    expect(screen.getByText("Use the format PA-2026-114.")).toBeInTheDocument();
    expect(screen.getByText("Upload a PDF, JPEG or PNG file.")).toBeInTheDocument();
    expect(bodies).toEqual([]);
  });

  it.each([
    ["an unsupported type", new File(["GIF89a"], "photo.gif", { type: "image/gif" }), "Upload a PDF, JPEG or PNG file."],
    [
      "a file over 10 MB",
      new File([new Uint8Array(10 * 1024 * 1024 + 1)], "scan.pdf", { type: "application/pdf" }),
      "The file must be 10 MB or smaller.",
    ],
    ["an empty file", new File([], "empty.pdf", { type: "application/pdf" }), "The file is empty."],
  ])("refuses %s before any request", async (_, file, message) => {
    const bodies = mockCreateClaim();
    const fieldOrder = mockS3();
    renderWithClient(<NewClaimForm />);

    const user = await fillValidForm(userEvent.setup({ applyAccept: false }));
    await user.upload(screen.getByLabelText(/Receipt or invoice/), file);
    await user.click(screen.getByRole("button", { name: "Submit claim" }));

    expect(screen.getByText(message)).toBeInTheDocument();
    expect(bodies).toEqual([]);
    expect(fieldOrder).toEqual([]);
  });

  it("shows the upload progress under the button while the file uploads", async () => {
    mockCreateClaim();
    let finishUpload: () => void = () => {};
    allowS3Preflight();
    server.use(
      s3Http.post(UPLOAD_URL, async () => {
        await new Promise<void>((resolve) => (finishUpload = resolve));
        return new HttpResponse(null, { status: 204, headers: S3_CORS });
      }),
    );
    renderWithClient(<NewClaimForm />);

    const user = await fillValidForm();
    await user.click(screen.getByRole("button", { name: "Submit claim" }));

    const bar = await screen.findByRole("progressbar", { name: "Upload progress" });
    expect(screen.getByText("Uploading the file… 0%")).toBeInTheDocument();
    expect(bar).toHaveAttribute("aria-valuenow", "0");
    expect(bar).not.toHaveAttribute("data-state", "indeterminate");
    expect(bar.compareDocumentPosition(screen.getByRole("button", { name: "Submitting…" }))).toBe(
      Node.DOCUMENT_POSITION_PRECEDING,
    );
    finishUpload();
    await waitFor(() => expect(navigation.push).toHaveBeenCalledWith(`/claims/view?id=${CLAIM_ID}`));
  });

  it("creates the claim, posts the S3 form with the file last, then opens the claim", async () => {
    const bodies = mockCreateClaim();
    const fieldOrder = mockS3();
    renderWithClient(<NewClaimForm />);

    const user = await fillValidForm();
    await user.click(screen.getByRole("button", { name: "Submit claim" }));

    await waitFor(() => expect(navigation.push).toHaveBeenCalledWith(`/claims/view?id=${CLAIM_ID}`));
    expect(bodies).toEqual([
      {
        purpose: "Dinner with Meridian Health",
        attendees: [{ name: "J. Weber", company: "Meridian Health" }],
        preapproval_ref: "PA-2026-114",
        file: { filename: "receipt.pdf", content_type: "application/pdf", size_bytes: PDF.size },
      },
    ]);
    expect(fieldOrder).toEqual([[...Object.keys(UPLOAD_FIELDS), "file"]]);
  });

  it("links back to the claims list", () => {
    renderWithClient(<NewClaimForm />);

    expect(screen.getByRole("link", { name: "← Claims" })).toHaveAttribute("href", "/claims");
  });

  it("shows an error and stays on the form when S3 refuses the upload", async () => {
    mockCreateClaim();
    mockS3(403);
    renderWithClient(<NewClaimForm />);

    const user = await fillValidForm();
    await user.click(screen.getByRole("button", { name: "Submit claim" }));

    expect(await screen.findByText(/The file could not be uploaded/)).toBeInTheDocument();
    expect(navigation.push).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Submit claim" })).toBeEnabled();
  });

  it("disables the button while submitting and shows an API error inline", async () => {
    server.use(
      http.post("/claims", async ({ response }) => {
        await delay(50);
        return response.untyped(HttpResponse.text("", { status: 500 }));
      }),
    );
    renderWithClient(<NewClaimForm />);

    const user = await fillValidForm();
    await user.click(screen.getByRole("button", { name: "Submit claim" }));

    expect(screen.getByRole("button", { name: "Submitting…" })).toBeDisabled();
    expect(await screen.findByText(GENERIC_ERROR)).toBeInTheDocument();
    expect(navigation.push).not.toHaveBeenCalled();
  });
});
