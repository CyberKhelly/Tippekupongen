import type { Metadata } from "next";
import { Inter, Geist, Geist_Mono, Space_Grotesk, Barlow_Condensed } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { NavRail } from "@/components/NavRail";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const geist = Geist({
  subsets: ["latin"],
  variable: "--font-heading",
  weight: ["400", "500", "600", "700", "800"],
  display: "swap",
});

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

const geistMono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

const barlowCondensed = Barlow_Condensed({
  subsets: ["latin"],
  variable: "--font-condensed",
  weight: ["700", "800", "900"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "TippeIQ",
  description: "Kupong-optimering for Norsk Tipping",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="no" className={`${inter.variable} ${geist.variable} ${spaceGrotesk.variable} ${geistMono.variable} ${barlowCondensed.variable}`}>
      <body className="font-sans antialiased">
        <Providers>
          <NavRail />
          {children}
        </Providers>
      </body>
    </html>
  );
}
