"use client";

// Lay detail (SRS 7.4), in the order the spec lays out: header, the six big
// numbers, sizes, roll lines, consumption, the documents, the activity log.
// Section 6 is the one people open when they doubt a number, so the notebook
// photo is large and opens full size.

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Camera,
  Check,
  ClipboardList,
  Loader2,
  Lock,
  Printer,
  X,
} from "lucide-react";
import Shell from "@/components/Shell";
import { ApiError, api, errorText } from "@/lib/api";
import { Issue, ROLL_END_LABEL, fmt, issuesOf } from "@/lib/cutting";
import { STATUS_LABEL, STATUS_STYLE } from "@/lib/cuttingFilters";

type Line = {
  id: number;
  line_no: number;
  roll_length_m: string;
  plies: number;
  remnant_m: string;
  remnant_disposition: string;
  remnant_disposition_label: string;
  shade_note: string;
  roll_end_action: keyof typeof ROLL_END_LABEL;
  roll_end_action_label: string;
  article: string;
  lot_no: string;
  roll_no: string;
  ticket_image: string | null;
  has_splice: boolean;
};

type Breakdown = {
  id: number;
  size: string;
  pieces_in_ply: number;
  theoretical_pieces: number;
  actual_pieces: number | null;
  is_manually_adjusted: boolean;
};

type Audit = {
  id: number;
  action: string;
  field: string;
  old_value: string;
  new_value: string;
  reason: string;
  user_name: string;
  at: string;
};

type Lay = {
  id: number;
  start_date: string;
  end_date: string;
  working_days: number;
  is_multi_day: boolean;
  status: string;
  status_label: string;
  entry_mode: string;
  is_backfill: boolean;
  notes: string;
  sheet_image: string | null;
  lay_length_m: string;
  lay_width_cm: string;
  pieces_per_ply: number;
  total_plies: number;
  theoretical_pieces: number;
  total_roll_length_m: string;
  total_remnant_m: string;
  consumed_m: string;
  fabric_shortage_m: string;
  expected_metrage: string;
  real_metrage: string | null;
  deviation_pct: string | null;
  has_shortage: boolean;
  has_length_mismatch: boolean;
  has_splice: boolean;
  bank_detail: { code: string; name: string };
  garment_model_detail: { code: string; name: string; fit: string };
  team_leader_detail: { full_name: string; employee_code: string };
  entered_by_name: string;
  lines: Line[];
  size_breakdown: Breakdown[];
  output: {
    actual_pieces: number;
    rejected_pieces: number;
    pieces_loss: number;
    recorded_by_name: string;
    recorded_at: string;
    notes: string;
  } | null;
  audit_entries: Audit[];
};

const ACTION_LABEL: Record<string, string> = {
  close: "قفل الفرشة",
  output: "تسجيل القطع",
  edit_after_close: "تعديل بعد القفل",
};

export default function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <Shell>
      <Detail id={id} />
    </Shell>
  );
}

