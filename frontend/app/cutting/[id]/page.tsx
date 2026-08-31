"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, ScanBarcode, Trash2, X } from "lucide-react";
import Shell from "@/components/Shell";
import { api, errorText } from "@/lib/api";

type MarkerSize = {
  id: number;
  label: string;
  ratio: number;
  total_pieces: number;
};

type Marker = {
  id: number;
  fabric_width: string | null;
  marker_length: string;
  min_top_length: string | null;
  pieces_per_lay: number;
  layers_count: number | null;
  lays_count: number;
  sizes: MarkerSize[];
  expected_metraj: number | null;
  total_pieces: number;
};

type Roll = {
  id: number;
  roll_number: string;
  lot_number: string;
  article_name: string;
  color: string;
  width: string | null;
  length: string;
  weight: string | null;
  grade: string;
  lays_used: number;
  actual_remaining: string | null;
  status: string;
  expected_remaining: number | null;
  remaining_diff: number | null;
};

type Summary = {
  rolls_count: number;
  total_meters: number | null;
  total_lays: number;
  total_pieces: number;
  sizes: { label: string; pieces: number }[];
  expected_metraj: number | null;
  real_metraj: number | null;
  metraj_diff: number | null;
  total_remnants: number | null;
  shortage_quantity: number | null;
  consumed_meters: number | null;
  consumption_pct: number | null;
  waste_pct: number | null;
  quick_mode: boolean;
};

type Cutting = {
  id: number;
  code: string;
  model_name: string;
  color: string;
  production_order_no: string;
  cutting_date: string;
  created_by_name: string;
  worksheet_photo: string | null;
  quick_total_meters: string | null;
  has_shortage: boolean;
  shortage_quantity: string | null;
  shortage_reason: string;
  shortage_notes: string;
  notes: string;
  markers: Marker[];
  rolls: Roll[];
  summary: Summary;
};

const fmt = (v: number | string | null | undefined, d = 2) => {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(d).replace(/\.?0+$/, "") : String(v);
};

const EMPTY_ROLL = {
  roll_number: "",
  lot_number: "",
  article_name: "",
  color: "",
  width: "",
  length: "",
  weight: "",
  grade: "",
  lays_used: "",
};

export default function CuttingDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [data, setData] = useState<Cutting | null>(null);
  const [msg, setMsg] = useState("");

  const load = useCallback(() => {
    api(`/api/cuttings/${id}/`).then(setData).catch(() => {});
  }, [id]);
  useEffect(load, [load]);

  if (!data) {
    return (
      <Shell>
        <div className="py-20 text-center text-slate-400">جارٍ التحميل…</div>
      </Shell>
    );
  }

  const setSummary = (summary: Summary) => setData((d) => (d ? { ...d, summary } : d));

  return (
    <Shell>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">
          قصة <span className="text-red-700">{data.code}</span> — {data.model_name}
        </h1>
        <button className="btn-secondary" onClick={() => router.push("/cutting")}>
          ← كل القصات
        </button>
      </div>

      {msg && (
        <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800">{msg}</div>
      )}

      <div className="space-y-6">
        <HeaderCard data={data} onSaved={load} setMsg={setMsg} />
        <MarkerSection data={data} onChanged={load} setMsg={setMsg} />
        <RollEntryCard data={data} onAdded={load} setMsg={setMsg} />
        <RollsTable data={data} onChanged={load} setSummary={setSummary} setMsg={setMsg} />
        <ShortageSection data={data} onSaved={load} setMsg={setMsg} />
        <SummaryPanel s={data.summary} />
      </div>
    </Shell>
  );
}

/* ---------------- header ---------------- */

