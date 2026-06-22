import type { Metadata } from "next";
import { Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { NavRail } from "@/components/NavRail";

const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
});

export const metadata: Metadata = {
  title: "TippeQpongen",
  description: "Norsk Tipping kupong-optimizer",
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
    <html lang="no" className={jakarta.variable}>
      <body className="font-sans antialiased">
        <NavRail />
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  );
}
