import type { MetadataRoute } from "next";

const BACKEND = process.env.BACKEND_URL ?? "http://127.0.0.1:8010";

// Regenerated on every request (not cached) so a freshly uploaded favicon
// shows up in the install prompt without a redeploy.
export const dynamic = "force-dynamic";

export default async function manifest(): Promise<MetadataRoute.Manifest> {
  let name = "MR.Mekawy Factory ERP";
  let icon192: string | null = null;
  let icon512: string | null = null;

  try {
    const res = await fetch(`${BACKEND}/api/settings/public/`, { cache: "no-store" });
    if (res.ok) {
      const d = await res.json();
      name = d.company_name || name;
      icon192 = d.icon_192_url;
      icon512 = d.icon_512_url;
    }
  } catch {
    // backend unreachable at manifest-build time — fall back to defaults
  }

  const icons: MetadataRoute.Manifest["icons"] = [];
  if (icon192) {
    icons.push(
      { src: icon192, sizes: "192x192", type: "image/png", purpose: "any" },
      { src: icon192, sizes: "192x192", type: "image/png", purpose: "maskable" }
    );
  }
  if (icon512) {
    icons.push(
      { src: icon512, sizes: "512x512", type: "image/png", purpose: "any" },
      { src: icon512, sizes: "512x512", type: "image/png", purpose: "maskable" }
    );
  }

  return {
    name,
    short_name: name.length > 12 ? "Mekawy ERP" : name,
    description: "نظام إدارة المصنع — شؤون العاملين والحضور والانصراف",
    start_url: "/",
    display: "standalone",
    orientation: "portrait-primary",
    background_color: "#ffffff",
    theme_color: "#dc2626",
    lang: "ar",
    dir: "rtl",
    icons,
  };
}
