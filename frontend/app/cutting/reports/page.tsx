"use client";

// Cutting reports (SRS section 9). One screen for all of them: the backend
// returns the same {title, columns, rows} shape whichever report is asked
// for, so this renders any of them without knowing what they contain — and
// the Excel and PDF buttons hand the same dict to the same writers.
//
// Report 4 in the SRS, "حركة الأتواب", is not here: it needs a roll table and
// opening balances, which SRS 4.3 defers to the inventory phase.

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Download, FileSpreadsheet, FileText, Loader2 } from "lucide-react";
import Shell from "@/components/Shell";
import { api, downloadFile, errorText } from "@/lib/api";

type Column = [string, string];
type Report = {
  title: string;
  period: { start: string | null; end: string | null };
  columns: Column[];
  rows: Record<string, unknown>[];
  note?: string;
  total_shortage?: number;
  total_waste_m?: number;
  total_usable_m?: number;
  by_leader?: { team_leader: string; lays: number; shortage: number }[];
};

const REPORTS = [
  { key: "metrage", label: "الميتراج لكل موديل" },
  { key: "shortage", label: "العجز" },
  { key: "productivity", label: "إنتاجية رؤساء الفرق" },
  { key: "remnants", label: "البواقي والهالك" },
  { key: "banks", label: "تقرير البنوك اليومي" },
  { key: "quality", label: "جودة الإدخال" },
];

export default function Page() {
  return (
    <Shell>
      <Suspense fallback={<div className="p-6 text-slate-500">جارٍ التحميل…</div>}>
        <Reports />
      </Suspense>
    </Shell>
  );
}

