"use client";

// The most important screen in the module. Its order follows the notebook page
// in reference/notebook-page-1749.jpeg exactly, so the supervisor copies with
// his eyes and not his head:
//
//   التاريخ · الكود · الموديل (+ المقاسات بين أقواس) · عرض الفرشة · طول الفرشة · عدد القطع
//   ثم جدول: طول التوب | الراق | الباقي | اللون
//   ثم في الآخر: إجمالي الراق × عدد القطع
//
// The bank and the team leader are NOT on the notebook page but the system
// needs both, so they sit in their own block that says so rather than being
// slipped into the header as if he forgot to write them.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Camera, Check, Loader2, Plus, Trash2, X } from "lucide-react";
import Shell from "@/components/Shell";
import { ApiError, api, errorText } from "@/lib/api";
import { compressImage } from "@/lib/image";
import {
  Issue,
  LineDraft,
  ROLL_END_LABEL,
  RollEndAction,
  SizeChip,
  emptyLine,
  fmt,
  issuesOf,
  liveTotals,
  num,
  quickTotals,
  remnantIsWaste,
  widthToCm,
} from "@/lib/cutting";

type Bank = { id: number; code: string; name: string };
type GarmentModel = { id: number; code: string; name: string; fit: string };
type TeamLeader = {
  id: number;
  employee_code: string;
  full_name: string;
  was_present: boolean;
};

const today = () => new Date().toISOString().slice(0, 10);

// Big enough to hit with a thumb while standing up.
const FIELD = "min-h-12 text-base";

