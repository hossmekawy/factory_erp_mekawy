"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { FileDown, FileText } from "lucide-react";
import Shell from "@/components/Shell";
import { api, downloadFile, errorText } from "@/lib/api";

type Row = {
  id: number;
  code: string;
  model_name: string;
  color: string;
  production_order_no: string;
  cutting_date: string;
  employee: string;
  rolls_count: number;
  total_meters: number | null;
  total_lays: number;
  total_pieces: number;
  sizes: string | null;
  expected_metraj: number | null;
  real_metraj: number | null;
  total_remnants: number | null;
  shortage: number | null;
  waste_pct: number | null;
};

type Report = {
  rows: Row[];
  totals: Record<string, number | null>;
  count: number;
};

const EMPTY_FILTERS = {
  code: "",
  model_name: "",
  color: "",
  production_order_no: "",
  roll_number: "",
  lot_number: "",
  date_from: "",
  date_to: "",
};

const fmt = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : String(v);

export default function CuttingReportsPage() {
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [report, setReport] = useState<Report | null>(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const qs = () => {
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries(filters)) if (v) p.set(k, v);
    return p.toString();
  };

  useEffect(() => {
    const t = setTimeout(() => {
      api(`/api/cutting/reports/?${qs()}`)
        .then(setReport)
        .catch(() => {});
    }, 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters]);

  async function download(kind: "xlsx" | "a4" | "a5") {
    setBusy(true);
    setMsg("");
    try {
      if (kind === "xlsx") {
        await downloadFile(`/api/cutting/reports/export/?${qs()}`, "cutting-report.xlsx");
      } else {
        await downloadFile(
          `/api/cutting/reports/pdf/?size=${kind}&${qs()}`,
          `cutting-report-${kind}.pdf`
        );
      }
    } catch (err) {
      setMsg(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  const F = (k: keyof typeof EMPTY_FILTERS, label: string, type = "text") => (
    <div>
      <label>{label}</label>
      <input
        type={type}
        value={filters[k]}
        onChange={(e) => setFilters({ ...filters, [k]: e.target.value })}
      />
    </div>
  );

  return (
    <Shell>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">تقارير مرحلة القص</h1>
        <div className="flex flex-wrap gap-2">
          <button className="btn-secondary" disabled={busy} onClick={() => download("xlsx")}>
            <FileDown className="h-4 w-4" /> Excel
          </button>
          <button className="btn-secondary" disabled={busy} onClick={() => download("a4")}>
            <FileText className="h-4 w-4" /> PDF A4
          </button>
          <button className="btn-secondary" disabled={busy} onClick={() => download("a5")}>
            <FileText className="h-4 w-4" /> PDF A5
          </button>
        </div>
      </div>

      {msg && <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800">{msg}</div>}

      <div className="card mb-4">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {F("code", "الكود")}
          {F("model_name", "الموديل")}
          {F("color", "اللون")}
          {F("production_order_no", "رقم أمر الإنتاج")}
          {F("roll_number", "رقم التوب")}
          {F("lot_number", "رقم اللوط")}
          {F("date_from", "من تاريخ", "date")}
          {F("date_to", "إلى تاريخ", "date")}
        </div>
      </div>

      {/* Mobile: cards, one per cutting — no horizontal scrolling */}
      <div className="space-y-3 md:hidden">
        {!report ? (
          <div className="card py-8 text-center text-slate-400">جارٍ التحميل…</div>
        ) : report.rows.length === 0 ? (
          <div className="card py-8 text-center text-slate-400">لا توجد نتائج</div>
        ) : (
          report.rows.map((r) => (
            <Link key={r.id} href={`/cutting/${r.id}`} className="card block">
              <div className="mb-1 flex items-center justify-between">
                <span className="font-bold text-red-700">{r.code}</span>
                <span className="text-xs text-slate-500" dir="ltr">{r.cutting_date}</span>
              </div>
              <div className="mb-1 text-sm text-slate-700">
                {r.model_name}
                {r.color && <span className="text-slate-400"> — {r.color}</span>}
                <span className="mr-2 text-xs text-slate-400">({r.employee})</span>
              </div>
              {r.sizes && (
                <div className="mb-3 text-xs font-medium text-red-700" dir="ltr">
                  {r.sizes}
                </div>
              )}
              <div className="grid grid-cols-3 gap-2 text-center">
                {[
                  ["الأمتار", fmt(r.total_meters)],
                  ["القطع", String(r.total_pieces)],
                  ["الأتواب", String(r.rolls_count)],
                  ["ميتراج حقيقي", fmt(r.real_metraj)],
                  ["البواقي", fmt(r.total_remnants)],
                  ["هالك %", fmt(r.waste_pct)],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-lg bg-red-50 px-1 py-1.5">
                    <div className="text-[10px] text-slate-500">{label}</div>
                    <div className="text-sm font-bold text-red-700">{value}</div>
                  </div>
                ))}
              </div>
              {r.shortage != null && (
                <div className="mt-2 text-xs font-bold text-red-600">⚠️ عجز: {fmt(r.shortage)} م</div>
              )}
            </Link>
          ))
        )}
      </div>

      {/* Desktop: full table */}
      <div className="card hidden overflow-x-auto p-0 md:block">
        <table className="data min-w-[1000px]">
          <thead>
            <tr>
              <th>الكود</th>
              <th>الموديل</th>
              <th>اللون</th>
              <th>التاريخ</th>
              <th>موظف القص</th>
              <th>الأتواب</th>
              <th>الأمتار</th>
              <th>الراقات</th>
              <th>القطع</th>
              <th>المقاسات</th>
              <th>ميتراج متوقع</th>
              <th>ميتراج حقيقي</th>
              <th>البواقي</th>
              <th>العجز</th>
              <th>هالك %</th>
            </tr>
          </thead>
          <tbody>
            {!report ? (
              <tr><td colSpan={15} className="py-8 text-center text-slate-400">جارٍ التحميل…</td></tr>
            ) : report.rows.length === 0 ? (
              <tr><td colSpan={15} className="py-8 text-center text-slate-400">لا توجد نتائج</td></tr>
            ) : (
              report.rows.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link href={`/cutting/${r.id}`} className="font-bold text-red-700 hover:underline">
                      {r.code}
                    </Link>
                  </td>
                  <td>{r.model_name}</td>
                  <td>{r.color || "—"}</td>
                  <td dir="ltr">{r.cutting_date}</td>
                  <td>{r.employee}</td>
                  <td>{r.rolls_count}</td>
                  <td>{fmt(r.total_meters)}</td>
                  <td>{r.total_lays}</td>
                  <td>{r.total_pieces}</td>
                  <td dir="ltr" className="text-xs">{r.sizes ?? "—"}</td>
                  <td>{fmt(r.expected_metraj)}</td>
                  <td>{fmt(r.real_metraj)}</td>
                  <td>{fmt(r.total_remnants)}</td>
                  <td>{fmt(r.shortage)}</td>
                  <td>{fmt(r.waste_pct)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {report && report.rows.length > 0 && (
        <div className="card mt-4 flex flex-wrap justify-center gap-x-8 gap-y-2 text-sm font-bold">
          <span>القصات: {report.count}</span>
          <span>الأتواب: {fmt(report.totals.rolls)}</span>
          <span>الأمتار: {fmt(report.totals.meters)}</span>
          <span>القطع: {fmt(report.totals.pieces)}</span>
          <span>البواقي: {fmt(report.totals.remnants)}</span>
          <span>العجز: {fmt(report.totals.shortage)}</span>
        </div>
      )}
    </Shell>
  );
}
