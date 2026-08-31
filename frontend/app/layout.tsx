import type { Metadata, Viewport } from "next";
import { Cairo, Tajawal } from "next/font/google";
import PwaRegister from "@/components/PwaRegister";
import "./globals.css";

const cairo = Cairo({
  subsets: ["arabic", "latin"],
  variable: "--font-cairo",
});

// SRS section 10 asks for Tajawal on the cutting screens. Loaded here so it is
// available app-wide, but applied only via the .font-tajawal class so the HR
// screens keep the Cairo they already use.
const tajawal = Tajawal({
  subsets: ["arabic", "latin"],
  weight: ["400", "500", "700", "800"],
  variable: "--font-tajawal",
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
    <html lang="ar" dir="rtl" className={`${cairo.variable} ${tajawal.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-slate-100 text-slate-900">
        {children}
        <PwaRegister />
      </body>
    </html>
  );
}
