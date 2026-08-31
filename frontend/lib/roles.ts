// Single source of truth for role → access mapping across the app.
// Roles mirror the Django groups: admin, hr, production_manager,
// cutting_supervisor, cutting. The cutting roles are kept even though the old
// cutting module is gone — the replacement module needs the same three.

export const ROLE_LABEL: Record<string, string> = {
  admin: "مدير",
  hr: "شؤون عاملين",
  production_manager: "مدير إنتاج",
  cutting_supervisor: "مشرف قص",
  cutting: "موظف قص",
};

// Where each role lands after login (and when bounced off a forbidden page).
// The three cutting roles point at the dashboard for now: the old cutting
// module was removed and its replacement is not built yet. Sending them to a
// route that no longer exists would bounce them straight back into a login
// redirect loop. Repoint these at the new module once it ships.
export const ROLE_HOME: Record<string, string> = {
  admin: "/",
  hr: "/employees",
  production_manager: "/",
  cutting_supervisor: "/",
  cutting: "/",
};

// Route prefixes each role may open. "all" = unrestricted (admin).
// ["/"] matches the dashboard only — allowedForRole() compares the pathname
// exactly or against the prefix plus a slash, and "//" never matches.
export const ROLE_PREFIXES: Record<string, string[] | "all"> = {
  admin: "all",
  hr: ["/employees", "/attendance", "/reports/weekly"],
  production_manager: ["/"],
  cutting_supervisor: ["/"],
  cutting: ["/"],
};

export function allowedForRole(role: string, pathname: string): boolean {
  const prefixes = ROLE_PREFIXES[role];
  if (prefixes === "all") return true;
  if (!prefixes) return false;
  return prefixes.some((p) => pathname === p || pathname.startsWith(p + "/"));
}
