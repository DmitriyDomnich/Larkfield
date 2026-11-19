"use client";

import type { ClaimRead } from "@/api/types";
import { QueryState } from "@/components/widgets/QueryState/QueryState";

import { useFileLink } from "../hooks/useFileLink";

export function ClaimFileLink({ claim }: { claim: ClaimRead }) {
  const fileVerified = claim.document?.size_bytes != null;
  const fileLink = useFileLink(claim.id, fileVerified);

  if (!claim.document) return null;
  if (!fileVerified) {
    return <span>{claim.document.original_filename} (waiting for the upload)</span>;
  }
  return (
    <QueryState query={fileLink}>
      {(link) => (
        <a href={link.url} target="_blank" rel="noopener noreferrer" className="underline">
          {claim.document?.original_filename}
        </a>
      )}
    </QueryState>
  );
}
