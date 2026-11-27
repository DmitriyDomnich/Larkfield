import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import type { ReactNode } from "react";

import { AppShell } from "@/components/widgets/AppShell/AppShell";
import { getContentSecurityPolicy } from "@/core/csp";
import { Providers } from "@/core/providers";
import { AuthGate } from "@/features/auth/AuthGate/AuthGate";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Larkfield",
  description: "Expense intake desk",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <head>
        <meta
          httpEquiv="Content-Security-Policy"
          content={getContentSecurityPolicy(process.env.NODE_ENV === "development")}
        />
      </head>
      <body className="flex min-h-full flex-col">
        <Providers>
          <AuthGate>
            <AppShell>{children}</AppShell>
          </AuthGate>
        </Providers>
      </body>
    </html>
  );
}