function HeaderCard({
  data,
  onSaved,
  setMsg,
}: {
  data: Cutting;
  onSaved: () => void;
  setMsg: (m: string) => void;
}) {
  const [form, setForm] = useState({
    code: data.code,
    model_name: data.model_name,
    color: data.color,
    production_order_no: data.production_order_no,
    cutting_date: data.cutting_date,
    notes: data.notes,
  });
  const [quick, setQuick] = useState(data.quick_total_meters ?? "");
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    setMsg("");
    try {
      await api(`/api/cuttings/${data.id}/`, {
        method: "PATCH",
        body: JSON.stringify({
          ...form,
          quick_total_meters: quick === "" ? null : quick,
        }),
      });
      onSaved();
    } catch (err) {
      setMsg(errorText(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card">
      <h2 className="mb-4 text-lg font-bold">بيانات القصة</h2>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
        <div>
          <label>الكود *</label>
          <input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
        </div>
        <div>
          <label>الموديل *</label>
          <input
            value={form.model_name}
            onChange={(e) => setForm({ ...form, model_name: e.target.value })}
          />
        </div>
        <div>
          <label>اللون</label>
          <input value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value })} />
        </div>
        <div>
          <label>أمر الإنتاج</label>
          <input
            value={form.production_order_no}
            onChange={(e) => setForm({ ...form, production_order_no: e.target.value })}
          />
        </div>
        <div>
          <label>التاريخ</label>
          <input
            type="date"
            value={form.cutting_date}
            onChange={(e) => setForm({ ...form, cutting_date: e.target.value })}
          />
        </div>
      </div>
      <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3">
        <div className="md:col-span-2">
          <label>ملاحظات</label>
          <input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        </div>
        <div>
          <label>إجمالي الأمتار — إدخال سريع (اختياري)</label>
          <input
            type="number"
            step="0.01"
            min="0"
            placeholder="بدل إدخال الأتواب واحد واحد"
            value={quick}
            onChange={(e) => setQuick(e.target.value)}
          />
        </div>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button className="btn-primary" onClick={save} disabled={saving}>
          {saving ? "جارٍ الحفظ…" : "حفظ البيانات"}
        </button>
        <span className="text-sm text-slate-500">موظف القص: {data.created_by_name}</span>
        {data.worksheet_photo && (
          <a
            href={data.worksheet_photo}
            target="_blank"
            className="text-sm font-medium text-red-700 hover:underline"
          >
            📷 صورة ورقة القصة
          </a>
        )}
      </div>
    </div>
  );
}

/* ---------------- markers (الفرشة) ---------------- */

const EMPTY_MARKER = {
  marker_length: "",
  pieces_per_lay: "",
  lays_count: "",
  fabric_width: "",
  min_top_length: "",
  layers_count: "",
};

type SizeRow = { label: string; ratio: string };