function Detail({ id }: { id: string }) {
  const router = useRouter();
  const [lay, setLay] = useState<Lay | null>(null);
  const [productivity, setProductivity] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [issues, setIssues] = useState<Issue[]>([]);
  const [busy, setBusy] = useState(false);
  const [zoom, setZoom] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([
      api(`/api/cutting/lays/${id}/`),
      api(`/api/cutting/lays/${id}/calculations/`).catch(() => null),
    ])
      .then(([d, calc]) => {
        setLay(d);
        setProductivity(calc?.productivity ?? null);
      })
      .catch((e) => setError(errorText(e)))
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(load, [load]);

  const act = async (path: string, body: object = {}) => {
    setBusy(true);
    setError("");
    setIssues([]);
    try {
      await api(`/api/cutting/lays/${id}/${path}/`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      load();
    } catch (e) {
      const found = issuesOf((e as ApiError).data);
      setIssues(found);
      if (!found.length) setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  if (loading)
    return (
      <div className="flex items-center justify-center gap-2 p-10 text-slate-500">
        <Loader2 className="h-5 w-5 animate-spin" />
        جارٍ التحميل…
      </div>
    );
  if (!lay) return <p className="card m-3 text-rose-700">{error || "الفرشة مش موجودة"}</p>;

  const m = lay.garment_model_detail;

  return (
    <div className="font-tajawal mx-auto max-w-5xl p-3 print:max-w-none">
      <Link
        href="/cutting"
        className="mb-2 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-red-700 print:hidden"
      >
        <ArrowRight className="h-4 w-4" />
        كل الفرشات
      </Link>

      {/* ---- 1. header ---- */}
      <section className="card">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold">
              <bdi>{m.code}</bdi>{" "}
              <span className="font-normal text-slate-500">
                <bdi>{m.name}</bdi>
                {m.fit && ` · ${m.fit}`}
              </span>
            </h1>
            <p className="mt-1 text-sm text-slate-500" dir="ltr">
              {lay.is_multi_day
                ? `${lay.start_date} → ${lay.end_date} (${lay.working_days} أيام)`
                : lay.start_date}
            </p>
            <p className="mt-1 text-sm text-slate-600">
              {lay.bank_detail?.name} · {lay.team_leader_detail?.full_name}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full px-3 py-1 text-sm font-semibold ${
                STATUS_STYLE[lay.status] ?? "bg-slate-100"
              }`}
            >
              {lay.status_label || STATUS_LABEL[lay.status]}
            </span>
            {lay.entry_mode === "quick" && <Tag tone="amber">إدخال سريع</Tag>}
            {lay.is_backfill && <Tag tone="slate">مرحّلة</Tag>}
            {lay.has_splice && <Tag tone="slate">فيها وصل</Tag>}
            {lay.has_length_mismatch && <Tag tone="amber">فرق في الأطوال</Tag>}
            {lay.has_shortage && <Tag tone="rose">فيها عجز</Tag>}
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-2 print:hidden">
          {lay.status === "open" && (
            <button className="btn-primary" disabled={busy} onClick={() => act("close")}>
              <Lock className="h-4 w-4" />
              قفل الفرشة
            </button>
          )}
          {lay.status === "closed" && !lay.output && (
            // The counting screen is the next phase; until then this says so
            // rather than linking somewhere that does not exist.
            <span className="btn-secondary cursor-default opacity-70">
              <ClipboardList className="h-4 w-4" />
              مستنية ترقيم
            </span>
          )}
          {lay.status === "counted" && (
            <button className="btn-primary" disabled={busy} onClick={() => act("approve")}>
              <Check className="h-4 w-4" />
              اعتماد
            </button>
          )}
          <button className="btn-secondary" onClick={() => window.print()}>
            <Printer className="h-4 w-4" />
            طباعة
          </button>
        </div>

        {error && <p className="mt-3 font-semibold text-rose-700">{error}</p>}
        {issues.length > 0 && (
          <div className="mt-3 space-y-2">
            {issues.map((i, n) => (
              <div
                key={n}
                className={`rounded-lg px-3 py-2 text-sm ${
                  i.level === "error"
                    ? "bg-rose-50 text-rose-800"
                    : i.level === "warning"
                      ? "bg-amber-50 text-amber-800"
                      : "bg-slate-50 text-slate-600"
                }`}
              >
                <span className="ml-2 rounded bg-white/70 px-1.5 py-0.5 font-mono text-xs">
                  {i.code}
                </span>
                {i.message}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ---- 2. the six numbers ---- */}
      <section className="card mt-3 grid grid-cols-3 gap-3 sm:grid-cols-6">
        <Big label="طول الفرشة" value={fmt(Number(lay.lay_length_m))} unit="م" />
        <Big label="عرض الفرشة" value={fmt(Number(lay.lay_width_cm))} unit="سم" />
        <Big label="إجمالي الراق" value={String(lay.total_plies)} />
        <Big
          label="إجمالي القطع"
          value={String(lay.output?.actual_pieces ?? lay.theoretical_pieces)}
          unit={lay.output ? "فعلية" : "نظرية"}
        />
        <Big label="الميتراج المتوقع" value={fmt(Number(lay.expected_metrage), 3)} />
        <Big
          label="الميتراج الحقيقي"
          value={lay.real_metrage ? fmt(Number(lay.real_metrage), 3) : "—"}
          unit={
            lay.deviation_pct != null
              ? `${Number(lay.deviation_pct) > 0 ? "+" : ""}${fmt(Number(lay.deviation_pct))}%`
              : "بانتظار الترقيم"
          }
          tone={lay.deviation_pct != null && Math.abs(Number(lay.deviation_pct)) > 2 ? "rose" : "slate"}
        />
      </section>

      {/* ---- 3. sizes ---- */}
      <section className="card mt-3">
        <h2 className="mb-2 font-bold">المقاسات</h2>
        <div className="overflow-x-auto">
          <table className="data">
            <thead>
              <tr>
                <th>المقاس</th>
                <th>قطع في الراق</th>
                <th>إجمالي القطع</th>
                <th>القطع الفعلية</th>
              </tr>
            </thead>
            <tbody>
              {lay.size_breakdown.map((b) => (
                <tr key={b.id}>
                  <td dir="ltr" className="text-right font-semibold">{b.size}</td>
                  <td dir="ltr" className="text-right">{b.pieces_in_ply}</td>
                  <td dir="ltr" className="text-right">{b.theoretical_pieces}</td>
                  <td dir="ltr" className="text-right">
                    {b.actual_pieces ?? "—"}
                    {b.is_manually_adjusted && (
                      <span className="mr-1 text-xs text-amber-600">(يدوي)</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* ---- 4. roll lines ---- */}
      <section className="card mt-3">
        <h2 className="mb-2 font-bold">سطور الأتواب</h2>
        <div className="overflow-x-auto">
          <table className="data">
            <thead>
              <tr>
                <th>#</th>
                <th>طول التوب</th>
                <th>الراق</th>
                <th>الباقي</th>
                <th>اللون</th>
                <th>نهاية التوب</th>
                <th>الخامة / اللوط / التوب</th>
                <th>تيكت</th>
              </tr>
            </thead>
            <tbody>
              {lay.lines.map((l) => (
                <tr key={l.id}>
                  <td dir="ltr" className="text-right">{l.line_no}</td>
                  <td dir="ltr" className="text-right">{fmt(Number(l.roll_length_m))}</td>
                  <td dir="ltr" className="text-right">{l.plies}</td>
                  <td dir="ltr" className="text-right">
                    <span
                      className={`rounded px-1.5 py-0.5 ${
                        Number(l.remnant_m) <= 0
                          ? ""
                          : l.remnant_disposition === "waste"
                            ? "bg-rose-50 text-rose-700"
                            : "bg-emerald-50 text-emerald-700"
                      }`}
                    >
                      {fmt(Number(l.remnant_m))}
                    </span>
                  </td>
                  <td>{l.shade_note || "—"}</td>
                  <td className="text-xs">{l.roll_end_action_label}</td>
                  <td className="text-xs">
                    <bdi>{[l.article, l.lot_no, l.roll_no].filter(Boolean).join(" / ") || "—"}</bdi>
                  </td>
                  <td>
                    {l.ticket_image && (
                      <button onClick={() => setZoom(l.ticket_image)} aria-label="صورة التيكت">
                        <Camera className="h-4 w-4 text-slate-400 hover:text-red-600" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* ---- 5. consumption and shortage ---- */}
      <section className="card mt-3">
        <h2 className="mb-2 font-bold">الاستهلاك والعجز</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Big label="أطوال الأتواب" value={fmt(Number(lay.total_roll_length_m))} unit="م" />
          <Big label="المستهلك" value={fmt(Number(lay.consumed_m))} unit="م" />
          <Big label="البواقي" value={fmt(Number(lay.total_remnant_m))} unit="م" />
          <Big
            label="العجز"
            value={fmt(Number(lay.fabric_shortage_m))}
            unit="م"
            tone={lay.has_shortage ? "rose" : "slate"}
          />
        </div>
        {lay.has_shortage && (
          <p className="mt-2 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-800">
            أطوال الأتواب أكبر من (المستهلك + البواقي) بـ{" "}
            <bdi>{fmt(Number(lay.fabric_shortage_m))}</bdi> متر — القماش ده مش متحسِب له.
          </p>
        )}
        {lay.output && (
          <p className="mt-2 text-sm text-slate-600">
            فاقد القطع: <bdi>{lay.output.pieces_loss}</bdi> قطعة · التالف:{" "}
            <bdi>{lay.output.rejected_pieces}</bdi>
            {lay.output.notes && ` · ${lay.output.notes}`}
          </p>
        )}
        {productivity && (
          <p className="mt-2 text-sm text-slate-600">
            إنتاجية {productivity.full_name}:{" "}
            {productivity.pieces_per_hour != null ? (
              <>
                <bdi>{productivity.pieces_per_hour}</bdi> قطعة/ساعة —{" "}
                <span className={productivity.is_reliable ? "" : "text-amber-700"}>
                  {productivity.coverage_label}
                </span>
                {!productivity.is_reliable && " (تغطية أقل من النص، الرقم مش موثوق)"}
              </>
            ) : (
              <span className="text-slate-400">{productivity.unavailable_reason}</span>
            )}
          </p>
        )}
      </section>

      {/* ---- 6. documents ---- */}
      <section className="card mt-3">
        <h2 className="mb-2 font-bold">المرجع</h2>
        {lay.sheet_image ? (
          <button onClick={() => setZoom(lay.sheet_image)} className="block w-full">
            <img
              src={lay.sheet_image}
              alt="ورقة الدفتر"
              className="max-h-[70vh] w-full rounded-lg object-contain ring-1 ring-slate-200"
            />
          </button>
        ) : (
          <p className="text-sm text-slate-400">مفيش صورة دفتر</p>
        )}
        {lay.notes && <p className="mt-2 text-sm text-slate-600">{lay.notes}</p>}
      </section>

      {/* ---- 7. activity log ---- */}
      <section className="card mt-3">
        <h2 className="mb-2 font-bold">سجل النشاط</h2>
        <p className="text-sm text-slate-500">أنشأها {lay.entered_by_name}</p>
        {lay.audit_entries.length === 0 ? (
          <p className="mt-1 text-sm text-slate-400">مفيش تعديلات مسجّلة</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {lay.audit_entries.map((a) => (
              <li key={a.id} className="border-r-2 border-slate-200 pr-3 text-sm">
                <span className="font-semibold">{ACTION_LABEL[a.action] ?? a.action}</span>
                <span className="mr-2 text-xs text-slate-400" dir="ltr">
                  {new Date(a.at).toLocaleString("ar-EG")}
                </span>
                <div className="text-slate-600">
                  {a.user_name}
                  {a.field && ` · ${a.field}`}
                  {a.old_value && a.new_value && (
                    <>
                      : <bdi>{a.old_value}</bdi> ← <bdi>{a.new_value}</bdi>
                    </>
                  )}
                </div>
                {a.reason && <div className="text-xs text-amber-700">السبب: {a.reason}</div>}
              </li>
            ))}
          </ul>
        )}
      </section>

      {zoom && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-3 print:hidden"
          onClick={() => setZoom(null)}
        >
          <button className="absolute left-4 top-4 text-white" aria-label="إغلاق">
            <X className="h-7 w-7" />
          </button>
          <img src={zoom} alt="" className="max-h-full max-w-full object-contain" />
        </div>
      )}
    </div>
  );
}

function Big({
  label,
  value,
  unit,
  tone = "slate",
}: {
  label: string;
  value: string;
  unit?: string;
  tone?: "slate" | "rose";
}) {
  return (
    <div>
      <div className="text-[11px] text-slate-400">{label}</div>
      <div
        dir="ltr"
        className={`text-right text-xl font-bold ${
          tone === "rose" ? "text-rose-600" : "text-slate-800"
        }`}
      >
        {value}
      </div>
      {unit && <div className="text-right text-[10px] text-slate-400">{unit}</div>}
    </div>
  );
}

function Tag({ children, tone }: { children: React.ReactNode; tone: "rose" | "amber" | "slate" }) {
  const colour = {
    rose: "bg-rose-100 text-rose-700",
    amber: "bg-amber-100 text-amber-700",
    slate: "bg-slate-100 text-slate-600",
  }[tone];
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${colour}`}>{children}</span>;
}
