import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Social Cockpit — Performance Intelligence",
  description: "Analytics, historical imports, campaign performance, and evidence-backed recommendations for social teams.",
  openGraph: {
    title: "Social Cockpit",
    description: "Turn performance into better posts.",
    images: [{ url: "/og.png", width: 1745, height: 909 }],
  },
  twitter: { card: "summary_large_image", images: ["/og.png"] },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
