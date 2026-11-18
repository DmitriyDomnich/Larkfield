"use client";

import { signOut } from "aws-amplify/auth";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { PageGate } from "@/features/auth/PageGate/PageGate";
import { canOpenPage } from "@/features/auth/pageAccess";
import { useMe } from "@/features/auth/hooks/useMe";
import { cn } from "@/lib/utils";

const NAV_LINKS = [
  { href: "/claims", label: "Claims" },
  { href: "/claims/new", label: "New claim" },
  { href: "/review", label: "Review queue" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const me = useMe();
  const pathname = usePathname();
  const role = me.data?.role;
  const links = role ? NAV_LINKS.filter((link) => canOpenPage(role, link.href)) : [];

  return (
    <>
      <header className="border-b">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
          <Link href="/" className="font-semibold">
            Larkfield
          </Link>
          <nav aria-label="Main" className="flex gap-4 text-sm">
            {links.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                aria-current={pathname === link.href ? "page" : undefined}
                className={cn(
                  "text-muted-foreground hover:text-foreground",
                  pathname === link.href && "text-foreground font-medium",
                )}
              >
                {link.label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            {me.data && <span className="text-muted-foreground">{me.data.email}</span>}
            <Button variant="outline" size="sm" onClick={() => void signOut()}>
              Sign out
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        <PageGate>{children}</PageGate>
      </main>
    </>
  );
}
