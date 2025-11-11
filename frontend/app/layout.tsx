import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BigFlavor Band Agent",
  description: "Discover and stream music from BigFlavor Band",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        {children}
      </body>
    </html>
  );
}
