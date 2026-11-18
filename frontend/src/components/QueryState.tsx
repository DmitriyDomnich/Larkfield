"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import { Loader2Icon } from "lucide-react";
import type { ReactNode } from "react";

import { getErrorMessage } from "@/api/errors";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

type QueryStateProps<T> = {
  query: UseQueryResult<T>;
  children: (data: T) => ReactNode;
};

export function QueryState<T>({ query, children }: QueryStateProps<T>) {
  if (query.isPending) {
    return (
      <div role="status" className="text-muted-foreground flex items-center gap-2 p-4 text-sm">
        <Loader2Icon className="size-4 animate-spin" aria-hidden />
        Loading…
      </div>
    );
  }
  if (query.isError) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Could not load</AlertTitle>
        <AlertDescription>
          <p>{getErrorMessage(query.error)}</p>
          <Button
            variant="outline"
            size="sm"
            disabled={query.isFetching}
            onClick={() => void query.refetch()}
          >
            Try again
          </Button>
        </AlertDescription>
      </Alert>
    );
  }
  return children(query.data);
}
