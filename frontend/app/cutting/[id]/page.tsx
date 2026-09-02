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
  Pencil,
  Plus,
  Trash2,
  Check,
  ClipboardList,
  Loader2,
  Lock,
  Printer,
  X,
} from "lucide-react";
import Shell from "@/components/Shell";
import { ApiError, api, downloadFile, errorText } from "@/lib/api";
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

type Shade = {
  id: number;
  shade: string;
  plies: number;
  pieces: number;
  pct: number | null;
  is_manual: boolean;
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
  bank: number;
  team_leader: number;
  bank_detail: { code: string; name: string };
  code: string;
  garment_model_detail: { code: string; name: string; category_label: string };
  team_leader_detail: { full_name: string; employee_code: string };
  entered_by_name: string;
  lines: Line[];
  size_breakdown: Breakdown[];
  shade_breakdown: Shade[];
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
  line_added: "إضافة سطر",
  line_edited: "تعديل سطر",
  line_deleted: "حذف سطر",
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
  const [editing, setEditing] = useState(false);
  const [editLine, setEditLine] = useState<Line | "new" | null>(null);
  const [printing, setPrinting] = useState<"a4" | "a5" | null>(null);

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

  const downloadSheet = async (size: "a4" | "a5") => {
    setPrinting(size);
    setError("");
    try {
      await downloadFile(
        `/api/cutting/lays/${id}/pdf/?paper=${size}`,
        `قصة-${lay?.code ?? id}-${size}.pdf`
      );
    } catch (e) {
      setError(errorText(e));
    } finally {
      setPrinting(null);
    }
  };

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
              <bdi>{lay.code}</bdi>{" "}
              <span className="font-normal text-slate-500">
                <bdi>{m.name}</bdi>
                {m.category_label && ` · ${m.category_label}`}
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
            <Link href={`/cutting/count?lay=${id}`} className="btn-primary">
              <ClipboardList className="h-4 w-4" />
              تسجيل القطع
            </Link>
          )}
          {lay.status === "counted" && (
            <button className="btn-primary" disabled={busy} onClick={() => act("approve")}>
              <Check className="h-4 w-4" />
              اعتماد
            </button>
          )}
          <button
            data-testid="edit-lay"
            className="btn-secondary"
            onClick={() => setEditing(true)}
          >
            <Pencil className="h-4 w-4" />
            تعديل
          </button>
          {/* A built sheet, not the browser's print — that put the navigation
              and the buttons on the paper. */}
          <button
            data-testid="pdf-a4"
            className="btn-secondary"
            disabled={printing !== null}
            onClick={() => downloadSheet("a4")}
          >
            {printing === "a4" ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Printer className="h-4 w-4" />
            )}
            طباعة A4
          </button>
          <button
            data-testid="pdf-a5"
            className="btn-secondary"
            disabled={printing !== null}
            onClick={() => downloadSheet("a5")}
          >
            {printing === "a5" ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Printer className="h-4 w-4" />
            )}
            A5
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

      {/* ---- 3b. plies per shade ---- */}
      {lay.shade_breakdown?.length > 0 && (
        <section className="card mt-3">
          <h2 className="mb-2 font-bold">الراق لكل لون</h2>
          <div className="overflow-x-auto">
            <table className="data" data-testid="shade-table">
              <thead>
                <tr>
                  <th>اللون</th>
                  <th>الراق</th>
                  <th>القطع</th>
                  <th>النسبة</th>
                </tr>
              </thead>
              <tbody>
                {lay.shade_breakdown.map((sh) => (
                  <tr key={sh.id}>
                    <td className="font-semibold">{sh.shade}</td>
                    <td dir="ltr" className="text-right">{sh.plies}</td>
                    <td dir="ltr" className="text-right">{sh.pieces}</td>
                    <td dir="ltr" className="text-right">
                      {sh.pct != null ? `${sh.pct}%` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {lay.shade_breakdown.some((sh) => sh.is_manual) && (
            <p className="mt-2 text-xs text-slate-500">مُدخَل يدوي مع الإدخال السريع.</p>
          )}
        </section>
      )}

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
                <th />
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
                  <td className="whitespace-nowrap">
                    <button
                      data-testid="edit-line"
                      className="p-1 text-slate-400 hover:text-red-700"
                      onClick={() => setEditLine(l)}
                      aria-label="تعديل السطر"
                    >
                      <Pencil className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <button
          data-testid="add-line"
          className="btn-secondary mt-3 w-full print:hidden"
          onClick={() => setEditLine("new")}
        >
          <Plus className="h-4 w-4" />
          إضافة سطر
        </button>
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
        <h2 className="mb-2 font-bold">صورة ورقة الدفتر</h2>
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

      {editLine && (
        <EditLineDialog
          lay={lay}
          line={editLine === "new" ? null : editLine}
          shades={lay.lines.map((l) => l.shade_note).filter(Boolean)}
          onClose={() => setEditLine(null)}
          onSaved={() => {
            setEditLine(null);
            load();
          }}
        />
      )}

      {editing && (
        <EditLayDialog
          lay={lay}
          onClose={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            load();
          }}
        />
      )}

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

// Editing the header of a lay. The lines live on the new-lay screen; what gets
// mistyped and needs fixing from here is the code, the dates and who it is on.
// SRS 3: once the lay is closed the reason is mandatory and lands in the log.
function EditLayDialog({
  lay,
  onClose,
  onSaved,
}: {
  lay: Lay;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isOpen = lay.status === "open";
  const [code, setCode] = useState(lay.code);
  const [startDate, setStartDate] = useState(lay.start_date);
  const [endDate, setEndDate] = useState(lay.end_date);
  const [notes, setNotes] = useState(lay.notes ?? "");
  const [bank, setBank] = useState<number | "">(lay.bank ?? "");
  const [leader, setLeader] = useState<number | "">(lay.team_leader ?? "");
  const [reason, setReason] = useState("");
  const [banks, setBanks] = useState<{ id: number; name: string }[]>([]);
  const [leaders, setLeaders] = useState<{ id: number; full_name: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [issues, setIssues] = useState<Issue[]>([]);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    api("/api/cutting/banks/?is_active=true")
      .then((d) => setBanks(d.results ?? d))
      .catch(() => {});
    api(`/api/cutting/team-leaders/?date_from=${startDate}&date_to=${endDate}`)
      .then(setLeaders)
      .catch(() => {});
  }, [startDate, endDate]);

  const save = async () => {
    setBusy(true);
    setError("");
    setIssues([]);
    setFieldErrors({});
    try {
      await api(`/api/cutting/lays/${lay.id}/`, {
        method: "PATCH",
        body: JSON.stringify({
          code: code.trim(),
          start_date: startDate,
          end_date: endDate || startDate,
          bank,
          team_leader: leader,
          notes,
          ...(isOpen ? {} : { edit_reason: reason }),
        }),
      });
      onSaved();
    } catch (e) {
      const data = (e as ApiError).data as Record<string, unknown> | null;
      const found = issuesOf(data);
      if (found.length) setIssues(found);
      else if (data && typeof data === "object") {
        const perField: Record<string, string> = {};
        for (const [k, v] of Object.entries(data)) {
          if (Array.isArray(v)) perField[k] = String(v[0]);
        }
        setFieldErrors(perField);
        if (!Object.keys(perField).length) setError(errorText(e));
      } else setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-0 sm:items-center sm:p-4 print:hidden">
      <div className="max-h-[92vh] w-full max-w-md overflow-y-auto rounded-t-2xl bg-white p-4 sm:rounded-2xl">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-bold">تعديل القصة</h2>
          <button onClick={onClose} aria-label="إغلاق">
            <X className="h-5 w-5 text-slate-400" />
          </button>
        </div>

        {!isOpen && (
          <p className="mb-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
            القصة مقفولة — التعديل بيتسجّل في سجل النشاط بالسبب.
          </p>
        )}

        <div className="space-y-3">
          <div>
            <label>كود القصة</label>
            <input
              data-testid="edit-code"
              dir="ltr"
              className="ltr-num min-h-11"
              inputMode="numeric"
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
            {fieldErrors.code && (
              <p data-testid="edit-code-error" className="mt-1 text-sm text-rose-600">
                {fieldErrors.code}
              </p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="!text-xs">من</label>
              <input
                data-testid="edit-start"
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
              />
            </div>
            <div>
              <label className="!text-xs">إلى</label>
              <input
                data-testid="edit-end"
                type="date"
                min={startDate}
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="!text-xs">البنك</label>
              <select
                data-testid="edit-bank"
                value={bank}
                onChange={(e) => setBank(e.target.value ? Number(e.target.value) : "")}
              >
                {banks.map((b) => (
                  <option key={b.id} value={b.id}>{b.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="!text-xs">رئيس الفريق</label>
              <select
                data-testid="edit-leader"
                value={leader}
                onChange={(e) => setLeader(e.target.value ? Number(e.target.value) : "")}
              >
                {leaders.map((l) => (
                  <option key={l.id} value={l.id}>{l.full_name}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label>ملاحظات</label>
            <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>

          {!isOpen && (
            <div>
              <label>
                سبب التعديل<span className="text-rose-600"> *</span>
              </label>
              <textarea
                data-testid="edit-reason"
                rows={2}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="مثلاً: الكود اتكتب غلط"
              />
            </div>
          )}
        </div>

        {error && <p className="mt-3 text-sm font-semibold text-rose-700">{error}</p>}
        {issues.map((i, n) => (
          <div
            key={n}
            data-testid="edit-issue"
            data-code={i.code}
            className="mt-2 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-800"
          >
            {i.message}
          </div>
        ))}

        <div className="mt-4 flex gap-2">
          <button className="btn-secondary flex-1" onClick={onClose}>إلغاء</button>
          <button
            data-testid="edit-save"
            className="btn-primary flex-1"
            disabled={busy || !code.trim() || (!isOpen && !reason.trim())}
            onClick={save}
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "حفظ"}
          </button>
        </div>
      </div>
    </div>
  );
}

// One roll line. A line typed wrong used to mean deleting the whole lay and
// entering it again — not a thing anyone does at a bank with a notebook in
// hand. Same rules as the header: an open lay changes freely, a closed one
// needs a reason, and every number on the lay is recalculated by the server
// afterwards.
function EditLineDialog({
  lay,
  line,
  shades,
  onClose,
  onSaved,
}: {
  lay: Lay;
  line: Line | null;
  shades: string[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const isOpen = lay.status === "open";
  const [length, setLength] = useState(line?.roll_length_m ?? "");
  const [plies, setPlies] = useState(line ? String(line.plies) : "");
  const [remnant, setRemnant] = useState(line?.remnant_m ?? "0");
  const [shade, setShade] = useState(line?.shade_note ?? "");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [issues, setIssues] = useState<Issue[]>([]);

  const body = () => ({
    roll_length_m: length,
    plies: Number(plies),
    remnant_m: remnant || "0",
    shade_note: shade.trim(),
    ...(isOpen ? {} : { edit_reason: reason }),
  });

  const run = async (method: "POST" | "PATCH" | "DELETE") => {
    setBusy(true);
    setError("");
    setIssues([]);
    try {
      if (method === "DELETE") {
        await api(`/api/cutting/lay-lines/${line!.id}/`, {
          method: "DELETE",
          body: JSON.stringify(isOpen ? {} : { edit_reason: reason }),
        });
      } else if (method === "POST") {
        await api("/api/cutting/lay-lines/", {
          method: "POST",
          body: JSON.stringify({ lay: lay.id, ...body() }),
        });
      } else {
        await api(`/api/cutting/lay-lines/${line!.id}/`, {
          method: "PATCH",
          body: JSON.stringify(body()),
        });
      }
      onSaved();
    } catch (e) {
      const found = issuesOf((e as ApiError).data);
      setIssues(found);
      if (!found.length) setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  const incomplete = !length || !Number(plies) || (!isOpen && !reason.trim());

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-0 sm:items-center sm:p-4 print:hidden">
      <div className="max-h-[92vh] w-full max-w-md overflow-y-auto rounded-t-2xl bg-white p-4 sm:rounded-2xl">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-bold">{line ? `تعديل سطر ${line.line_no}` : "سطر جديد"}</h2>
          <button onClick={onClose} aria-label="إغلاق">
            <X className="h-5 w-5 text-slate-400" />
          </button>
        </div>

        {!isOpen && (
          <p className="mb-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
            القصة مقفولة — التعديل بيتسجّل في سجل النشاط، والحسابات كلها هتتعاد.
          </p>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="!text-xs">طول التوب</label>
            <input
              data-testid="line-length-edit"
              dir="ltr"
              className="ltr-num min-h-11"
              inputMode="decimal"
              value={length}
              onChange={(e) => setLength(e.target.value)}
            />
          </div>
          <div>
            <label className="!text-xs">الراق</label>
            <input
              data-testid="line-plies-edit"
              dir="ltr"
              className="ltr-num min-h-11"
              inputMode="numeric"
              value={plies}
              onChange={(e) => setPlies(e.target.value)}
            />
          </div>
          <div>
            <label className="!text-xs">الباقي</label>
            <input
              data-testid="line-remnant-edit"
              dir="ltr"
              className="ltr-num min-h-11"
              inputMode="decimal"
              value={remnant}
              onChange={(e) => setRemnant(e.target.value)}
            />
          </div>
          <div>
            <label className="!text-xs">اللون</label>
            <input
              data-testid="line-shade-edit"
              className="min-h-11"
              list="known-shades"
              value={shade}
              onChange={(e) => setShade(e.target.value)}
            />
            <datalist id="known-shades">
              {[...new Set(shades)].map((sh) => (
                <option key={sh} value={sh} />
              ))}
            </datalist>
          </div>
        </div>

        {!isOpen && (
          <div className="mt-3">
            <label>
              سبب التعديل<span className="text-rose-600"> *</span>
            </label>
            <textarea
              data-testid="line-reason"
              rows={2}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="مثلاً: الراق اتكتب غلط"
            />
          </div>
        )}

        {error && <p className="mt-3 text-sm font-semibold text-rose-700">{error}</p>}
        {issues.map((i, n) => (
          <div
            key={n}
            data-testid="line-issue"
            data-code={i.code}
            className="mt-2 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-800"
          >
            <span className="ml-2 rounded bg-white/70 px-1.5 py-0.5 font-mono text-xs">
              {i.code}
            </span>
            {i.message}
          </div>
        ))}

        <div className="mt-4 flex gap-2">
          {line && (
            <button
              data-testid="delete-line"
              className="btn-danger"
              disabled={busy || (!isOpen && !reason.trim())}
              onClick={() => {
                if (confirm("متأكد إنك عايز تمسح السطر ده؟")) run("DELETE");
              }}
              aria-label="حذف السطر"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          )}
          <button className="btn-secondary flex-1" onClick={onClose}>إلغاء</button>
          <button
            data-testid="save-line"
            className="btn-primary flex-1"
            disabled={busy || incomplete}
            onClick={() => run(line ? "PATCH" : "POST")}
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "حفظ"}
          </button>
        </div>
      </div>
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
