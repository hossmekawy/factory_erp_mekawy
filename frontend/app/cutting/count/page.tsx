"use client";

// The counting screen (SRS 7.3). A worklist of lays that are closed but not
// yet numbered, each opening into the small form the spec draws:
//
//   كود 1747 · موديل X · القطع النظرية 500
//   [ القطع السليمة: ___ ] [ التالف: ___ ] [ ملاحظات ]  [ حفظ ]
//
// The split across sizes is automatic and comes from the server, so the
// largest-remainder rule is not reimplemented here. Manual adjustment is
// locked by default and asks before it opens (SRS 4.9).

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Check, ChevronDown, ClipboardList, Loader2, Lock, Unlock } from "lucide-react";
import Shell from "@/components/Shell";
import { ApiError, api, errorText } from "@/lib/api";
import { Issue, fmt, issuesOf } from "@/lib/cutting";

type Row = {
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
  theoretical_pieces: number;
  total_plies: number;
  pieces_per_ply: number;
};

type SizeSplit = {
  size: string;
  pieces_in_ply: number;
  theoretical_pieces: number;
  actual_pieces: number;
};

type Preview = {
  actual_pieces: number;
  theoretical_pieces: number;
  sizes: SizeSplit[];
  pieces_loss: number;
  pieces_loss_pct: string | null;
  exceeds_tolerance: boolean;
  issues: Issue[];
};

export default function Page() {
  return (
    <Shell>
      <Suspense fallback={<div className="p-6 text-slate-500">جارٍ التحميل…</div>}>
        <CountingList />
      </Suspense>
    </Shell>
  );
}

