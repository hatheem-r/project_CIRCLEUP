import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CircleUp",
  description: "Find out when you are actually free.",
};

// Renders static markup only: no data is fetched on the server anywhere in this app.
export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full">
      <body className="min-h-full font-sans antialiased">{children}</body>
    </html>
  );
}
