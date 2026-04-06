import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Verticals - AI Video Generator",
  description: "Create professional YouTube Shorts with AI",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased dark">
      <body className="min-h-full flex flex-col" style={{ background: '#08090a' }}>{children}</body>
    </html>
  );
}