function CountingList() {
  const params = useSearchParams();
  const focus = params.get("lay");

  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<number | null>(focus ? Number(focus) : null);
  const [doneIds, setDoneIds] = useState<number[]>([]);

  const load = useCallback(() => {
    setLoading(true);
    api("/api/cutting/lays/?awaiting_count=true&ordering=end_date")
      .then((d) => setRows(d.results))
      .catch((e) => setError(errorText(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const pending = rows.filter((r) => !doneIds.includes(r.id));

  return (
    <div className="font-tajawal mx-auto max-w-3xl p-3">
      <div className="mb-3 flex items-center justify-between">
        <h1 className="flex items-center gap-2 text-lg font-bold">
          <ClipboardList className="h-5 w-5 text-red-600" />
          الترقيم
        </h1>
        <Link href="/cutting" className="text-sm text-slate-500 hover:text-red-700">
          كل الفرشات
        </Link>
      </div>

      {error && <p className="card mb-3 text-rose-700">{error}</p>}

      {loading ? (
        <div className="card flex items-center justify-center gap-2 py-10 text-slate-500">
          <Loader2 className="h-5 w-5 animate-spin" />
          جارٍ التحميل…
        </div>
      ) : pending.length === 0 ? (
        <div className="card py-10 text-center">
          <Check className="mx-auto h-12 w-12 rounded-full bg-emerald-100 p-2.5 text-emerald-600" />
          <p className="mt-3 font-semibold">مفيش فرشات مستنية ترقيم</p>
          <p className="mt-1 text-sm text-slate-500">كل الفرشات المقفولة اتسجّلت قطعها.</p>
        </div>
      ) : (
        <div className="space-y-2">
          <p className="text-sm text-slate-500">
            <bdi>{pending.length}</bdi> فرشة مستنية ترقيم
          </p>
          {pending.map((row) => (
            <CountCard
              key={row.id}
              row={row}
              isOpen={open === row.id}
              onToggle={() => setOpen(open === row.id ? null : row.id)}
              onSaved={() => {
                setDoneIds((d) => [...d, row.id]);
                setOpen(null);
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function CountCard({
  row,
  isOpen,
  onToggle,
  onSaved,
}: {
  row: Row;
  isOpen: boolean;
  onToggle: () => void;
  onSaved: () => void;
}) {
  const [good, setGood] = useState("");
  const [rejected, setRejected] = useState("");
  const [notes, setNotes] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [manual, setManual] = useState<Record<string, string> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [issues, setIssues] = useState<Issue[]>([]);

  const goodNum = Number(good);

  // Ask the server for the split as he types. One implementation of the
  // largest-remainder rule, and it is the one the save will use.
  useEffect(() => {
    if (!isOpen || !good || goodNum <= 0) {
      setPreview(null);
      return;
    }
    const t = setTimeout(() => {
      api(`/api/cutting/lays/${row.id}/distribution/?actual_pieces=${goodNum}`)
        .then((d) => {
          setPreview(d);
          setError("");
        })
        .catch(() => setPreview(null));
    }, 300);
    return () => clearTimeout(t);
  }, [good, goodNum, isOpen, row.id]);

  const manualTotal = manual
    ? Object.values(manual).reduce((s, v) => s + (Number(v) || 0), 0)
    : 0;
  const manualMatches = !manual || manualTotal === goodNum;

  const unlockManual = () => {
    if (!preview) return;
    if (!confirm("هتعدّل التوزيع الأوتوماتيكي — متأكد؟")) return;
    setManual(
      Object.fromEntries(preview.sizes.map((s) => [s.size, String(s.actual_pieces)]))
    );
  };

  const save = async () => {
    setBusy(true);
    setError("");
    setIssues([]);
    try {
      await api(`/api/cutting/lays/${row.id}/output/`, {
        method: "POST",
        body: JSON.stringify({
          actual_pieces: goodNum,
          rejected_pieces: Number(rejected) || 0,
          notes,
          ...(manual
            ? {
                manual_distribution: Object.fromEntries(
                  Object.entries(manual).map(([k, v]) => [k, Number(v) || 0])
                ),
              }
            : {}),
        }),
      });
      onSaved();
    } catch (e) {
      const found = issuesOf((e as ApiError).data);
      setIssues(found);
      if (!found.length) setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  // Errors can come from either side: the preview already knows the count is
  // impossible (V9), and the save reports whatever it refused. Both must gray
  // the button out — the backend would refuse anyway, but letting him press it
  // and fail teaches nothing.
  const blocked =
    issues.some((i) => i.level === "error") ||
    (preview?.issues ?? []).some((i) => i.level === "error");

  return (
    <div className="card">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-2 text-right"
        data-testid="count-card"
      >
        <div className="flex-1">
          <div className="font-bold">
            <bdi>{row.code}</bdi>{" "}
            <span className="font-normal text-slate-500">
              <bdi>{row.garment_model_name}</bdi>
              {row.category && ` · ${row.category}`}
            </span>
          </div>
          <div className="text-xs text-slate-500">
            القطع النظرية <bdi className="font-semibold">{row.theoretical_pieces}</bdi> ·{" "}
            {row.bank_name} · {row.team_leader_name}
          </div>
        </div>
        <ChevronDown
          className={`h-4 w-4 shrink-0 text-slate-400 transition-transform ${
            isOpen ? "rotate-180" : ""
          }`}
        />
      </button>

      {isOpen && (
        <div className="mt-3 space-y-3 border-t border-slate-100 pt-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label>القطع السليمة</label>
              <input
                data-testid="good-pieces"
                dir="ltr"
                className="ltr-num min-h-12 text-base"
                inputMode="numeric"
                value={good}
                onChange={(e) => {
                  setGood(e.target.value);
                  setManual(null); // a new total invalidates a hand-made split
                }}
              />
            </div>
            <div>
              <label>التالف</label>
              <input
                data-testid="rejected-pieces"
                dir="ltr"
                className="ltr-num min-h-12 text-base"
                inputMode="numeric"
                value={rejected}
                onChange={(e) => setRejected(e.target.value)}
              />
            </div>
          </div>

          {preview && (
            <div>
              <div className="mb-1 flex items-center justify-between">
                <span className="text-sm font-semibold text-slate-600">
                  التوزيع على المقاسات
                </span>
                {manual ? (
                  <span className="flex items-center gap-1 text-xs font-semibold text-amber-700">
                    <Unlock className="h-3 w-3" />
                    تعديل يدوي
                  </span>
                ) : (
                  <button
                    type="button"
                    data-testid="unlock-manual"
                    onClick={unlockManual}
                    className="flex items-center gap-1 text-xs font-semibold text-slate-400 hover:text-red-700"
                  >
                    <Lock className="h-3 w-3" />
                    تعديل يدوي
                  </button>
                )}
              </div>

              <div className="overflow-x-auto">
                <table className="data">
                  <thead>
                    <tr>
                      <th>المقاس</th>
                      <th>في الراق</th>
                      <th>النظرية</th>
                      <th>الفعلية</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.sizes.map((s) => (
                      <tr key={s.size}>
                        <td dir="ltr" className="text-right font-semibold">{s.size}</td>
                        <td dir="ltr" className="text-right">{s.pieces_in_ply}</td>
                        <td dir="ltr" className="text-right text-slate-400">
                          {s.theoretical_pieces}
                        </td>
                        <td dir="ltr" className="text-right">
                          {manual ? (
                            <input
                              data-testid={`manual-${s.size}`}
                              dir="ltr"
                              className="ltr-num !py-1"
                              inputMode="numeric"
                              value={manual[s.size] ?? ""}
                              onChange={(e) =>
                                setManual({ ...manual, [s.size]: e.target.value })
                              }
                            />
                          ) : (
                            <span className="font-semibold">{s.actual_pieces}</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {manual && (
                <p
                  data-testid="manual-total"
                  className={`mt-1 text-sm font-semibold ${
                    manualMatches ? "text-emerald-700" : "text-rose-700"
                  }`}
                >
                  مجموع المقاسات <bdi>{manualTotal}</bdi> من <bdi>{goodNum}</bdi>
                  {!manualMatches && " — لازم يتساووا"}
                </p>
              )}

              <p className="mt-2 text-sm text-slate-600">
                فاقد القطع <bdi className="font-semibold">{preview.pieces_loss}</bdi>
                {preview.pieces_loss_pct != null && (
                  <bdi
                    className={`mr-1 ${
                      preview.exceeds_tolerance ? "font-semibold text-rose-700" : ""
                    }`}
                  >
                    ({fmt(Number(preview.pieces_loss_pct))}%)
                  </bdi>
                )}
                {preview.exceeds_tolerance && " — تعدّى نسبة التسامح، اكتب السبب"}
              </p>

              {preview.issues.map((i, n) => (
                <div
                  key={n}
                  data-testid="preview-issue"
                  data-code={i.code}
                  className="mt-2 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-800"
                >
                  <span className="ml-2 rounded bg-white/70 px-1.5 py-0.5 font-mono text-xs">
                    {i.code}
                  </span>
                  {i.message}
                </div>
              ))}
            </div>
          )}

          <div>
            <label>ملاحظات {preview?.exceeds_tolerance && "(مطلوبة)"}</label>
            <textarea
              data-testid="count-notes"
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>

          {error && <p className="font-semibold text-rose-700">{error}</p>}
          {issues.map((i, n) => (
            <div
              key={n}
              data-testid="save-issue"
              data-code={i.code}
              className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-800"
            >
              <span className="ml-2 rounded bg-white/70 px-1.5 py-0.5 font-mono text-xs">
                {i.code}
              </span>
              {i.message}
            </div>
          ))}

          <button
            data-testid="save-count"
            className="btn-primary w-full"
            disabled={
              busy ||
              !goodNum ||
              !manualMatches ||
              blocked ||
              (preview?.exceeds_tolerance === true && !notes.trim())
            }
            onClick={save}
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "حفظ"}
          </button>
        </div>
      )}
    </div>
  );
}
