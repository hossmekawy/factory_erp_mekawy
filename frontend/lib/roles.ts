// Single source of truth for role → access mapping across the app.
// Roles mirror the Django groups: admin, hr, production_manager,
// cutting_supervisor, cutting.

export const ROLE_LABEL: Record<string, string> = {
  admin: "مدير",
  hr: "شؤون عاملين",
  production_manager: "مدير إنتاج",
  cutting_supervisor: "مشرف قص",
  cutting: "موظف قص",
};

// Where each role lands after login (and when bounced off a forbidden page).
export const ROLE_HOME: Record<string, string> = {
  admin: "/",
  hr: "/employees",
  production_manager: "/cutting",
  cutting_supervisor: "/cutting",
  cutting: "/cutting",
};

// Route prefixes each role may open. "all" = unrestricted (admin).
export const ROLE_PREFIXES: Record<string, string[] | "all"> = {
  admin: "all",
  hr: ["/employees", "/attendance", "/reports/weekly"],
  production_manager: ["/cutting"],
  cutting_supervisor: ["/cutting"],
  cutting: ["/cutting"],
};

export function allowedForRole(role: string, pathname: string): boolean {
  const prefixes = ROLE_PREFIXES[role];
  if (prefixes === "all") return true;
  if (!prefixes) return false;
  return prefixes.some((p) => pathname === p || pathname.startsWith(p + "/"));
}
