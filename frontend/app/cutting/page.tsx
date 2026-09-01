"use client";

// The lay list (SRS 7.1). Every bit of state — search text, filters, sort,
// page — lives in the URL, which is also exactly the query the API takes. That
// is what makes a link reproduce someone else's screen (7.1.2).

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Bookmark,
  Camera,
  ChevronDown,
  FileSpreadsheet,
  FileText,
  Filter,
  Loader2,
  Plus,
  Search,
  SlidersHorizontal,
  X,
} from "lucide-react";
import Shell from "@/components/Shell";
import { api, downloadFile, errorText } from "@/lib/api";
import { fmt } from "@/lib/cutting";
import {
  FILTER_GROUPS,
  NON_FILTER_PARAMS,
  STATUS_LABEL,
  STATUS_STYLE,
  chipLabel,
} from "@/lib/cuttingFilters";

type LayRow = {
  id: number;
  start_date: string;
  end_date: string;
  is_multi_day: boolean;
  code: string;
  garment_model_code: string;
  garment_model_name: string;
  category: string;
  bank_name: string;
  team_leader_name: string;
  lay_length_m: string;
  pieces_per_ply: number;
  sizes_summary: string[];
  total_plies: number;
  theoretical_pieces: number;
  actual_pieces: number | null;
  expected_metrage: string;
  real_metrage: string | null;
  deviation_pct: string | null;
  has_shortage: boolean;
  has_length_mismatch: boolean;
  has_sheet_image: boolean;
  status: string;
  status_label: string;
};

type Summary = {
  lays: number;
  theoretical_pieces: number;
  actual_pieces: number;
  avg_real_metrage: string | null;
  with_shortage: number;
  awaiting_count: number;
};

type SavedFilter = { id: number; name: string; query: string; params: string };

const PAGE_SIZE = 50;

function shortDate(iso: string) {
  const [, m, d] = iso.split("-");
  return `${Number(d)}/${Number(m)}`;
}

function dateCell(row: LayRow) {
  return row.is_multi_day
    ? `${shortDate(row.start_date)} → ${shortDate(row.end_date)}`
    : shortDate(row.start_date);
}

export default function Page() {
  return (
    <Shell>
      <Suspense fallback={<div className="p-6 text-slate-500">جارٍ التحميل…</div>}>
        <LayList />
      </Suspense>
    </Shell>
  );
}

