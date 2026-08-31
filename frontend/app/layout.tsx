import type { Metadata, Viewport } from "next";
import { Cairo } from "next/font/google";
import PwaRegister from "@/components/PwaRegister";
import "./globals.css";

const cairo = Cairo({
  subsets: ["arabic", "latin"],
  variable: "--font-cairo",
});

const BACKEND = process.env.BACKEND_URL ?? "http://127.0.0.1:8010";

export const viewport: Viewport = {
  themeColor: "#dc2626",
  width: "device-width",
  initialScale: 1,
};

export async function generateMetadata(): Promise<Metadata> {
  let name = "MR.Mekawy Factory ERP";
  let favicon: string | null = null;
  let appleIcon: string | null = null;

  try {
    const res = await fetch(`${BACKEND}/api/settings/public/`, { cache: "no-store" });
    if (res.ok) {
      const d = await res.json();
      name = d.company_name || name;
      favicon = d.favicon_url;
      appleIcon = d.apple_touch_icon_url;
    }
  } catch {
    // backend unreachable — fall back to defaults, page still renders
  }

  return {
    title: name,
    description: "نظام إدارة المصنع — شؤون العاملين والحضور والانصراف",
    manifest: "/manifest.webmanifest",
    appleWebApp: { capable: true, statusBarStyle: "default", title: name },
    icons: {
      icon: favicon ? [{ url: favicon, type: "image/x-icon" }] : undefined,
      apple: appleIcon ? [{ url: appleIcon }] : undefined,
    },
  };
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ar" dir="rtl" className={`${cairo.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-slate-100 text-slate-900">
        {children}
        <PwaRegister />
      </body>
    </html>
  );
}
