"use client";

import { useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api, errorText } from "@/lib/api";

type Employee = { id: number; full_name: string; employee_code: string };
type Punch = {
  id: number;
  local_time: string;
  punch_state: number;
  source: string;
};

const SOURCE_AR: Record<string, string> = { device: "بصمة", manual: "يدوي" };

function EmployeePicker({
  value,
  onPick,
}: {
  value: Employee | null;
  onPick: (e: Employee | null) => void;
}) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Employee[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => {
      api(`/api/employees/?search=${encodeURIComponent(q)}&page=1`)
        .then((d) => setResults(d.results))
        .catch(() => {});
    }, 250);
    return () => clearTimeout(t);
  }, [q, open]);

  if (value) {
    return (
      <div className="flex items-center justify-between rounded-lg border border-slate-300 bg-slate-50 px-3 py-2">
        <span className="font-semibold">
          {value.full_name}{" "}
          <span className="text-sm text-slate-500">({value.employee_code})</span>
        </span>
        <button
          className="text-sm text-red-700 hover:underline"
          onClick={() => {
            onPick(null);
            setQ("");
          }}
        >
          تغيير
        </button>
      </div>
    );
  }

  return (
    <div className="relative">
      <input
        placeholder="ابحث عن الموظف بالاسم أو الكود…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onFocus={() => setOpen(true)}
      />
      {open && results.length > 0 && (
        <div className="absolute z-10 mt-1 max-h-60 w-full overflow-y-auto rounded-lg border border-slate-200 bg-white shadow-lg">
          {results.map((e) => (
            <button
              key={e.id}
              className="block w-full px-3 py-2 text-right hover:bg-red-50"
              onClick={() => {
                onPick(e);
                setOpen(false);
              }}
            >
              {e.full_name}{" "}
              <span className="text-sm text-slate-500">({e.employee_code})</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ManualAttendancePage() {
  const today = new Date().toISOString().slice(0, 10);
  const [emp, setEmp] = useState<Employee | null>(null);
  const [date, setDate] = useState(today);
  const [punches, setPunches] = useState<Punch[]>([]);
  const [checkIn, setCheckIn] = useState("");
  const [checkOut, setCheckOut] = useState("");
  const [msg, setMsg] = useState("");
  const [saving, setSaving] = useState(false);

  const hhmm = (iso: string) => iso.slice(11, 16);

  const loadDay = useCallback(() => {
    if (!emp) return;
    api(`/api/attendance/day/?employee=${emp.id}&date=${date}`)
      .then((d) => {
        const p: Punch[] = d.punches;
        setPunches(p);
        // Prefill inputs from existing MANUAL punches (device punches stay in
        // the list below and are not overwritten).
        const mIn = p.find((x) => x.source === "manual" && x.punch_state === 0);
        const mOut = p.find((x) => x.source === "manual" && x.punch_state === 1);
        setCheckIn(mIn ? hhmm(mIn.local_time) : "");
        setCheckOut(mOut ? hhmm(mOut.local_time) : "");
      })
      .catch(() => {});
  }, [emp, date]);

  useEffect(() => {
    setMsg("");
    if (emp) loadDay();
    else {
      setPunches([]);
      setCheckIn("");
      setCheckOut("");
    }
  }, [emp, date, loadDay]);

  async function save() {
    if (!emp) return;
    setSaving(true);
    setMsg("");
    try {
      await api("/api/attendance/manual/", {
        method: "POST",
        body: JSON.stringify({
          employee: emp.id,
          date,
          check_in: checkIn || null,
          check_out: checkOut || null,
        }),
      });
      setMsg("✅ تم حفظ الحضور");
      loadDay();
    } catch (e) {
      setMsg(errorText(e));
    } finally {
      setSaving(false);
    }
  }

  async function deletePunch(id: number) {
    if (!confirm("حذف هذه البصمة؟")) return;
    try {
      await api(`/api/attendance/${id}/`, { method: "DELETE" });
      loadDay();
    } catch (e) {
      setMsg(errorText(e));
    }
  }

  return (
    <Shell>
      <h1 className="mb-2 text-2xl font-bold">تسجيل / تعديل الحضور يدوياً</h1>
      <p className="mb-6 text-sm text-slate-600">
        لو الموظف نسي يعمل البصمة، اختر اسمه واليوم وسجّل وقت الحضور والانصراف.
      </p>

      <div className="card mb-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label>الموظف</label>
            <EmployeePicker value={emp} onPick={setEmp} />
          </div>
          <div>
            <label>اليوم</label>
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </div>
        </div>
      </div>

      {emp && (
        <>
          <div className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="card">
              <div className="mb-3 text-lg font-bold text-emerald-700">🟢 الحضور</div>
              <button
                type="button"
                className="btn-secondary mb-3 w-full text-base"
                onClick={() => setCheckIn("08:00")}
              >
                ⏰ اختصار: ٨:٠٠ صباحاً
              </button>
              <label>أو وقت آخر</label>
              <input
                type="time"
                value={checkIn}
                onChange={(e) => setCheckIn(e.target.value)}
              />
              {checkIn && (
                <button
                  className="mt-2 text-sm text-red-600 hover:underline"
                  onClick={() => setCheckIn("")}
                >
                  مسح وقت الحضور
                </button>
              )}
            </div>

            <div className="card">
              <div className="mb-3 text-lg font-bold text-red-700">🔵 الانصراف</div>
              <button
                type="button"
                className="btn-secondary mb-3 w-full text-base"
                onClick={() => setCheckOut("17:00")}
              >
                ⏰ اختصار: ٥:٠٠ مساءً
              </button>
              <label>أو وقت آخر</label>
              <input
                type="time"
                value={checkOut}
                onChange={(e) => setCheckOut(e.target.value)}
              />
              {checkOut && (
                <button
                  className="mt-2 text-sm text-red-600 hover:underline"
                  onClick={() => setCheckOut("")}
                >
                  مسح وقت الانصراف
                </button>
              )}
            </div>
          </div>

          {msg && (
            <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800">
              {msg}
            </div>
          )}

          <button className="btn-primary mb-6 w-full text-base sm:w-auto" onClick={save} disabled={saving}>
            {saving ? "جارٍ الحفظ…" : "💾 حفظ الحضور"}
          </button>

          <div className="card">
            <h2 className="mb-3 text-lg font-bold">بصمات هذا اليوم</h2>
            {punches.length === 0 ? (
              <div className="text-slate-500">لا توجد أي بصمات مسجلة لهذا اليوم</div>
            ) : (
              <div className="space-y-2">
                {punches.map((p) => (
                  <div
                    key={p.id}
                    className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2"
                  >
                    <div className="flex items-center gap-3">
                      <span className="font-bold" dir="ltr">
                        {hhmm(p.local_time)}
                      </span>
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                          p.source === "manual"
                            ? "bg-amber-100 text-amber-700"
                            : "bg-slate-100 text-slate-600"
                        }`}
                      >
                        {SOURCE_AR[p.source] ?? p.source}
                      </span>
                      <span className="text-xs text-slate-500">
                        {p.punch_state === 1 ? "انصراف" : "حضور"}
                      </span>
                    </div>
                    <button
                      className="text-sm text-red-600 hover:underline"
                      onClick={() => deletePunch(p.id)}
                    >
                      حذف
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </Shell>
  );
}
