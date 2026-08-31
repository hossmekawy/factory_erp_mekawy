"use client";

import { useEffect, useRef, useState } from "react";
import Shell from "@/components/Shell";
import { api, errorText } from "@/lib/api";

const DAYS: { value: number; label: string }[] = [
  { value: 5, label: "السبت" },
  { value: 6, label: "الأحد" },
  { value: 0, label: "الاثنين" },
  { value: 1, label: "الثلاثاء" },
  { value: 2, label: "الأربعاء" },
  { value: 3, label: "الخميس" },
  { value: 4, label: "الجمعة" },
];

type Settings = {
  company_name: string;
  work_start: string;
  work_end: string;
  weekend_days: number[];
  favicon_url: string | null;
  icon_192_url: string | null;
  updated_at: string;
};

export default function SettingsPage() {
  const [s, setS] = useState<Settings | null>(null);
  const [companyName, setCompanyName] = useState("");
  const [workStart, setWorkStart] = useState("08:00");
  const [workEnd, setWorkEnd] = useState("17:00");
  const [weekend, setWeekend] = useState<number[]>([4]);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  function load() {
    api("/api/settings/")
      .then((d: Settings) => {
        setS(d);
        setCompanyName(d.company_name);
        setWorkStart(d.work_start.slice(0, 5));
        setWorkEnd(d.work_end.slice(0, 5));
        setWeekend(d.weekend_days);
      })
      .catch((e) => setErr(errorText(e)));
  }

  useEffect(load, []);

  function toggleDay(v: number) {
    setWeekend((cur) => (cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v]));
  }

  async function saveSchedule(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setErr("");
    setMsg("");
    try {
      await api("/api/settings/", {
        method: "PUT",
        body: JSON.stringify({
          company_name: companyName,
          work_start: workStart,
          work_end: workEnd,
          weekend_days: weekend,
        }),
      });
      setMsg("✅ تم حفظ الإعدادات");
      load();
    } catch (e) {
      setErr(errorText(e));
    } finally {
      setSaving(false);
    }
  }

  async function uploadFavicon(file: File) {
    setUploading(true);
    setErr("");
    setMsg("");
    const fd = new FormData();
    fd.append("image", file);
    try {
      await api("/api/settings/favicon/", { method: "POST", body: fd });
      setMsg("✅ تم تحديث الأيقونة — قد تحتاج تحديث الصفحة (Ctrl+F5) لرؤيتها في المتصفح");
      load();
    } catch (e) {
      setErr(errorText(e));
    } finally {
      setUploading(false);
    }
  }

  if (!s) {
    return (
      <Shell>
        <div className="text-slate-500">جارٍ التحميل…</div>
      </Shell>
    );
  }

  return (
    <Shell>
      <h1 className="mb-6 text-2xl font-bold">الإعدادات</h1>

      {msg && (
        <div className="mb-4 rounded-lg bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {msg}
        </div>
      )}
      {err && (
        <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{err}</div>
      )}

      <form onSubmit={saveSchedule} className="space-y-6">
        <div className="card">
          <h2 className="mb-4 text-lg font-bold">اسم النظام</h2>
          <input value={companyName} onChange={(e) => setCompanyName(e.target.value)} />
        </div>

        <div className="card">
          <h2 className="mb-4 text-lg font-bold">مواعيد العمل</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label>بداية الدوام (الحضور)</label>
              <input
                type="time"
                value={workStart}
                onChange={(e) => setWorkStart(e.target.value)}
              />
            </div>
            <div>
              <label>نهاية الدوام (الانصراف)</label>
              <input type="time" value={workEnd} onChange={(e) => setWorkEnd(e.target.value)} />
            </div>
          </div>
        </div>

        <div className="card">
          <h2 className="mb-4 text-lg font-bold">أيام الإجازة الأسبوعية</h2>
          <div className="flex flex-wrap gap-2">
            {DAYS.map((d) => {
              const active = weekend.includes(d.value);
              return (
                <button
                  type="button"
                  key={d.value}
                  onClick={() => toggleDay(d.value)}
                  className={`rounded-lg border px-4 py-2 text-sm font-semibold transition ${
                    active
                      ? "border-red-300 bg-red-50 text-red-700"
                      : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
                  }`}
                >
                  {d.label} {active ? "🔴 إجازة" : ""}
                </button>
              );
            })}
          </div>
          <p className="mt-3 text-sm text-slate-500">
            الأيام المحدَّدة باللون الأحمر تُحتسب إجازة أسبوعية ولا تظهر في التقرير كأيام عمل.
          </p>
        </div>

        <button className="btn-primary" disabled={saving}>
          {saving ? "جارٍ الحفظ…" : "حفظ الإعدادات"}
        </button>
      </form>

      <div className="card mt-6">
        <h2 className="mb-4 text-lg font-bold">أيقونة النظام (Favicon)</h2>
        <p className="mb-4 text-sm text-slate-600">
          ارفع أي صورة (PNG، JPG، أو حتى شعار كبير) وسيتم تحويلها تلقائياً لأيقونة المتصفح
          (favicon.ico) وأيقونات تطبيق الجوال (PWA) بكل المقاسات المطلوبة.
        </p>
        <div className="flex flex-wrap items-center gap-4">
          {s.icon_192_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={s.icon_192_url}
              alt="أيقونة النظام"
              className="h-16 w-16 rounded-xl border border-slate-200 object-contain bg-slate-50"
            />
          ) : (
            <div className="flex h-16 w-16 items-center justify-center rounded-xl border border-dashed border-slate-300 text-slate-400">
              لا توجد
            </div>
          )}
          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/x-icon,image/svg+xml"
            className="max-w-xs"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) uploadFavicon(f);
            }}
          />
          {uploading && <span className="text-sm text-slate-500">جارٍ الرفع والتحويل…</span>}
        </div>
      </div>
    </Shell>
  );
}