function Reports() {
  const router = useRouter();
  const params = useSearchParams();
  const name = params.get("r") ?? "metrage";
  const from = params.get("date_from") ?? "";
  const to = params.get("date_to") ?? "";
  const includeBackfill = params.get("include_backfill") === "true";

  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const query = new URLSearchParams();
  if (from) query.set("date_from", from);
  if (to) query.set("date_to", to);
  if (includeBackfill) query.set("include_backfill", "true");
  const qs = query.toString();

  const setParams = useCallback(
    (patch: Record<string, string | null>) => {
      const next = new URLSearchParams(params.toString());
      for (const [k, v] of Object.entries(patch)) {
        if (v === null || v === "") next.delete(k);
        else next.set(k, v);
      }
      router.replace(`/cutting/reports?${next}`, { scroll: false });
    },
    [params, router]
  );

  useEffect(() => {
    setLoading(true);
    setError("");
    api(`/api/cutting/reports/${name}/?${qs}`)
      .then(setReport)
      .catch((e) => setError(errorText(e)))
      .finally(() => setLoading(false));
  }, [name, qs]);

  const download = (kind: "xlsx" | "pdf") =>
    downloadFile(
      `/api/cutting/reports/${name}/?${qs}${qs ? "&" : ""}export=${kind}`,
      `${name}.${kind}`
    ).catch((e) => setError(errorText(e)));

  return (
    <div className="font-tajawal mx-auto max-w-6xl p-3">
      <h1 className="mb-3 text-lg font-bold">التقارير</h1>

      <div className="card mb-3 space-y-3">
        <div className="flex flex-wrap gap-1.5">
          {REPORTS.map((r) => (
            <button
              key={r.key}
              data-testid={`report-${r.key}`}
              onClick={() => setParams({ r: r.key })}
              className={`rounded-full px-3 py-1.5 text-sm font-semibold transition ${
                name === r.key
                  ? "bg-red-600 text-white"
                  : "bg-slate-100 text-slate-600 hover:bg-red-50 hover:text-red-700"
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div>
            <label className="!text-xs">من تاريخ</label>
            <input
              data-testid="date-from"
              type="date"
              value={from}
              onChange={(e) => setParams({ date_from: e.target.value })}
            />
          </div>
          <div>
            <label className="!text-xs">إلى تاريخ</label>
            <input
              data-testid="date-to"
              type="date"
              value={to}
              onChange={(e) => setParams({ date_to: e.target.value })}
            />
          </div>
          <label className="col-span-2 flex items-end gap-2 pb-2 text-sm sm:col-span-2">
            <input
              data-testid="include-backfill"
              type="checkbox"
              className="!w-auto"
              checked={includeBackfill}
              onChange={(e) =>
                setParams({ include_backfill: e.target.checked ? "true" : null })
              }
            />
            <span className="font-normal text-slate-600">
              ضمّ الفرشات المرحّلة
              <span className="mr-1 text-xs text-slate-400">
                (مستبعدة افتراضيًا عشان متلخبطش التشغيلي)
              </span>
            </span>
          </label>
        </div>

        <div className="flex gap-2">
          <button data-testid="export-xlsx" className="btn-secondary"
                  onClick={() => download("xlsx")}>
            <FileSpreadsheet className="h-4 w-4" />
            إكسيل
          </button>
          <button data-testid="export-pdf" className="btn-secondary"
                  onClick={() => download("pdf")}>
            <FileText className="h-4 w-4" />
            PDF
          </button>
        </div>
      </div>

      {error && <p className="card mb-3 text-rose-700">{error}</p>}

      {loading ? (
        <div className="card flex items-center justify-center gap-2 py-10 text-slate-500">
          <Loader2 className="h-5 w-5 animate-spin" />
          جارٍ التحميل…
        </div>
      ) : !report ? null : report.rows.length === 0 ? (
        <div className="card py-10 text-center text-slate-500">
          مفيش بيانات في الفترة دي
        </div>
      ) : (
        <>
          <div className="card overflow-x-auto">
            <h2 className="mb-2 font-bold">{report.title}</h2>
            <table className="data" data-testid="report-table">
              <thead>
                <tr>
                  {report.columns.map(([key, label]) => (
                    <th key={key}>{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {report.rows.map((row, i) => (
                  <tr key={i}>
                    {report.columns.map(([key]) => (
                      <Cell key={key} value={row[key]} />
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            {report.note && (
              <p className="mt-2 text-xs text-slate-500">{report.note}</p>
            )}
          </div>

          {report.by_leader && report.by_leader.length > 0 && (
            <div className="card mt-3">
              <h2 className="mb-2 font-bold">العجز حسب رئيس الفريق</h2>
              <p className="mb-2 text-xs text-slate-500">
                اسم بيتكرر هنا معناه إن العجز مش صدفة — يستاهل نظرة على الفرد نفسه.
              </p>
              <table className="data">
                <thead>
                  <tr>
                    <th>رئيس الفريق</th>
                    <th>القصات</th>
                    <th>إجمالي العجز</th>
                  </tr>
                </thead>
                <tbody>
                  {report.by_leader.map((l) => (
                    <tr key={l.team_leader}>
                      <td>{l.team_leader}</td>
                      <td dir="ltr" className="text-right">{l.lays}</td>
                      <td dir="ltr" className="text-right font-semibold text-rose-700">
                        {l.shortage}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {(report.total_waste_m != null || report.total_shortage != null) && (
            <div className="card mt-3 flex flex-wrap gap-6">
              {report.total_shortage != null && (
                <Total label="إجمالي العجز" value={report.total_shortage} unit="م" rose />
              )}
              {report.total_waste_m != null && (
                <Total label="هالك" value={report.total_waste_m} unit="م" rose />
              )}
              {report.total_usable_m != null && (
                <Total label="صالح للاستخدام" value={report.total_usable_m} unit="م" />
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function Cell({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === "")
    return <td className="text-slate-300">—</td>;
  if (typeof value === "boolean")
    return (
      <td className={value ? "text-emerald-700" : "text-amber-700"}>
        {value ? "نعم" : "لا"}
      </td>
    );
  if (typeof value === "number")
    return (
      <td dir="ltr" className="text-right">
        {value}
      </td>
    );
  const text = String(value);
  const numeric = /^[\d.,\-+% →/]+$/.test(text);
  return (
    <td dir={numeric ? "ltr" : undefined} className={numeric ? "text-right" : undefined}>
      {text}
    </td>
  );
}

function Total({
  label,
  value,
  unit,
  rose,
}: {
  label: string;
  value: number;
  unit?: string;
  rose?: boolean;
}) {
  return (
    <div>
      <div className="text-[11px] text-slate-400">{label}</div>
      <div
        dir="ltr"
        className={`text-right text-xl font-bold ${rose ? "text-rose-600" : "text-slate-800"}`}
      >
        {value} {unit}
      </div>
    </div>
  );
}
