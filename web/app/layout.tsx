/** GenomeOS P5 application shell (design §11). */

import type {Metadata} from "next";
import "maplibre-gl/dist/maplibre-gl.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "GenomeOS Atlas",
  description: "Explore measured observations and inferred genomic surfaces worldwide.",
};

export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
