"use client";

import { Button } from "@/components/ui/button";
import type { ClaimRead } from "@/api/types";
import { QueryState } from "@/components/widgets/QueryState/QueryState";
import { useFileLink } from "@/features/claims/hooks/useFileLink";

export function DocumentViewer({ claim }: { claim: ClaimRead }) {
  const fileVerified = claim.document?.size_bytes != null;
  const fileLink = useFileLink(claim.id, fileVerified);

  if (!claim.document || !fileVerified) {
    return <p className="text-muted-foreground text-sm">The document has not been uploaded yet.</p>;
  }
  const { original_filename: filename, content_type: contentType } = claim.document;

  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <h2 className="truncate font-medium">{filename}</h2>
        <Button
          variant="outline"
          size="sm"
          disabled={fileLink.isFetching}
          onClick={() => void fileLink.refetch()}
        >
          Reload document
        </Button>
      </div>
      <QueryState query={fileLink}>
        {(link) =>
          contentType === "application/pdf" ? (
            <iframe
              src={link.url}
              title={filename}
              className="h-[75vh] w-full rounded-lg border"
            />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={link.url} alt={filename} className="w-full rounded-lg border" />
          )
        }
      </QueryState>
    </section>
  );
}
