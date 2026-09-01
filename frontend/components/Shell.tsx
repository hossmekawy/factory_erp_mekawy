"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  BarChart3,
  Bell,
  ChevronDown,
  ClipboardList,
  Clock,
  Factory,
  Fingerprint,
  Home,
  HardHat,
  Layers,
  LogOut,
  Menu,
  Ruler,
  Settings as SettingsIcon,
  Scissors,
  ShieldCheck,
  Shirt,
  SquarePen,
  Users,
  UsersRound,
  X,
} from "lucide-react";
import { api, clearTokens, getAccess } from "@/lib/api";
import { ROLE_HOME, ROLE_LABEL, allowedForRole } from "@/lib/roles";

type NavItem = {
  href: string;
  label: string;
  Icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  roles: string[];
};

type NavGroup = {
  key: string;
  label: string;
  Icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  items: NavItem[];
};

// `roles` = non-admin roles that can see the item; admin sees everything.

const NAV_TOP: NavItem[] = [
  { href: "/", label: "لوحة التحكم", Icon: Home, roles: [] },
];

// Every role that may open a cutting screen. Writing is gated on the backend
// (cutting/permissions.py); this only decides what appears in the menu.
const CUTTING_ROLES = ["production_manager", "cutting_supervisor", "cutting"];

const NAV_GROUPS: NavGroup[] = [
  {
    key: "production",
    label: "الإنتاج",
    Icon: Factory,
    items: [
      { href: "/cutting", label: "الفرشات", Icon: Layers, roles: CUTTING_ROLES },
      {
        href: "/cutting/new",
        label: "فرشة جديدة",
        Icon: Scissors,
        roles: CUTTING_ROLES,
      },
      { href: "/cutting/count", label: "الترقيم", Icon: ClipboardList, roles: CUTTING_ROLES },
      { href: "/cutting/models", label: "الموديلات", Icon: Shirt, roles: CUTTING_ROLES },
      { href: "/cutting/fits", label: "القَصّات", Icon: Ruler, roles: CUTTING_ROLES },
      { href: "/cutting/reports", label: "تقارير القص", Icon: BarChart3, roles: CUTTING_ROLES },
    ],
  },
  {
    key: "hr",
    label: "شؤون العاملين",
    Icon: UsersRound,
    items: [
      { href: "/employees", label: "الموظفون", Icon: HardHat, roles: ["hr"] },
      { href: "/attendance", label: "سجل الحضور", Icon: Clock, roles: ["hr"] },
      { href: "/attendance/manual", label: "تسجيل حضور يدوي", Icon: SquarePen, roles: ["hr"] },
      { href: "/reports/weekly", label: "التقرير الأسبوعي", Icon: BarChart3, roles: ["hr"] },
    ],
  },
  {
    key: "system",
    label: "إدارة النظام",
    Icon: ShieldCheck,
    items: [
      { href: "/devices", label: "أجهزة البصمة", Icon: Fingerprint, roles: [] },
      { href: "/users", label: "مستخدمو النظام", Icon: Users, roles: [] },
      { href: "/settings", label: "الإعدادات", Icon: SettingsIcon, roles: [] },
    ],
  },
];

function NotificationBell({ unread }: { unread: number }) {
  return (
    <Link
      href="/cutting/notifications"
      data-testid="notification-bell"
      className="relative rounded-lg p-2 text-slate-500 hover:bg-red-50 hover:text-red-700"
      aria-label={unread ? `${unread} تنبيه غير مقروء` : "التنبيهات"}
    >
      <Bell className="h-5 w-5" />
      {unread > 0 && (
        <span
          data-testid="unread-badge"
          className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-bold text-white"
        >
          {unread > 99 ? "99+" : unread}
        </span>
      )}
    </Link>
  );
}

