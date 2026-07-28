import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Spectral } from "next/font/google";

import "@/styles/globals.css";
import "katex/dist/katex.min.css";
import { Providers } from "./providers";

// Spectral carries every heading; IBM Plex Sans the body; IBM Plex Mono every
// number, code span and micro-label.
const sans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-sans",
});
const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
});
const display = Spectral({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
  variable: "--font-display",
});

export const metadata: Metadata = {
  title: "Eduverse — adaptive Python tutor",
  description:
    "An adaptive Python-learning agent: it finds where you are, then teaches one well-chosen topic at a time.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body
        className={`${sans.variable} ${mono.variable} ${display.variable} font-sans text-[15px] leading-[1.55]`}
      >
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
