import type { Metadata } from "next";
import { Bebas_Neue, Cabin, Barlow_Condensed, Oswald } from "next/font/google";
import "./globals.css";
import Nav from "@/components/Nav";
import StaleBanner from "@/components/StaleBanner";
import ThemeProvider from "@/components/ThemeProvider";

const bebasNeue = Bebas_Neue({
  variable: "--font-display",
  subsets: ["latin"],
  weight: "400",
});

const cabin = Cabin({
  variable: "--font-body",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const barlowCondensed = Barlow_Condensed({
  variable: "--font-data",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const oswald = Oswald({
  variable: "--font-display-fallback",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "Waypoint",
  description: "Incentives, briefs, and schedule for ESA marathon hosts",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${bebasNeue.variable} ${cabin.variable} ${barlowCondensed.variable} ${oswald.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <ThemeProvider>
          <Nav />
          <StaleBanner />
          <main className="flex-1 max-w-5xl w-full mx-auto px-4 py-6">
            {children}
          </main>
        </ThemeProvider>
      </body>
    </html>
  );
}