export default function NewLayPage() {
  const router = useRouter();

  // --- header, in notebook order ---------------------------------------
  const [startDate, setStartDate] = useState(today());
  const [endDate, setEndDate] = useState("");
  const [modelQuery, setModelQuery] = useState("");
  const [model, setModel] = useState<GarmentModel | null>(null);
  const [modelResults, setModelResults] = useState<GarmentModel[]>([]);
  const [addingModel, setAddingModel] = useState(false);
  const [newModelName, setNewModelName] = useState("");
  const [sizesRaw, setSizesRaw] = useState("");
  const [chips, setChips] = useState<SizeChip[]>([]);
  const [piecesPerPly, setPiecesPerPly] = useState(0);
  const [sizesError, setSizesError] = useState("");
  const [widthRaw, setWidthRaw] = useState("");
  const [lengthRaw, setLengthRaw] = useState("");

  // --- not on the page, required by the system --------------------------
  const [banks, setBanks] = useState<Bank[]>([]);
  const [bankId, setBankId] = useState<number | "">("");
  const [leaders, setLeaders] = useState<TeamLeader[]>([]);
  const [leaderId, setLeaderId] = useState<number | "">("");

  // --- body -------------------------------------------------------------
  const [mode, setMode] = useState<"detailed" | "quick">("detailed");
  const [lines, setLines] = useState<LineDraft[]>([emptyLine()]);
  const [quickMetres, setQuickMetres] = useState("");
  const [quickPlies, setQuickPlies] = useState("");
  const [notes, setNotes] = useState("");

  // --- sheet photo ------------------------------------------------------
  const [sheet, setSheet] = useState<File | null>(null);
  const [sheetPreview, setSheetPreview] = useState<string | null>(null);
  const [compressing, setCompressing] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // --- submission -------------------------------------------------------
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [issues, setIssues] = useState<Issue[]>([]);
  const [reason, setReason] = useState("");
  const [needsReason, setNeedsReason] = useState(false);
  const [savedId, setSavedId] = useState<number | null>(null);
  const [done, setDone] = useState(false);

  const layLength = num(lengthRaw);
  const widthCm = widthToCm(widthRaw);

  const totals = useMemo(
    () =>
      mode === "detailed"
        ? liveTotals(lines, layLength, piecesPerPly)
        : quickTotals(num(quickMetres), num(quickPlies), layLength, piecesPerPly),
    [mode, lines, quickMetres, quickPlies, layLength, piecesPerPly]
  );

  // --- lookups ----------------------------------------------------------

  useEffect(() => {
    api("/api/cutting/banks/?is_active=true")
      .then((d) => setBanks(d.results ?? d))
      .catch(() => {});
  }, []);

  // Team leaders are ranked by whether the device saw them on the lay's own
  // days — entry happens days later, so today's attendance is the wrong list.
  useEffect(() => {
    const from = startDate;
    const to = endDate || startDate;
    if (!from) return;
    api(`/api/cutting/team-leaders/?date_from=${from}&date_to=${to}`)
      .then((d) => setLeaders(d))
      .catch(() => {});
  }, [startDate, endDate]);

  useEffect(() => {
    if (model) return;
    const t = setTimeout(() => {
      api(`/api/cutting/models/?search=${encodeURIComponent(modelQuery)}&page=1`)
        .then((d) => setModelResults(d.results ?? []))
        .catch(() => {});
    }, 250);
    return () => clearTimeout(t);
  }, [modelQuery, model]);

  // The size text is split on the server so the screen and the database can
  // never disagree about what "30 32 32" means.
  useEffect(() => {
    if (!sizesRaw.trim()) {
      setChips([]);
      setPiecesPerPly(0);
      setSizesError("");
      return;
    }
    const t = setTimeout(() => {
      api("/api/cutting/size-sets/parse/", {
        method: "POST",
        body: JSON.stringify({ sizes_raw: sizesRaw }),
      })
        .then((d) => {
          setChips(d.sizes);
          setPiecesPerPly(d.total_pieces);
          setSizesError("");
        })
        .catch((e) => {
          setChips([]);
          setPiecesPerPly(0);
          setSizesError(issuesOf((e as ApiError).data)[0]?.message ?? "");
        });
    }, 300);
    return () => clearTimeout(t);
  }, [sizesRaw]);

  // SRS 7.2: the model in his hand may not be in the catalogue yet. He can add
  // it without leaving the screen — the backend lets a supervisor create a
  // model but not rewrite one.
  const quickAddModel = async () => {
    const code = modelQuery.trim();
    if (!code) return;
    setAddingModel(true);
    setError("");
    try {
      const created = await api("/api/cutting/models/", {
        method: "POST",
        body: JSON.stringify({ code, name: newModelName.trim() || code }),
      });
      setModel(created);
      setModelQuery("");
      setNewModelName("");
      setModelResults([]);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setAddingModel(false);
    }
  };

  // Picking a model offers its usual size run, still editable.
  const pickModel = useCallback((m: GarmentModel & { default_size_set_detail?: any }) => {
    setModel(m);
    setModelQuery("");
    setModelResults([]);
    const preset = m.default_size_set_detail?.sizes_raw;
    if (preset && !sizesRaw.trim()) setSizesRaw(preset);
  }, [sizesRaw]);

  // --- rows -------------------------------------------------------------

  const setLine = (key: string, patch: Partial<LineDraft>) =>
    setLines((ls) => ls.map((l) => (l.key === key ? { ...l, ...patch } : l)));

  const addLine = () => setLines((ls) => [...ls, emptyLine()]);

  const removeLine = (key: string) =>
    setLines((ls) => (ls.length === 1 ? [emptyLine()] : ls.filter((l) => l.key !== key)));

  // --- photo ------------------------------------------------------------

  const onPickPhoto = async (file: File | undefined) => {
    if (!file) return;
    setCompressing(true);
    try {
      const small = await compressImage(file);
      setSheet(small);
      setSheetPreview(URL.createObjectURL(small));
    } finally {
      setCompressing(false);
    }
  };

  // --- save -------------------------------------------------------------

  const payloadLines = () => {
    if (mode === "quick") {
      return [{
        roll_length_m: num(quickMetres).toFixed(2),
        plies: Math.round(num(quickPlies)),
        remnant_m: "0",
        is_aggregate: true,
        roll_end_action: "new_roll",
      }];
    }
    return lines
      .filter((l) => num(l.roll_length_m) > 0 && num(l.plies) > 0)
      .map((l) => ({
        roll_length_m: num(l.roll_length_m).toFixed(2),
        plies: Math.round(num(l.plies)),
        remnant_m: num(l.remnant_m).toFixed(2),
        shade_note: l.shade_note.trim(),
        roll_end_action: l.roll_end_action,
      }));
  };

  const missing = (): string | null => {
    if (!model) return "اختار الموديل";
    if (!piecesPerPly) return "اكتب المقاسات";
    if (!widthCm) return "اكتب عرض الفرشة";
    if (!layLength) return "اكتب طول الفرشة";
    if (bankId === "") return "اختار البنك";
    if (leaderId === "") return "اختار رئيس الفريق";
    if (!payloadLines().length) return "اكتب سطر واحد على الأقل";
    return null;
  };

  /** Create the lay if it is not saved yet, and return its id. */
  const saveLay = async (): Promise<number> => {
    if (savedId) {
      await api(`/api/cutting/lays/${savedId}/`, {
        method: "PATCH",
        body: JSON.stringify({
          start_date: startDate,
          end_date: endDate || startDate,
          bank: bankId,
          garment_model: model!.id,
          team_leader: leaderId,
          lay_width_cm: String(widthCm),
          lay_length_m: layLength.toFixed(2),
          sizes_raw: sizesRaw,
          entry_mode: mode,
          notes,
          lines: payloadLines(),
        }),
      });
      return savedId;
    }
    const created = await api("/api/cutting/lays/", {
      method: "POST",
      body: JSON.stringify({
        start_date: startDate,
        end_date: endDate || startDate,
        bank: bankId,
        garment_model: model!.id,
        team_leader: leaderId,
        lay_width_cm: String(widthCm),
        lay_length_m: layLength.toFixed(2),
        sizes_raw: sizesRaw,
        entry_mode: mode,
        notes,
        lines: payloadLines(),
      }),
    });
    setSavedId(created.id);
    return created.id;
  };

  const uploadSheet = async (id: number) => {
    if (!sheet) return;
    const form = new FormData();
    form.append("sheet_image", sheet);
    await api(`/api/cutting/lays/${id}/attachments/`, { method: "POST", body: form });
  };

  const run = async (closeAfter: boolean) => {
    setError("");
    setIssues([]);
    const gap = missing();
    if (gap) {
      setError(gap);
      return;
    }
    if (closeAfter && !sheet) {
      setError("صوّر ورقة الدفتر قبل القفل");
      return;
    }
    setBusy(true);
    try {
      const id = await saveLay();
      await uploadSheet(id);
      if (!closeAfter) {
        setError("");
        setIssues([]);
        setBusy(false);
        return;
      }
      await api(`/api/cutting/lays/${id}/close/`, {
        method: "POST",
        body: JSON.stringify({ reason }),
      });
      setDone(true);
    } catch (e) {
      const found = issuesOf((e as ApiError).data);
      setIssues(found);
      // Warnings alone mean the backend is waiting for a reason, not refusing.
      const onlyWarnings = found.length > 0 && found.every((i) => i.level !== "error");
      setNeedsReason(onlyWarnings);
      if (!found.length) setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  // --- render -----------------------------------------------------------

  if (done) {
    return (
      <Shell>
        <div className="font-tajawal mx-auto max-w-md p-4 text-center">
          <div className="card mt-10">
            <Check className="mx-auto h-14 w-14 rounded-full bg-emerald-100 p-3 text-emerald-600" />
            <h1 className="mt-4 text-xl font-bold">الفرشة اتقفلت</h1>
            <p className="mt-1 text-slate-500">
              {totals.totalPlies} راق · {totals.theoreticalPieces} قطعة نظرية
            </p>
            <div className="mt-6 flex flex-col gap-2">
              <button className="btn-primary" onClick={() => location.reload()}>
                فرشة جديدة
              </button>
              <button className="btn-secondary" onClick={() => router.push("/")}>
                رجوع للوحة التحكم
              </button>
            </div>
          </div>
        </div>
      </Shell>
    );
  }

  const errorIssues = issues.filter((i) => i.level === "error");
  const warnIssues = issues.filter((i) => i.level === "warning");
  const infoIssues = issues.filter((i) => i.level === "info");

  return (
    <Shell>
      {/* pb leaves room for the fixed calculation bar */}
      <div className="font-tajawal mx-auto max-w-2xl p-3 pb-44">
        <h1 className="mb-3 text-lg font-bold">فرشة جديدة</h1>

        {/* ---- header: the notebook's own order ---- */}
        <section className="card space-y-3">
          <Row label="التاريخ">
            <div className="flex items-center gap-2">
              <input
                type="date"
                className={FIELD}
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
              />
              <span className="shrink-0 text-sm text-slate-400">→</span>
              <input
                type="date"
                className={FIELD}
                value={endDate}
                min={startDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </div>
            <Hint>سيب التاريخ التاني فاضي لو الفرشة يوم واحد</Hint>
          </Row>

          <Row label="الكود / الموديل">
            {model ? (
              <div className="flex items-center justify-between rounded-lg border border-slate-300 bg-slate-50 px-3 py-2">
                <span className="font-semibold">
                  <bdi>{model.code}</bdi>
                  <span className="mr-2 text-sm font-normal text-slate-500">
                    <bdi>{model.name}</bdi>
                    {model.fit && <> · {model.fit}</>}
                  </span>
                </span>
                <button
                  type="button"
                  className="text-sm text-red-700 hover:underline"
                  onClick={() => setModel(null)}
                >
                  تغيير
                </button>
              </div>
            ) : (
              <div className="relative">
                <input
                  data-testid="model-search"
                  dir="ltr"
                  className={`${FIELD} ltr-num`}
                  inputMode="numeric"
                  placeholder="اكتب الكود أو اسم الموديل…"
                  value={modelQuery}
                  onChange={(e) => setModelQuery(e.target.value)}
                />
                {modelResults.length > 0 && (
                  <div className="absolute z-20 mt-1 max-h-56 w-full overflow-y-auto rounded-lg border border-slate-200 bg-white shadow-lg">
                    {modelResults.map((m) => (
                      <button
                        key={m.id}
                        type="button"
                        className="block w-full px-3 py-3 text-right hover:bg-red-50"
                        onClick={() => pickModel(m)}
                      >
                        <bdi className="font-semibold">{m.code}</bdi>{" "}
                        <span className="text-sm text-slate-500">
                          <bdi>{m.name}</bdi>
                          {m.fit && <> · {m.fit}</>}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
                {modelQuery.trim() && modelResults.length === 0 && (
                  <div className="mt-2 rounded-lg border border-dashed border-slate-300 p-3">
                    <p className="text-sm text-slate-600">
                      مفيش موديل بالكود{" "}
                      <span className="font-bold">{modelQuery.trim()}</span>
                    </p>
                    <input
                      data-testid="new-model-name"
                      className={`${FIELD} mt-2`}
                      placeholder="اسم الموديل (اختياري)"
                      value={newModelName}
                      onChange={(e) => setNewModelName(e.target.value)}
                    />
                    <button
                      type="button"
                      data-testid="quick-add-model"
                      className="btn-secondary mt-2 w-full"
                      disabled={addingModel}
                      onClick={quickAddModel}
                    >
                      {addingModel ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <>
                          <Plus className="h-4 w-4" />
                          ضيفه للكتالوج
                        </>
                      )}
                    </button>
                  </div>
                )}
              </div>
            )}
          </Row>

          <Row label="المقاسات">
            <input
              data-testid="sizes-input"
              dir="ltr"
              className={`${FIELD} ltr-num`}
              inputMode="numeric"
              placeholder="30 32 32 34 34 36"
              value={sizesRaw}
              onChange={(e) => setSizesRaw(e.target.value)}
            />
            {sizesError && <p className="mt-1 text-sm text-rose-600">{sizesError}</p>}
            {chips.length > 0 && (
              <div dir="ltr" className="mt-2 flex flex-wrap justify-end gap-1.5">
                {chips.map((c) => (
                  <span
                    key={c.size}
                    className="rounded-full bg-slate-100 px-2.5 py-1 text-sm font-semibold text-slate-700"
                  >
                    {c.size}
                    {c.pieces_in_ply > 1 && (
                      <span className="ml-1 text-red-600">&times;{c.pieces_in_ply}</span>
                    )}
                  </span>
                ))}
              </div>
            )}
            <Hint>الدفتر بيكتبها بين أقواس — (32)(34) بتشتغل برضه</Hint>
          </Row>

          <div className="grid grid-cols-2 gap-3">
            <Row label="عرض الفرشة">
              <input
                data-testid="width-input"
                dir="ltr"
                className={`${FIELD} ltr-num`}
                inputMode="decimal"
                placeholder="1.62"
                value={widthRaw}
                onChange={(e) => setWidthRaw(e.target.value)}
              />
              <Hint testid="width-hint">
                {widthCm ? `هيتسجّل ${fmt(widthCm)} سم` : "بالمتر زي الدفتر"}
              </Hint>
            </Row>
            <Row label="طول الفرشة">
              <input
                data-testid="length-input"
                dir="ltr"
                className={`${FIELD} ltr-num`}
                inputMode="decimal"
                placeholder="6.55"
                value={lengthRaw}
                onChange={(e) => setLengthRaw(e.target.value)}
              />
              <Hint>بالمتر</Hint>
            </Row>
          </div>

          <Row label="عدد القطع">
            <div
              data-testid="pieces-per-ply"
              className="flex h-12 items-center rounded-lg border border-slate-200 bg-slate-50 px-3 text-base font-bold text-slate-700"
            >
              <bdi>{piecesPerPly || "—"}</bdi>
              <span className="mr-2 text-sm font-normal text-slate-400">
                بيتحسب من المقاسات
              </span>
            </div>
          </Row>
        </section>

        {/* ---- required by the system, absent from the notebook ---- */}
        <section className="card mt-3 space-y-3 border-r-4 border-amber-300">
          <p className="text-sm font-semibold text-amber-700">
            مش مكتوبين في الدفتر — السيستم محتاجهم
          </p>
          <div className="grid grid-cols-2 gap-3">
            <Row label="البنك">
              <select
                data-testid="bank-select"
                className={FIELD}
                value={bankId}
                onChange={(e) => setBankId(e.target.value ? Number(e.target.value) : "")}
              >
                <option value="">اختار…</option>
                {banks.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.code} — {b.name}
                  </option>
                ))}
              </select>
            </Row>
            <Row label="رئيس الفريق">
              <select
                data-testid="leader-select"
                className={FIELD}
                value={leaderId}
                onChange={(e) => setLeaderId(e.target.value ? Number(e.target.value) : "")}
              >
                <option value="">اختار…</option>
                {leaders.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.was_present ? "✓ " : ""}
                    {l.full_name}
                  </option>
                ))}
              </select>
              <Hint>✓ = البصمة شافته في أيام الفرشة</Hint>
            </Row>
          </div>
        </section>

        {/* ---- mode switch ---- */}
        <div className="mt-3 grid grid-cols-2 gap-1 rounded-xl bg-slate-200 p-1">
          {(["detailed", "quick"] as const).map((m) => (
            <button
              key={m}
              type="button"
              data-testid={`mode-${m}`}
              onClick={() => setMode(m)}
              className={`rounded-lg py-2.5 text-sm font-semibold transition ${
                mode === m ? "bg-white text-red-700 shadow-sm" : "text-slate-600"
              }`}
            >
              {m === "detailed" ? "تفصيلي" : "سريع"}
            </button>
          ))}
        </div>

        {/* ---- body ---- */}
        {mode === "detailed" ? (
          <section className="card mt-3">
            <div className="mb-2 grid grid-cols-[1.6rem_1.15fr_0.75fr_0.85fr_1fr_1.6rem] gap-1.5 text-xs font-semibold text-slate-500">
              <span />
              <span>طول التوب</span>
              <span>الراق</span>
              <span>الباقي</span>
              <span>اللون</span>
              <span />
            </div>

            <div className="space-y-2">
              {lines.map((l, i) => {
                const waste = remnantIsWaste(num(l.remnant_m));
                const hasRemnant = num(l.remnant_m) > 0;
                return (
                  <div key={l.key} className="space-y-1">
                    <div className="grid grid-cols-[1.6rem_1.15fr_0.75fr_0.85fr_1fr_1.6rem] items-center gap-1.5">
                      <span className="text-center text-xs font-bold text-slate-400">
                        {i + 1}
                      </span>
                      <input
                        data-testid="line-length"
                        dir="ltr"
                        className={`${FIELD} ltr-num`}
                        inputMode="decimal"
                        value={l.roll_length_m}
                        onChange={(e) => setLine(l.key, { roll_length_m: e.target.value })}
                      />
                      <input
                        data-testid="line-plies"
                        dir="ltr"
                        className={`${FIELD} ltr-num`}
                        inputMode="numeric"
                        value={l.plies}
                        onChange={(e) => setLine(l.key, { plies: e.target.value })}
                      />
                      <input
                        className={`${FIELD} ltr-num ${
                          hasRemnant
                            ? waste
                              ? "!border-rose-400 !bg-rose-50 !text-rose-700"
                              : "!border-emerald-400 !bg-emerald-50 !text-emerald-700"
                            : ""
                        }`}
                        data-testid="line-remnant"
                        dir="ltr"
                        inputMode="decimal"
                        value={l.remnant_m}
                        onChange={(e) => setLine(l.key, { remnant_m: e.target.value })}
                      />
                      <input
                        data-testid="line-shade"
                        className={FIELD}
                        value={l.shade_note}
                        placeholder="كحلي"
                        onChange={(e) => setLine(l.key, { shade_note: e.target.value })}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && i === lines.length - 1) addLine();
                        }}
                      />
                      <button
                        type="button"
                        aria-label="حذف السطر"
                        className="flex h-12 items-center justify-center text-slate-300 hover:text-rose-600"
                        onClick={() => removeLine(l.key)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>

                    <div className="mr-7 flex gap-1">
                      {(Object.keys(ROLL_END_LABEL) as RollEndAction[]).map((a) => (
                        <button
                          key={a}
                          type="button"
                          data-testid={`roll-end-${a}`}
                          onClick={() => setLine(l.key, { roll_end_action: a })}
                          className={`rounded-full px-2.5 py-1 text-xs font-medium transition ${
                            l.roll_end_action === a
                              ? "bg-red-600 text-white"
                              : "bg-slate-100 text-slate-500"
                          }`}
                        >
                          {ROLL_END_LABEL[a]}
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>

            <button
              type="button"
              data-testid="add-line"
              onClick={addLine}
              className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg border-2 border-dashed border-slate-300 py-3 text-sm font-semibold text-slate-500 hover:border-red-300 hover:text-red-600"
            >
              <Plus className="h-4 w-4" />
              إضافة سطر
            </button>

            {totals.spliceCount > 0 && (
              <p className="mt-2 text-center text-xs text-slate-500">
                {totals.spliceCount} وصل — الراق الموصول اتحسب مرة واحدة
              </p>
            )}
          </section>
        ) : (
          <section className="card mt-3 grid grid-cols-2 gap-3">
            <Row label="إجمالي الأمتار">
              <input
                data-testid="quick-metres"
                dir="ltr"
                className={`${FIELD} ltr-num`}
                inputMode="decimal"
                value={quickMetres}
                onChange={(e) => setQuickMetres(e.target.value)}
              />
            </Row>
            <Row label="إجمالي الراق">
              <input
                data-testid="quick-plies"
                dir="ltr"
                className={`${FIELD} ltr-num`}
                inputMode="numeric"
                value={quickPlies}
                onChange={(e) => setQuickPlies(e.target.value)}
              />
            </Row>
            <p className="col-span-2 text-xs text-slate-500">
              الفرشة هتتسجّل &quot;إدخال سريع&quot; وتقدر تفكّها لتفصيلي بعدين.
            </p>
          </section>
        )}

        {/* ---- notebook photo ---- */}
        <section className="card mt-3">
          <label className="mb-2">صورة ورقة الدفتر</label>
          <input
            ref={fileRef}
            data-testid="sheet-input"
            type="file"
            accept="image/*"
            capture="environment"
            className="hidden"
            onChange={(e) => onPickPhoto(e.target.files?.[0])}
          />
          {sheetPreview ? (
            <div className="relative">
              <img
                src={sheetPreview}
                alt="ورقة الدفتر"
                className="max-h-56 w-full rounded-lg object-cover"
              />
              <button
                type="button"
                aria-label="شيل الصورة"
                onClick={() => {
                  setSheet(null);
                  setSheetPreview(null);
                  if (fileRef.current) fileRef.current.value = "";
                }}
                className="absolute left-2 top-2 rounded-full bg-black/60 p-1.5 text-white"
              >
                <X className="h-4 w-4" />
              </button>
              <p className="mt-1 text-xs text-slate-500">
                {(sheet!.size / 1024).toFixed(0)} كيلوبايت بعد الضغط
              </p>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={compressing}
              className="flex w-full items-center justify-center gap-2 rounded-lg border-2 border-dashed border-slate-300 py-6 text-sm font-semibold text-slate-500 hover:border-red-300 hover:text-red-600"
            >
              {compressing ? (
                <Loader2 className="h-5 w-5 animate-spin" />
              ) : (
                <Camera className="h-5 w-5" />
              )}
              {compressing ? "بيتضغط…" : "صوّر الورقة"}
            </button>
          )}
          <p className="mt-2 text-xs text-amber-700">إلزامية قبل القفل</p>
        </section>

        <section className="card mt-3">
          <label>ملاحظات</label>
          <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </section>

        {/* ---- what the backend said ---- */}
        {(error || issues.length > 0) && (
          <section className="card mt-3 space-y-2">
            {error && <p className="font-semibold text-rose-700">{error}</p>}
            {errorIssues.map((i, n) => (
              <IssueLine key={n} issue={i} tone="rose" />
            ))}
            {warnIssues.map((i, n) => (
              <IssueLine key={n} issue={i} tone="amber" />
            ))}
            {infoIssues.map((i, n) => (
              <IssueLine key={n} issue={i} tone="slate" />
            ))}

            {needsReason && (
              <div className="pt-1">
                <label>السبب — مطلوب عشان تعدّي التحذيرات</label>
                <textarea
                  data-testid="reason-input"
                  rows={2}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="مثلاً: رئيس الفريق كان في فرع تاني"
                />
                <button
                  data-testid="close-with-reason"
                  className="btn-primary mt-2 w-full"
                  disabled={busy || !reason.trim()}
                  onClick={() => run(true)}
                >
                  اقفل بالسبب ده
                </button>
              </div>
            )}
          </section>
        )}

        {/* ---- live calculation bar: no server call ---- */}
        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-200 bg-white/95 backdrop-blur">
          <div className="mx-auto grid max-w-2xl grid-cols-4 gap-1 px-3 py-2 text-center">
            <Stat testid="stat-plies" label="إجمالي الراق" value={String(totals.totalPlies)} />
            <Stat testid="stat-pieces" label="القطع النظرية" value={String(totals.theoreticalPieces)} />
            <Stat testid="stat-metrage" label="الميتراج" value={fmt(totals.expectedMetrage, 3)} />
            <Stat
              testid="stat-shortage"
              label="العجز"
              value={fmt(totals.shortage)}
              tone={totals.shortage > 0.5 ? "rose" : "slate"}
            />
          </div>
          <div className="mx-auto flex max-w-2xl gap-2 px-3 pb-3">
            <button
              data-testid="save-btn"
              className="btn-secondary flex-1"
              disabled={busy}
              onClick={() => run(false)}
            >
              حفظ
            </button>
            <button
              data-testid="close-btn"
              className="btn-primary flex-[2]"
              disabled={busy}
              onClick={() => run(true)}
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "قفل الفرشة"}
            </button>
          </div>
        </div>
      </div>
    </Shell>
  );
}

// --- small pieces --------------------------------------------------------

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label>{label}</label>
      {children}
    </div>
  );
}

function Hint({ children, testid }: { children: React.ReactNode; testid?: string }) {
  return (
    <p data-testid={testid} className="mt-1 text-xs text-slate-400">
      {children}
    </p>
  );
}

function Stat({
  label,
  value,
  tone = "slate",
  testid,
}: {
  label: string;
  value: string;
  tone?: "slate" | "rose";
  testid?: string;
}) {
  return (
    <div>
      <div className="text-[11px] text-slate-400">{label}</div>
      <div
        data-testid={testid}
        dir="ltr"
        className={`text-lg font-bold ${
          tone === "rose" ? "text-rose-600" : "text-slate-800"
        }`}
      >
        {value}
      </div>
    </div>
  );
}

function IssueLine({ issue, tone }: { issue: Issue; tone: "rose" | "amber" | "slate" }) {
  const colour = {
    rose: "bg-rose-50 text-rose-800",
    amber: "bg-amber-50 text-amber-800",
    slate: "bg-slate-50 text-slate-600",
  }[tone];
  return (
    <div
      data-testid="issue"
      data-code={issue.code}
      data-level={issue.level}
      className={`rounded-lg px-3 py-2 text-sm ${colour}`}
    >
      <span className="ml-2 rounded bg-white/70 px-1.5 py-0.5 font-mono text-xs">
        {issue.code}
      </span>
      {issue.message}
      {issue.line_no && <span className="text-xs"> (سطر {issue.line_no})</span>}
    </div>
  );
}
