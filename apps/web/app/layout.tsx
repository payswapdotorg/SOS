import type { Metadata } from "next";
import "../styles/globals.css";

export const metadata: Metadata = {
  title: {
    default: "SOS — Mission-governed software evolution",
    template: "%s · SOS",
  },
  description:
    "Public cockpit of SOS: mission-governed software evolution. Mission, systems, evidence, candidates, assurance, decisions (ASK included), experiments, memory and activity — rendered honestly from the typed API contract.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" data-scroll-behavior="smooth">
      <body className="min-h-screen flex flex-col bg-white text-slate-900 antialiased">
        <a href="#main" className="skip-link">
          Skip to main content
        </a>
        {children}
      </body>
    </html>
  );
}