function LayList() {
  const router = useRouter();
  const params = useSearchParams();

  const [rows, setRows] = useState<LayRow[]>([]);
  const [count, setCount] = useState(0);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [drawer, setDrawer] = useState(false);
  const [saved, setSaved] = useState<SavedFilter[]>([]);
  // Saved searches need a table that a deployment may not have migrated yet.
  // If the endpoint is not there, hide the feature rather than offering a
  // button that errors.
  const [savedAvailable, setSavedAvailable] = useState(false);
  const [parsedChips, setParsedChips] = useState<{ label: string; value: string }[]>([]);

  // The search box is the one control that is not read straight from the URL:
  // it types faster than a route change should follow.
  const [q, setQ] = useState(params.get("q") ?? "");
  // What this box itself last pushed into the URL. Without it, the sync below
  // fires on our own debounced write and reverts anything typed in between —
  // type "MEGAN" fast enough and you get "MEGA" back.
  const [pushed, setPushed] = useState(params.get("q") ?? "");

  const queryString = params.toString();

  const setParams = useCallback(
    (patch: Record<string, string | null>, resetPage = true) => {
      const next = new URLSearchParams(params.toString());
      for (const [k, v] of Object.entries(patch)) {
        if (v === null || v === "") next.delete(k);
        else next.set(k, v);
      }
      if (resetPage) next.delete("page");
      router.replace(`/cutting${next.toString() ? `?${next}` : ""}`, { scroll: false });
    },
    [params, router]
  );

  // 300ms debounce, per SRS 7.1.1.
  useEffect(() => {
    const current = params.get("q") ?? "";
    if (q === current) return;
    const t = setTimeout(() => {
      setPushed(q);
      setParams({ q: q || null });
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  // Adopt the URL only when it changed from somewhere else — a saved search,
  // "clear all", the back button — never in reply to our own write.
  useEffect(() => {
    const fromUrl = params.get("q") ?? "";
    if (fromUrl !== pushed) {
      setQ(fromUrl);
      setPushed(fromUrl);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryString]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    // The search endpoint understands the shorthand tokens; the plain list does
    // not, so route through it whenever there is anything in the box.
    const hasQ = (params.get("q") ?? "").trim().length > 0;
    const path = hasQ ? "/api/cutting/lays/search/" : "/api/cutting/lays/";
    Promise.all([
      api(`${path}?${queryString}`),
      api(`/api/cutting/lays/summary/?${queryString}`),
    ])
      .then(([list, sum]) => {
        if (cancelled) return;
        setRows(list.results);
        setCount(list.count);
        setParsedChips(
          (list.parsed?.filters ?? []).map((f: any) => ({
            label: f.label,
            value: f.value,
          }))
        );
        setSummary(sum);
      })
      .catch((e) => !cancelled && setError(errorText(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [queryString]);

  useEffect(() => {
    api("/api/cutting/saved-filters/")
      .then((d) => {
        setSaved(d.results ?? d);
        setSavedAvailable(true);
      })
      .catch(() => setSavedAvailable(false));
  }, []);

  const activeFilters = useMemo(
    () =>
      Array.from(params.entries()).filter(
        ([k, v]) => !NON_FILTER_PARAMS.has(k) && v !== ""
      ),
    [queryString]
  );

  const ordering = params.get("ordering") ?? "-start_date";
  const page = Number(params.get("page") ?? 1);
  const pages = Math.max(1, Math.ceil(count / PAGE_SIZE));

  const sortBy = (field: string) =>
    setParams({ ordering: ordering === field ? `-${field}` : field });

  const clearAll = () => {
    const next = new URLSearchParams();
    const keep = params.get("q");
    if (keep) next.set("q", keep);
    router.replace(`/cutting${next.toString() ? `?${next}` : ""}`, { scroll: false });
  };

  const saveCurrent = async () => {
    const name = prompt("اسم البحث؟");
    if (!name) return;
    try {
      await api("/api/cutting/saved-filters/", {
        method: "POST",
        body: JSON.stringify({ name, query: q, params: queryString }),
      });
      const d = await api("/api/cutting/saved-filters/");
      setSaved(d.results ?? d);
    } catch (e) {
      setError(errorText(e));
    }
  };

  return (
    <div className="font-tajawal mx-auto max-w-7xl p-3">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h1 className="text-lg font-bold">الفرشات</h1>
        <div className="flex items-center gap-2">
          {/* Exports carry whatever filters are applied (SRS 7.1). */}
          <button
            data-testid="export-xlsx"
            className="btn-secondary"
            onClick={() =>
              downloadFile(
                `/api/cutting/lays/export/?${queryString}${queryString ? "&" : ""}export=xlsx`,
                "cutting-lays.xlsx"
              ).catch((e) => setError(errorText(e)))
            }
          >
            <FileSpreadsheet className="h-4 w-4" />
            <span className="hidden sm:inline">إكسيل</span>
          </button>
          <button
            data-testid="export-pdf"
            className="btn-secondary"
            onClick={() =>
              downloadFile(
                `/api/cutting/lays/export/?${queryString}${queryString ? "&" : ""}export=pdf`,
                "cutting-lays.pdf"
              ).catch((e) => setError(errorText(e)))
            }
          >
            <FileText className="h-4 w-4" />
            <span className="hidden sm:inline">PDF</span>
          </button>
          <Link href="/cutting/new" className="btn-primary">
            <Plus className="h-4 w-4" />
            <span className="hidden sm:inline">فرشة جديدة</span>
          </Link>
        </div>
      </div>

      {/* ---- summary cards ---- */}
      <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        <Card label="فرشات الفترة" value={summary ? String(summary.lays) : "—"} />
        <Card
          label="إجمالي القطع"
          value={summary ? String(summary.actual_pieces || summary.theoretical_pieces) : "—"}
          hint={summary?.actual_pieces ? "فعلية" : "نظرية"}
        />
        <Card
          label="متوسط الميتراج"
          value={summary?.avg_real_metrage ? fmt(Number(summary.avg_real_metrage), 3) : "—"}
        />
        <Card
          label="فيها عجز"
          value={summary ? String(summary.with_shortage) : "—"}
          tone={summary && summary.with_shortage > 0 ? "rose" : "slate"}
        />
        <Card
          label="مستنية ترقيم"
          value={summary ? String(summary.awaiting_count) : "—"}
          tone={summary && summary.awaiting_count > 0 ? "amber" : "slate"}
        />
      </div>

      {/* ---- search + filters ---- */}
      <div className="card mb-3 space-y-3">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              className="!pr-9"
              placeholder="ابحث… أو اكتب ميتراج>1.2 · عجز:نعم · مقاس:32"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <button
            className="btn-secondary shrink-0"
            onClick={() => setDrawer(true)}
            aria-label="فلاتر"
          >
            <SlidersHorizontal className="h-4 w-4" />
            <span className="hidden sm:inline">فلاتر</span>
            {activeFilters.length > 0 && (
              <span className="rounded-full bg-red-600 px-1.5 text-xs text-white">
                {activeFilters.length}
              </span>
            )}
          </button>
        </div>

        {saved.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {saved.map((s) => (
              <button
                key={s.id}
                onClick={() => router.replace(`/cutting?${s.params}`, { scroll: false })}
                className="flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600 hover:bg-red-50 hover:text-red-700"
              >
                <Bookmark className="h-3 w-3" />
                {s.name}
              </button>
            ))}
          </div>
        )}

        {(activeFilters.length > 0 || parsedChips.length > 0) && (
          <div className="flex flex-wrap items-center gap-1.5">
            {parsedChips.map((c, i) => (
              <span
                key={`p${i}`}
                className="rounded-full bg-sky-50 px-2.5 py-1 text-xs font-medium text-sky-700"
                title="من نص البحث"
              >
                {c.label} {c.value}
              </span>
            ))}
            {activeFilters.map(([k, v]) => (
              <span
                key={k}
                className="flex items-center gap-1 rounded-full bg-red-50 px-2.5 py-1 text-xs font-medium text-red-700"
              >
                {chipLabel(k, v)}
                <button onClick={() => setParams({ [k]: null })} aria-label="إلغاء">
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
            {activeFilters.length > 0 && (
              <button
                onClick={clearAll}
                className="text-xs font-semibold text-slate-500 underline hover:text-red-700"
              >
                مسح الكل
              </button>
            )}
            {savedAvailable && (
              <button
                onClick={saveCurrent}
                className="mr-auto flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-red-700"
              >
                <Bookmark className="h-3 w-3" />
                احفظ البحث
              </button>
            )}
          </div>
        )}
      </div>

      {error && <p className="card mb-3 text-rose-700">{error}</p>}

      {/* ---- results ---- */}
      {loading ? (
        <div className="card flex items-center justify-center gap-2 py-10 text-slate-500">
          <Loader2 className="h-5 w-5 animate-spin" />
          جارٍ التحميل…
        </div>
      ) : rows.length === 0 ? (
        <div className="card py-10 text-center text-slate-500">مفيش فرشات بالفلاتر دي</div>
      ) : (
        <>
          {/* phones: a three-line card per lay (SRS 7.1) */}
          <div className="space-y-2 lg:hidden">
            {rows.map((r) => (
              <Link key={r.id} href={`/cutting/${r.id}`} className="card block space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-bold">
                    <bdi>{r.code}</bdi>{" "}
                    <span className="font-normal text-slate-500">
                      <bdi>{r.garment_model_name}</bdi>
                      {r.category && ` · ${r.category}`}
                    </span>
                  </span>
                  <span className="shrink-0 text-xs text-slate-400" dir="ltr">
                    {dateCell(r)}
                  </span>
                </div>
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <SizeChips sizes={r.sizes_summary} />
                  <span dir="ltr">{fmt(Number(r.lay_length_m))} م</span>
                  {r.has_sheet_image && <Camera className="h-3.5 w-3.5 text-slate-400" />}
                </div>
                <div className="flex items-center justify-between gap-2 text-sm">
                  <span className="text-slate-600" dir="ltr">
                    {fmt(Number(r.expected_metrage), 3)} →{" "}
                    {r.real_metrage ? fmt(Number(r.real_metrage), 3) : "…"}
                  </span>
                  <Deviation value={r.deviation_pct} shortage={r.has_shortage} />
                  <StatusPill status={r.status} label={r.status_label} />
                </div>
              </Link>
            ))}
          </div>

          {/* desktop: the full column set */}
          <div className="hidden overflow-x-auto lg:block">
            <table className="data">
              <thead>
                <tr>
                  <Th field="code" {...{ ordering, sortBy }}>كود القصة</Th>
                  <Th field="start_date" {...{ ordering, sortBy }}>التاريخ</Th>
                  <th>الموديل</th>
                  <th>المقاسات</th>
                  <Th field="lay_length_m" {...{ ordering, sortBy }}>الطول</Th>
                  <th>ق/راق</th>
                  <Th field="theoretical_pieces" {...{ ordering, sortBy }}>إجمالي القطع</Th>
                  <Th field="expected_metrage" {...{ ordering, sortBy }}>المتوقع</Th>
                  <Th field="real_metrage" {...{ ordering, sortBy }}>الحقيقي</Th>
                  <Th field="deviation_pct" {...{ ordering, sortBy }}>الانحراف</Th>
                  <th>رئيس الفريق · البنك</th>
                  <Th field="status" {...{ ordering, sortBy }}>الحالة</Th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr
                    key={r.id}
                    className="cursor-pointer"
                    onClick={() => router.push(`/cutting/${r.id}`)}
                  >
                    <td dir="ltr" className="whitespace-nowrap text-right font-semibold">
                      <bdi>{r.code}</bdi>
                    </td>
                    <td dir="ltr" className="whitespace-nowrap text-right">{dateCell(r)}</td>
                    <td>
                      <div className="font-semibold"><bdi>{r.garment_model_name}</bdi></div>
                      <div className="text-xs text-slate-500">{r.category}</div>
                    </td>
                    <td><SizeChips sizes={r.sizes_summary} /></td>
                    <td dir="ltr" className="text-right">{fmt(Number(r.lay_length_m))}</td>
                    <td dir="ltr" className="text-right">{r.pieces_per_ply}</td>
                    <td dir="ltr" className="text-right">
                      {r.theoretical_pieces}
                      {r.actual_pieces != null && (
                        <span className="mr-1 font-semibold text-emerald-700">
                          / {r.actual_pieces}
                        </span>
                      )}
                    </td>
                    <td dir="ltr" className="text-right">{fmt(Number(r.expected_metrage), 3)}</td>
                    <td dir="ltr" className="text-right">
                      {r.real_metrage ? (
                        fmt(Number(r.real_metrage), 3)
                      ) : (
                        <span className="text-xs text-slate-400">بانتظار الترقيم</span>
                      )}
                    </td>
                    <td><Deviation value={r.deviation_pct} shortage={r.has_shortage} /></td>
                    <td className="text-xs">
                      {r.team_leader_name}
                      <div className="text-slate-400">{r.bank_name}</div>
                    </td>
                    <td><StatusPill status={r.status} label={r.status_label} /></td>
                    <td>{r.has_sheet_image && <Camera className="h-4 w-4 text-slate-400" />}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {pages > 1 && (
            <div className="mt-3 flex items-center justify-center gap-2">
              <button
                className="btn-secondary"
                disabled={page <= 1}
                onClick={() => setParams({ page: String(page - 1) }, false)}
              >
                السابق
              </button>
              <span className="text-sm text-slate-500" dir="ltr">
                {page} / {pages}
              </span>
              <button
                className="btn-secondary"
                disabled={page >= pages}
                onClick={() => setParams({ page: String(page + 1) }, false)}
              >
                التالي
              </button>
            </div>
          )}
        </>
      )}

      {drawer && (
        <FilterDrawer
          params={params}
          onClose={() => setDrawer(false)}
          onChange={setParams}
          onClear={clearAll}
        />
      )}
    </div>
  );
}

// --- pieces ---------------------------------------------------------------

function Card({
  label,
  value,
  hint,
  tone = "slate",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "slate" | "rose" | "amber";
}) {
  const colour = {
    slate: "text-slate-800",
    rose: "text-rose-600",
    amber: "text-amber-600",
  }[tone];
  return (
    <div className="rounded-xl bg-white p-3 shadow-sm ring-1 ring-slate-100">
      <div className="text-[11px] text-slate-400">{label}</div>
      <div dir="ltr" className={`text-right text-xl font-bold ${colour}`}>
        {value}
      </div>
      {hint && <div className="text-[10px] text-slate-400">{hint}</div>}
    </div>
  );
}

function SizeChips({ sizes }: { sizes: string[] }) {
  const shown = sizes.slice(0, 4);
  const rest = sizes.length - shown.length;
  return (
    <span dir="ltr" className="inline-flex items-center gap-1 text-xs">
      <span className="text-slate-600">{shown.join("·")}</span>
      {rest > 0 && <span className="text-slate-400">+{rest}</span>}
    </span>
  );
}

function Deviation({ value, shortage }: { value: string | null; shortage: boolean }) {
  if (value == null) return <span className="text-xs text-slate-300">—</span>;
  const n = Number(value);
  // Green inside the tolerance, red outside it (SRS 7.1).
  const bad = shortage || Math.abs(n) > 2;
  return (
    <span
      dir="ltr"
      className={`rounded px-1.5 py-0.5 text-xs font-bold ${
        bad ? "bg-rose-50 text-rose-700" : "bg-emerald-50 text-emerald-700"
      }`}
    >
      {n > 0 ? "+" : ""}
      {fmt(n)}%
    </span>
  );
}

function StatusPill({ status, label }: { status: string; label: string }) {
  return (
    <span
      className={`whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold ${
        STATUS_STYLE[status] ?? "bg-slate-100 text-slate-600"
      }`}
    >
      {label || STATUS_LABEL[status] || status}
    </span>
  );
}

function Th({
  field,
  ordering,
  sortBy,
  children,
}: {
  field: string;
  ordering: string;
  sortBy: (f: string) => void;
  children: React.ReactNode;
}) {
  const active = ordering === field || ordering === `-${field}`;
  return (
    <th className="cursor-pointer select-none" onClick={() => sortBy(field)}>
      <span className="inline-flex items-center gap-1">
        {children}
        {active && (
          <ChevronDown
            className={`h-3 w-3 ${ordering.startsWith("-") ? "" : "rotate-180"}`}
          />
        )}
      </span>
    </th>
  );
}

function FilterDrawer({
  params,
  onClose,
  onChange,
  onClear,
}: {
  params: URLSearchParams;
  onClose: () => void;
  onChange: (patch: Record<string, string | null>) => void;
  onClear: () => void;
}) {
  const [open, setOpen] = useState<string | null>("time");
  return (
    <div className="fixed inset-0 z-40 flex">
      <div className="flex-1 bg-black/40" onClick={onClose} />
      <aside
        data-testid="filter-drawer"
        className="flex w-full max-w-sm flex-col bg-white shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-slate-200 p-4">
          <span className="flex items-center gap-2 font-bold">
            <Filter className="h-4 w-4 text-red-600" />
            الفلاتر المتقدمة
          </span>
          <button onClick={onClose} aria-label="إغلاق">
            <X className="h-5 w-5 text-slate-400" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-3">
          {FILTER_GROUPS.map((group) => {
            const used = group.filters.filter((f) => params.get(f.param)).length;
            const isOpen = open === group.key;
            return (
              <div key={group.key} className="border-b border-slate-100 py-2">
                <button
                  className="flex w-full items-center gap-2 py-1 text-sm font-semibold"
                  onClick={() => setOpen(isOpen ? null : group.key)}
                >
                  <span className="flex-1 text-right">{group.label}</span>
                  {used > 0 && (
                    <span className="rounded-full bg-red-600 px-1.5 text-xs text-white">
                      {used}
                    </span>
                  )}
                  <ChevronDown
                    className={`h-4 w-4 text-slate-400 transition-transform ${
                      isOpen ? "rotate-180" : ""
                    }`}
                  />
                </button>
                {isOpen && (
                  <div className="grid grid-cols-2 gap-2 pt-2">
                    {group.filters.map((f) => (
                      <div key={f.param} className={f.kind === "select" ? "col-span-2" : ""}>
                        <label className="!text-xs">{f.label}</label>
                        {f.kind === "select" ? (
                          <select
                            value={params.get(f.param) ?? ""}
                            onChange={(e) => onChange({ [f.param]: e.target.value || null })}
                          >
                            <option value="">الكل</option>
                            {f.options!.map((o) => (
                              <option key={o.value} value={o.value}>
                                {o.label}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <input
                            type={f.kind === "date" ? "date" : "text"}
                            inputMode={f.kind === "number" ? "decimal" : undefined}
                            dir={f.kind === "text" ? undefined : "ltr"}
                            placeholder={f.placeholder}
                            defaultValue={params.get(f.param) ?? ""}
                            onBlur={(e) => onChange({ [f.param]: e.target.value || null })}
                            onKeyDown={(e) => {
                              if (e.key === "Enter")
                                onChange({ [f.param]: (e.target as HTMLInputElement).value || null });
                            }}
                          />
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <div className="flex gap-2 border-t border-slate-200 p-3">
          <button className="btn-secondary flex-1" onClick={onClear}>
            مسح الكل
          </button>
          <button className="btn-primary flex-1" onClick={onClose}>
            عرض النتائج
          </button>
        </div>
      </aside>
    </div>
  );
}
