"use client";

import { useRouter } from "next/navigation";
import type { MouseEvent, ReactNode } from "react";

import { TableRow } from "@/components/ui/table";

export function LinkRow({ href, children }: { href: string; children: ReactNode }) {
  const router = useRouter();

  function handleClick(event: MouseEvent<HTMLTableRowElement>) {
    const target = event.target as HTMLElement;
    if (target.closest("a")) return;
    router.push(href);
  }

  return (
    <TableRow onClick={handleClick} className="cursor-pointer">
      {children}
    </TableRow>
  );
}
