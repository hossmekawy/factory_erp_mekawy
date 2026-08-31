import type { NextConfig } from "next";

const BACKEND = process.env.BACKEND_URL ?? "http://127.0.0.1:8010";

const nextConfig: NextConfig = {
  // Django's APPEND_SLASH wants /api/thing/ while Next's default is to redirect
  // the trailing slash away, so a standalone run bounced /api/... between the
  // two forever. Nginx bypasses Next for /api in production, which is why this
  // only ever showed up when running without it.
  skipTrailingSlashRedirect: true,

  // In production nginx routes /api, /media and /admin straight to Django;
  // these rewrites make `next dev`/`next start` work standalone too.
  async rewrites() {
    return [
      // `:path*` drops a trailing slash when it rebuilds the destination, and
      // Django's APPEND_SLASH then 301s a GET and hard-errors a POST ("can't
      // redirect to the slash URL while maintaining POST data"). Every DRF
      // route in this project ends in a slash, so put it back explicitly.
      { source: "/api/:path*", destination: `${BACKEND}/api/:path*/` },
      { source: "/media/:path*", destination: `${BACKEND}/media/:path*` },
    ];
  },
};

export default nextConfig;
