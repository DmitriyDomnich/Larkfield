"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { LoadingSpinner } from "@/components/widgets/LoadingSpinner/LoadingSpinner";
import { QueryState } from "@/components/widgets/QueryState/QueryState";

import { canOpenPage } from "../pageAccess";
import { useMe } from "../hooks/useMe";

export function PageGate({ children }: { children: ReactNode }) {
  const me = useMe();
  const pathname = usePathname();
  const router = useRouter();
  const allowed = me.data ? canOpenPage(me.data.role, pathname) : null;

  useEffect(() => {
    if (allowed === false) {
      router.replace("/");
    }
  }, [allowed, router]);

  return <QueryState query={me}>{() => (allowed ? children : <LoadingSpinner />)}</QueryState>;
}