function MarkerSection({
  data,
  onChanged,
  setMsg,
}: {
  data: Cutting;
  onChanged: () => void;
  setMsg: (m: string) => void;
}) {
  const [form, setForm] = useState(EMPTY_MARKER);
  const [sizes, setSizes] = useState<SizeRow[]>([]);
  const [series, setSeries] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api("/api/cutting/sizes/").then(setSuggestions).catch(() => {});
  }, []);

  const ratioSum = sizes.reduce((t, s) => t + (Number(s.ratio) || 0), 0);

  function addSeries() {
    const labels = series.split(/[-,،\s]+/).map((s) => s.trim()).filter(Boolean);
    if (labels.length === 0) return;
    setSizes((prev) => [
      ...prev,
      ...labels
        .filter((l) => !prev.some((p) => p.label === l))
        .map((label) => ({ label, ratio: "1" })),
    ]);
    setSeries("");
  }

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMsg("");
    try {
      const body: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(form)) if (v !== "") body[k] = v;
      const cleanSizes = sizes.filter((s) => s.label.trim() !== "");
      if (cleanSizes.length > 0) {
        body.sizes = cleanSizes.map((s) => ({
          label: s.label.trim(),
          ratio: Number(s.ratio) || 1,
        }));
        delete body.pieces_per_lay; // server derives it from the sizes
      }
      await api(`/api/cuttings/${data.id}/markers/`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setForm(EMPTY_MARKER);
      setSizes([]);
      onChanged();
    } catch (err) {
      setMsg(errorText(err));
    } finally {
      setSaving(false);
    }
  }

  async function remove(mid: number) {
    if (!confirm("حذف هذه الفرشة؟")) return;
    try {
      await api(`/api/cuttings/${data.id}/markers/${mid}/`, { method: "DELETE" });
      onChanged();
    } catch (err) {
      setMsg(errorText(err));
    }
  }

  return (
    <div className="card">
      <h2 className="mb-4 text-lg font-bold">بيانات الفرشة</h2>

      {data.markers.length > 0 && (
        <div className="mb-4 overflow-x-auto">
          <table className="data min-w-[760px]">
            <thead>
              <tr>
                <th>طول الفرشة</th>
                <th>المقاسات</th>
                <th>قطع الراقة</th>
                <th>عدد الراقات</th>
                <th>عرض الفرشة</th>
                <th>أقل توب</th>
                <th>الطبقات</th>
                <th>الميتراج المتوقع</th>
                <th>إجمالي القطع</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.markers.map((m) => (
                <tr key={m.id}>
                  <td>{fmt(m.marker_length)} م</td>
                  <td>
                    {m.sizes.length === 0 ? (
                      "—"
                    ) : (
                      <div className="flex flex-wrap gap-1">
                        {m.sizes.map((s) => (
                          <span
                            key={s.id}
                            className="rounded-full bg-red-50 px-2 py-0.5 text-xs font-bold text-red-700"
                            dir="ltr"
                          >
                            {s.label}×{s.ratio}
                          </span>
                        ))}
                      </div>
                    )}
                  </td>
                  <td>{m.pieces_per_lay}</td>
                  <td>{m.lays_count}</td>
                  <td>{m.fabric_width ? `${fmt(m.fabric_width)} سم` : "—"}</td>
                  <td>{m.min_top_length ? `${fmt(m.min_top_length)} م` : "—"}</td>
                  <td>{m.layers_count ?? "—"}</td>
                  <td className="font-bold text-red-700">{fmt(m.expected_metraj, 3)}</td>
                  <td className="font-bold">{m.total_pieces}</td>
                  <td>
                    <button className="text-red-600 hover:text-red-800" onClick={() => remove(m.id)}>
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <form onSubmit={add} className="space-y-4">
        {/* المقاسات */}
        <div className="rounded-xl border border-slate-200 p-3">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <label className="!mb-0">المقاسات ونِسَبها في الراقة (اختياري)</label>
            <div className="flex items-center gap-2">
              <input
                className="!w-44"
                dir="ltr"
                placeholder="30-32-34-36-38"
                value={series}
                onChange={(e) => setSeries(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addSeries();
                  }
                }}
              />
              <button type="button" className="btn-secondary" onClick={addSeries}>
                إضافة سلسلة
              </button>
            </div>
          </div>
          {sizes.length > 0 && (
            <div className="mb-2 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
              {sizes.map((s, i) => (
                <div key={i} className="flex items-center gap-1 rounded-lg bg-slate-50 p-1.5">
                  <input
                    className="!px-2 text-center font-bold"
                    dir="ltr"
                    placeholder="المقاس"
                    list="size-suggestions"
                    value={s.label}
                    onChange={(e) =>
                      setSizes(sizes.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))
                    }
                  />
                  <span className="text-slate-400">×</span>
                  <input
                    type="number" min="1"
                    className="!w-14 !px-1 text-center"
                    value={s.ratio}
                    onChange={(e) =>
                      setSizes(sizes.map((x, j) => (j === i ? { ...x, ratio: e.target.value } : x)))
                    }
                  />
                  <button
                    type="button"
                    className="shrink-0 text-slate-400 hover:text-red-600"
                    onClick={() => setSizes(sizes.filter((_, j) => j !== i))}
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="text-sm font-medium text-red-700 hover:underline"
              onClick={() => setSizes([...sizes, { label: "", ratio: "1" }])}
            >
              ＋ مقاس
            </button>
            {sizes.length > 0 && (
              <span className="text-sm text-slate-500">
                قطع الراقة = <b className="text-red-700">{ratioSum}</b> (تلقائي من المقاسات)
              </span>
            )}
          </div>
          <datalist id="size-suggestions">
            {suggestions.map((s) => (
              <option key={s} value={s} />
            ))}
          </datalist>
        </div>

        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-7">
          <div>
            <label>طول الفرشة (م) *</label>
            <input
              type="number" step="0.01" min="0.01" required
              value={form.marker_length}
              onChange={(e) => setForm({ ...form, marker_length: e.target.value })}
            />
          </div>
          <div>
            <label>قطع الراقة {sizes.length === 0 && "*"}</label>
            {sizes.length > 0 ? (
              <input value={ratioSum} disabled className="bg-slate-50 text-center font-bold" />
            ) : (
              <input
                type="number" min="1" required
                value={form.pieces_per_lay}
                onChange={(e) => setForm({ ...form, pieces_per_lay: e.target.value })}
              />
            )}
          </div>
          <div>
            <label>عدد الراقات *</label>
            <input
              type="number" min="1" required
              value={form.lays_count}
              onChange={(e) => setForm({ ...form, lays_count: e.target.value })}
            />
          </div>
          <div>
            <label>العرض (سم)</label>
            <input
              type="number" step="0.01"
              value={form.fabric_width}
              onChange={(e) => setForm({ ...form, fabric_width: e.target.value })}
            />
          </div>
          <div>
            <label>أقل توب (م)</label>
            <input
              type="number" step="0.01"
              value={form.min_top_length}
              onChange={(e) => setForm({ ...form, min_top_length: e.target.value })}
            />
          </div>
          <div>
            <label>الطبقات</label>
            <input
              type="number" min="1"
              value={form.layers_count}
              onChange={(e) => setForm({ ...form, layers_count: e.target.value })}
            />
          </div>
          <div className="flex items-end">
            <button className="btn-primary w-full" disabled={saving}>
              {saving ? "…" : "إضافة فرشة"}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}

/* ---------------- roll entry (أتواب) ---------------- */

function RollEntryCard({
  data,
  onAdded,
  setMsg,
}: {
  data: Cutting;
  onAdded: () => void;
  setMsg: (m: string) => void;
}) {
  const [form, setForm] = useState(EMPTY_ROLL);
  const [found, setFound] = useState<string[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [rawText, setRawText] = useState("");
  const [showRaw, setShowRaw] = useState(false);
  const [ocrBusy, setOcrBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [scanOpen, setScanOpen] = useState(false);
  const rollNoRef = useRef<HTMLInputElement>(null);
  const canScan = typeof window !== "undefined" && "BarcodeDetector" in window;

  async function runOcr(file: File) {
    setOcrBusy(true);
    setMsg("");
    setWarnings([]);
    try {
      const body = new FormData();
      body.append("image", file);
      const r = await api("/api/cutting/ocr/", { method: "POST", body });
      const f = r.fields ?? {};
      setForm((prev) => ({
        ...prev,
        roll_number: f.roll_number != null ? String(f.roll_number) : prev.roll_number,
        lot_number: f.lot_number != null ? String(f.lot_number) : prev.lot_number,
        article_name: f.article_name ?? prev.article_name,
        color: f.color ?? prev.color,
        width: f.width != null ? String(f.width) : prev.width,
        length: f.length != null ? String(f.length) : prev.length,
        weight: f.weight != null ? String(f.weight) : prev.weight,
        grade: f.grade ?? prev.grade,
      }));
      setFound(r.found ?? []);
      setWarnings(r.warnings ?? []);
      setRawText(r.raw_text ?? "");
    } catch (err) {
      setMsg(errorText(err));
    } finally {
      setOcrBusy(false);
    }
  }

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMsg("");
    try {
      const body: Record<string, unknown> = { color: form.color, length: form.length };
      for (const k of ["roll_number", "lot_number", "article_name", "width", "weight", "grade", "lays_used"]) {
        const v = form[k as keyof typeof form];
        if (v !== "") body[k] = v;
      }
      await api(`/api/cuttings/${data.id}/rolls/`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setForm(EMPTY_ROLL);
      setFound([]);
      setWarnings([]);
      setRawText("");
      onAdded();
      rollNoRef.current?.focus();
    } catch (err) {
      setMsg(errorText(err));
    } finally {
      setSaving(false);
    }
  }

  const hl = (k: string) => (found.includes(k) ? "ring-2 ring-green-400" : "");

  return (
    <div className="card">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-bold">
          إضافة توب <span className="text-sm font-normal text-slate-500">(يُحفظ فوراً عند الإضافة)</span>
        </h2>
        <div className="flex gap-2">
          <label className={`btn-secondary cursor-pointer ${ocrBusy ? "opacity-50" : ""}`}>
            <Camera className="h-4 w-4" />
            {ocrBusy ? "جارٍ قراءة الليبل…" : "قراءة الليبل بالكاميرا"}
            <input
              type="file"
              accept="image/*"
              capture="environment"
              className="hidden"
              disabled={ocrBusy}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) runOcr(f);
                e.target.value = "";
              }}
            />
          </label>
          {canScan && (
            <button type="button" className="btn-secondary" onClick={() => setScanOpen(true)}>
              <ScanBarcode className="h-4 w-4" /> مسح باركود
            </button>
          )}
        </div>
      </div>

      {warnings.length > 0 && (
        <div className="mb-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
          {warnings.map((w, i) => (
            <div key={i}>⚠️ {w}</div>
          ))}
        </div>
      )}
      {found.length > 0 && (
        <div className="mb-3 text-sm text-green-700">
          ✅ تم قراءة {found.length} حقل من الليبل — راجِعها ثم اضغط إضافة.{" "}
          <button type="button" className="text-slate-500 underline" onClick={() => setShowRaw(!showRaw)}>
            {showRaw ? "إخفاء النص الخام" : "عرض النص الخام"}
          </button>
        </div>
      )}
      {showRaw && rawText && (
        <pre className="mb-3 max-h-40 overflow-auto rounded-lg bg-slate-50 p-3 text-xs" dir="ltr">
          {rawText}
        </pre>
      )}

      <form onSubmit={add} className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
        <div>
          <label>رقم التوب (اختياري)</label>
          <input
            ref={rollNoRef}
            dir="ltr"
            className={hl("roll_number")}
            value={form.roll_number}
            onChange={(e) => setForm({ ...form, roll_number: e.target.value })}
            placeholder="امسح الباركود هنا"
          />
        </div>
        <div>
          <label>اللون *</label>
          <input
            required
            className={hl("color")}
            value={form.color}
            onChange={(e) => setForm({ ...form, color: e.target.value })}
          />
        </div>
        <div>
          <label>الطول (م) *</label>
          <input
            required type="number" step="0.01" min="0.01"
            className={hl("length")}
            value={form.length}
            onChange={(e) => setForm({ ...form, length: e.target.value })}
          />
        </div>
        <div>
          <label>الوزن كجم (اختياري)</label>
          <input
            type="number" step="0.01"
            className={hl("weight")}
            value={form.weight}
            onChange={(e) => setForm({ ...form, weight: e.target.value })}
          />
        </div>
        <div>
          <label>العرض سم (اختياري)</label>
          <input
            type="number" step="0.01"
            className={hl("width")}
            value={form.width}
            onChange={(e) => setForm({ ...form, width: e.target.value })}
          />
        </div>
        <div>
          <label>رقم اللوط (اختياري)</label>
          <input
            dir="ltr"
            className={hl("lot_number")}
            value={form.lot_number}
            onChange={(e) => setForm({ ...form, lot_number: e.target.value })}
          />
        </div>
        <div>
          <label>اسم الخامة (اختياري)</label>
          <input
            className={hl("article_name")}
            value={form.article_name}
            onChange={(e) => setForm({ ...form, article_name: e.target.value })}
          />
        </div>
        <div>
          <label>الدرجة (اختياري)</label>
          <input
            className={hl("grade")}
            value={form.grade}
            onChange={(e) => setForm({ ...form, grade: e.target.value })}
          />
        </div>
        <div>
          <label>الراق المستخدم (اختياري)</label>
          <input
            type="number" min="0"
            value={form.lays_used}
            onChange={(e) => setForm({ ...form, lays_used: e.target.value })}
          />
        </div>
        <div className="flex items-end">
          <button className="btn-primary w-full" disabled={saving}>
            {saving ? "جارٍ الحفظ…" : "＋ إضافة التوب"}
          </button>
        </div>
      </form>

      {scanOpen && (
        <BarcodeScanner
          onResult={(code) => {
            setForm((f) => ({ ...f, roll_number: code }));
            setScanOpen(false);
          }}
          onClose={() => setScanOpen(false)}
        />
      )}
    </div>
  );
}

function BarcodeScanner({
  onResult,
  onClose,
}: {
  onResult: (code: string) => void;
  onClose: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let stream: MediaStream | null = null;
    let stop = false;
    async function run() {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "environment" },
        });
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const detector = new (window as any).BarcodeDetector();
        const tick = async () => {
          if (stop || !videoRef.current) return;
          try {
            const codes = await detector.detect(videoRef.current);
            if (codes.length > 0) {
              onResult(codes[0].rawValue);
              return;
            }
          } catch {}
          requestAnimationFrame(tick);
        };
        tick();
      } catch {
        setError("تعذر فتح الكاميرا");
      }
    }
    run();
    return () => {
      stop = true;
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [onResult]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl bg-white p-4" onClick={(e) => e.stopPropagation()}>
        <div className="mb-2 flex items-center justify-between">
          <b>وجّه الكاميرا نحو الباركود</b>
          <button className="text-slate-500" onClick={onClose}>✕</button>
        </div>
        {error ? (
          <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>
        ) : (
          <video ref={videoRef} className="w-full rounded-lg" muted playsInline />
        )}
      </div>
    </div>
  );
}

/* ---------------- rolls table ---------------- */

const STATUS_OPTIONS = [
  { value: "open", label: "قيد الاستخدام" },
  { value: "finished", label: "خلص" },
  { value: "remnant", label: "به باقي" },
];

function RollsTable({
  data,
  onChanged,
  setSummary,
  setMsg,
}: {
  data: Cutting;
  onChanged: () => void;
  setSummary: (s: Summary) => void;
  setMsg: (m: string) => void;
}) {
  async function patch(roll: Roll, body: Record<string, unknown>) {
    try {
      const r = await api(`/api/cuttings/${data.id}/rolls/${roll.id}/`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      setSummary(r.summary);
      onChanged();
    } catch (err) {
      setMsg(errorText(err));
    }
  }

  async function remove(roll: Roll) {
    if (!confirm(`حذف التوب ${roll.roll_number || roll.id}؟`)) return;
    try {
      await api(`/api/cuttings/${data.id}/rolls/${roll.id}/`, { method: "DELETE" });
      onChanged();
    } catch (err) {
      setMsg(errorText(err));
    }
  }

  if (data.rolls.length === 0) {
    return (
      <div className="card text-center text-slate-400">
        لم تتم إضافة أتواب بعد
        {data.summary.quick_mode && " — وضع الإدخال السريع مفعّل (إجمالي الأمتار فقط)"}
      </div>
    );
  }

  return (
    <div className="card overflow-x-auto p-0">
      <table className="data min-w-[860px]">
        <thead>
          <tr>
            <th>التوب</th>
            <th>اللون</th>
            <th>الطول</th>
            <th>الراق المستخدم</th>
            <th>الباقي</th>
            <th>الباقي المتوقع</th>
            <th>الفرق</th>
            <th>الحالة</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {data.rolls.map((r) => (
            <tr key={r.id}>
              <td>
                <b dir="ltr">{r.roll_number || `#${r.id}`}</b>
                {r.article_name && <div className="text-xs text-slate-500">{r.article_name}</div>}
              </td>
              <td>{r.color}</td>
              <td>{fmt(r.length)} م</td>
              <td>
                <input
                  type="number" min="0"
                  className="!w-20 text-center"
                  defaultValue={r.lays_used || ""}
                  onBlur={(e) => {
                    const v = e.target.value === "" ? 0 : Number(e.target.value);
                    if (v !== r.lays_used) patch(r, { lays_used: v });
                  }}
                />
              </td>
              <td>
                <input
                  type="number" step="0.01" min="0"
                  className="!w-24 text-center"
                  defaultValue={r.actual_remaining ?? ""}
                  onBlur={(e) => {
                    const v = e.target.value;
                    if (v !== (r.actual_remaining ?? "")) {
                      patch(r, { actual_remaining: v === "" ? null : v });
                    }
                  }}
                />
              </td>
              <td>{fmt(r.expected_remaining)}</td>
              <td
                className={
                  r.remaining_diff == null
                    ? ""
                    : r.remaining_diff < 0
                      ? "font-bold text-red-600"
                      : "font-bold text-green-700"
                }
              >
                {fmt(r.remaining_diff)}
              </td>
              <td>
                <select
                  className="!w-32"
                  value={r.status}
                  onChange={(e) => patch(r, { status: e.target.value })}
                >
                  {STATUS_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </td>
              <td>
                <button className="text-red-600 hover:text-red-800" onClick={() => remove(r)}>
                  <Trash2 className="h-4 w-4" />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ---------------- shortage ---------------- */

function ShortageSection({
  data,
  onSaved,
  setMsg,
}: {
  data: Cutting;
  onSaved: () => void;
  setMsg: (m: string) => void;
}) {
  const [has, setHas] = useState(data.has_shortage);
  const [qty, setQty] = useState(data.shortage_quantity ?? "");
  const [reason, setReason] = useState(data.shortage_reason);
  const [notes, setNotes] = useState(data.shortage_notes);
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    setMsg("");
    try {
      await api(`/api/cuttings/${data.id}/`, {
        method: "PATCH",
        body: JSON.stringify({
          has_shortage: has,
          shortage_quantity: has && qty !== "" ? qty : null,
          shortage_reason: has ? reason : "",
          shortage_notes: has ? notes : "",
        }),
      });
      onSaved();
    } catch (err) {
      setMsg(errorText(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card">
      <div className="mb-3 flex items-center gap-3">
        <h2 className="text-lg font-bold">عجز القماش</h2>
        <button
          type="button"
          onClick={() => setHas(!has)}
          className={`rounded-full px-4 py-1 text-sm font-bold ${
            has ? "bg-red-600 text-white" : "bg-slate-100 text-slate-600"
          }`}
        >
          {has ? "يوجد عجز" : "لا يوجد عجز"}
        </button>
      </div>
      {has && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <div>
            <label>كمية العجز (م)</label>
            <input type="number" step="0.01" min="0" value={qty} onChange={(e) => setQty(e.target.value)} />
          </div>
          <div>
            <label>السبب</label>
            <input value={reason} onChange={(e) => setReason(e.target.value)} />
          </div>
          <div>
            <label>ملاحظات</label>
            <input value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>
        </div>
      )}
      <button className="btn-primary mt-4" onClick={save} disabled={saving}>
        {saving ? "جارٍ الحفظ…" : "حفظ العجز"}
      </button>
    </div>
  );
}

/* ---------------- summary ---------------- */

function SummaryPanel({ s }: { s: Summary }) {
  const items: [string, string][] = [
    ["إجمالي الأتواب", String(s.rolls_count)],
    ["إجمالي الأمتار", fmt(s.total_meters)],
    ["إجمالي الراقات", String(s.total_lays)],
    ["إجمالي القطع", String(s.total_pieces)],
    ["الميتراج المتوقع (حسية)", fmt(s.expected_metraj, 3)],
    ["الميتراج الحقيقي", fmt(s.real_metraj, 3)],
    ["فرق الميتراج", fmt(s.metraj_diff, 3)],
    ["إجمالي البواقي", fmt(s.total_remnants)],
    ["إجمالي العجز", fmt(s.shortage_quantity)],
    ["نسبة الهالك %", fmt(s.waste_pct, 1)],
    ["نسبة استهلاك القماش %", fmt(s.consumption_pct, 1)],
  ];
  return (
    <div className="card">
      <h2 className="mb-4 text-lg font-bold">ملخص القصة</h2>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {items.map(([label, value]) => (
          <div key={label} className="rounded-xl bg-red-50 p-3 text-center">
            <div className="text-xs text-slate-600">{label}</div>
            <div className="mt-1 text-xl font-bold text-red-700">{value}</div>
          </div>
        ))}
      </div>
      {s.sizes.length > 0 && (
        <div className="mt-4">
          <div className="mb-2 text-sm font-bold text-slate-700">القطع حسب المقاس</div>
          <div className="flex flex-wrap gap-2">
            {s.sizes.map((z) => (
              <div
                key={z.label}
                className="rounded-full border border-red-200 bg-white px-3 py-1 text-sm"
              >
                <b className="text-red-700" dir="ltr">{z.label}</b>
                <span className="text-slate-500"> : {z.pieces} قطعة</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