export default function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [role, setRole] = useState<string>("");
  const [username, setUsername] = useState<string>("");
  const [ready, setReady] = useState(false);
  const [open, setOpen] = useState(false); // mobile drawer
  // Manual open/close overrides per dropdown group; without an override a
  // group is open when it contains the current page (or it's the only group).
  const [groupOpen, setGroupOpen] = useState<Record<string, boolean>>({});
  // Unread cutting alerts (SRS 11.1). Polled rather than pushed: the events
  // are a handful a day, and a websocket for that would be infrastructure
  // nobody has to maintain today.
  const [unread, setUnread] = useState(0);
  const [companyName, setCompanyName] = useState("MR.Mekawy");
  const [logoUrl, setLogoUrl] = useState<string | null>(null);
  // A stored icon can be a truncated upload. The URL still returns 200 with
  // the right content-type, so nothing but the decode tells us it is broken —
  // fall back to the letter badge rather than leaving an empty white box.
  const [logoBroken, setLogoBroken] = useState(false);

  useEffect(() => {
    if (!getAccess()) {
      router.replace("/login");
      return;
    }
    api("/api/me/")
      .then((d) => {
        if (d.role !== "admin" && !allowedForRole(d.role, pathname)) {
          router.replace(ROLE_HOME[d.role] ?? "/login");
          return; // stay on the loading screen until the redirect lands
        }
        setRole(d.role);
        setUsername(d.username);
        setReady(true);
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router, pathname]);

  useEffect(() => {
    api("/api/settings/public/")
      .then((d) => {
        setCompanyName(d.company_name || "MR.Mekawy");
        setLogoUrl(d.icon_512_url || d.icon_192_url || null);
        setLogoBroken(false);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!ready) return;
    const poll = () =>
      api("/api/cutting/notifications/unread_count/")
        .then((d) => setUnread(d.unread))
        .catch(() => {}); // no access to the module, or not migrated yet
    poll();
    const id = setInterval(poll, 60000);
    return () => clearInterval(id);
  }, [ready, pathname]);

  // Close the drawer whenever the route changes.
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center text-slate-500">
        جارٍ التحميل…
      </div>
    );
  }

  const visible = (item: NavItem) => role === "admin" || item.roles.includes(role);
  const topItems = NAV_TOP.filter(visible);
  const groups = NAV_GROUPS.map((g) => ({ ...g, items: g.items.filter(visible) })).filter(
    (g) => g.items.length > 0
  );

  // The active item is the one whose href is the longest prefix of the current
  // path, so /attendance/manual highlights only itself, not /attendance too.
  const allItems = [...topItems, ...groups.flatMap((g) => g.items)];
  const activeHref = allItems
    .filter((i) => (i.href === "/" ? pathname === "/" : pathname.startsWith(i.href)))
    .sort((a, b) => b.href.length - a.href.length)[0]?.href;

  const initial = (username || "?").trim().charAt(0).toUpperCase();

  const logoBadge = (size: string) =>
    logoUrl && !logoBroken ? (
      <img
        src={logoUrl}
        alt={companyName}
        onError={() => {
          // Try the smaller icon once before giving up on images entirely.
          if (logoUrl.includes("icon_512")) setLogoUrl(logoUrl.replace("icon_512", "icon_192"));
          else setLogoBroken(true);
        }}
        className={`${size} shrink-0 rounded-xl bg-white object-contain p-1 shadow-sm`}
      />
    ) : (
      <div
        className={`flex ${size} shrink-0 items-center justify-center rounded-xl bg-white text-lg font-black text-red-700 shadow-sm`}
      >
        {companyName.trim().charAt(0).toUpperCase()}
      </div>
    );

  const renderLink = (item: NavItem, active: boolean, sub = false) => {
    const Icon = item.Icon;
    const badge = sub ? "h-7 w-7" : "h-9 w-9";
    const icon = sub ? "h-4 w-4" : "h-[18px] w-[18px]";
    return (
      <Link
        key={item.href}
        href={item.href}
        className={`flex items-center gap-3 rounded-lg border-r-[3px] px-3 py-2 text-sm font-medium transition ${
          active
            ? "border-red-600 bg-red-50 font-semibold text-red-700"
            : "border-transparent text-slate-600 hover:bg-slate-50 hover:text-red-700"
        }`}
      >
        <span
          className={`flex ${badge} shrink-0 items-center justify-center rounded-full ${
            active ? "bg-white shadow-sm" : "bg-slate-100"
          }`}
        >
          <Icon className={`${icon} text-red-600`} strokeWidth={2} />
        </span>
        {item.label}
      </Link>
    );
  };

  const sidebar = (
    <div className="flex h-full flex-col bg-white text-slate-700">
      <div className="flex items-center justify-between gap-3 bg-gradient-to-l from-red-700 to-red-600 px-4 py-5">
        <div className="flex items-center gap-3">
          {logoBadge("h-10 w-10")}
          <div>
            <div className="text-base font-bold leading-tight text-white">{companyName}</div>
            <div className="text-[11px] leading-tight text-red-100">نظام إدارة المصنع</div>
          </div>
        </div>
        <button
          className="text-red-100 hover:text-white lg:hidden"
          onClick={() => setOpen(false)}
          aria-label="إغلاق"
        >
          <X className="h-5 w-5" />
        </button>
      </div>
      <nav className="flex-1 space-y-1 overflow-y-auto p-3">
        {topItems.map((item) => renderLink(item, item.href === activeHref))}

        {groups.map((group) => {
          const containsActive = group.items.some((i) => i.href === activeHref);
          const isOpen = groupOpen[group.key] ?? (containsActive || groups.length === 1);
          const GIcon = group.Icon;
          return (
            <div key={group.key}>
              <button
                type="button"
                onClick={() => setGroupOpen((s) => ({ ...s, [group.key]: !isOpen }))}
                className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-semibold transition ${
                  containsActive && !isOpen
                    ? "bg-red-50 text-red-700"
                    : "text-slate-700 hover:bg-slate-50 hover:text-red-700"
                }`}
              >
                <span
                  className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${
                    containsActive ? "bg-red-600" : "bg-slate-100"
                  }`}
                >
                  <GIcon
                    className={`h-[18px] w-[18px] ${containsActive ? "text-white" : "text-red-600"}`}
                    strokeWidth={2}
                  />
                </span>
                <span className="flex-1 text-right">{group.label}</span>
                <ChevronDown
                  className={`h-4 w-4 text-slate-400 transition-transform ${isOpen ? "rotate-180" : ""}`}
                />
              </button>
              {isOpen && (
                <div className="mt-1 mr-5 space-y-1 border-r-2 border-slate-100 pr-3">
                  {group.items.map((item) => renderLink(item, item.href === activeHref, true))}
                </div>
              )}
            </div>
          );
        })}
      </nav>
      <div className="border-t border-slate-200 p-3 text-sm">
        <div className="mb-2 flex items-center gap-2 px-2">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-red-600 text-xs font-bold text-white">
            {initial}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate font-semibold text-slate-800">{username}</div>
            <div className="text-xs text-slate-400">{ROLE_LABEL[role] ?? role}</div>
          </div>
          <NotificationBell unread={unread} />
        </div>
        <button
          onClick={() => {
            clearTokens();
            router.replace("/login");
          }}
          className="flex w-full items-center justify-center gap-2 rounded-lg border border-red-200 px-3 py-2 font-medium text-red-700 hover:bg-red-50"
        >
          <LogOut className="h-4 w-4" />
          تسجيل الخروج
        </button>
      </div>
    </div>
  );

  return (
    <div className="flex min-h-screen">
      {/* Desktop sidebar */}
      <aside className="hidden w-60 shrink-0 border-l border-slate-200 lg:block">{sidebar}</aside>

      {/* Mobile drawer */}
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-black/50"
            onClick={() => setOpen(false)}
          />
          <aside className="absolute inset-y-0 right-0 w-64 max-w-[80%] shadow-xl">
            {sidebar}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile top bar */}
        <header className="sticky top-0 z-30 flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3 lg:hidden">
          <div className="flex items-center gap-2">
            {logoBadge("h-8 w-8")}
            <div className="font-bold text-slate-900">{companyName}</div>
          </div>
          <div className="flex items-center gap-1">
            <NotificationBell unread={unread} />
            <button
              onClick={() => setOpen(true)}
              className="rounded-lg p-2 text-red-700 hover:bg-red-50"
              aria-label="القائمة"
            >
              <Menu className="h-6 w-6" />
            </button>
          </div>
        </header>
        <main className="min-w-0 flex-1 p-4 sm:p-6">{children}</main>
      </div>
    </div>
  );
}
