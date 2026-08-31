"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import Shell from "@/components/Shell";
import EmployeeForm, { EmployeeData } from "@/components/EmployeeForm";
import { api, errorText } from "@/lib/api";

const FINGERS: Record<number, string> = {
  0: "خنصر يسرى", 1: "بنصر يسرى", 2: "وسطى يسرى", 3: "سبابة يسرى", 4: "إبهام يسرى",
  5: "إبهام يمنى", 6: "سبابة يمنى", 7: "وسطى يمنى", 8: "بنصر يمنى", 9: "خنصر يمنى",
};

type Fingerprint = { id: number; finger_id: number; updated_at: string };
type Punch = { id: number; timestamp: string; punch_state: number };

export default function EmployeeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [emp, setEmp] = useState<EmployeeData | null>(null);
  const [tab, setTab] = useState<"data" | "fp" | "attendance">("data");
  const [fps, setFps] = useState<Fingerprint[]>([]);
  const [punches, setPunches] = useState<Punch[]>([]);
  const [finger, setFinger] = useState(6);
  const [enrollState, setEnrollState] = useState<string>("");
  const [msg, setMsg] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadFps = useCallback(() => {
    api(`/api/employees/${id}/fingerprints/`).then(setFps).catch(() => {});
  }, [id]);

  useEffect(() => {
    api(`/api/employees/${id}/`).then(setEmp).catch(() => {});
    loadFps();
    api(`/api/employees/${id}/attendance/`)
      .then((d) => setPunches(d.results))
      .catch(() => {});
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [id, loadFps]);

  async function enroll() {
    setMsg("");
    setEnrollState("");
    try {
      const res = await api(`/api/employees/${id}/enroll-fp/`, {
        method: "POST",
        body: JSON.stringify({ finger_id: finger }),
      });
      setEnrollState("queued");
      const cmdId = res.command_id;
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        try {
          const cmd = await api(`/api/commands/${cmdId}/`);
          if (cmd.status === "sent") setEnrollState("sent");
          if (cmd.status === "done") {
            setEnrollState("done");
            loadFps();
            clearInterval(pollRef.current!);
          }
          if (cmd.status === "failed") {
            setEnrollState("failed");
            clearInterval(pollRef.current!);
          }
        } catch {}
      }, 3000);
    } catch (e) {
      setMsg(errorText(e));
    }
  }

  async function pushToDevice() {
    setMsg("");
    try {
      await api(`/api/employees/${id}/push-to-device/`, { method: "POST" });
      setMsg("تم إرسال البيانات إلى الجهاز — ستُنفذ خلال ثوانٍ");
    } catch (e) {
      setMsg(errorText(e));
    }
  }

  async function removeEmployee() {
    if (!confirm(`هل أنت متأكد من حذف ${emp?.full_name}؟ سيُحذف من الجهاز أيضاً.`)) return;
    await api(`/api/employees/${id}/`, { method: "DELETE" });
    router.replace("/employees");
  }

  const ENROLL_LABELS: Record<string, string> = {
    queued: "⏳ في انتظار اتصال الجهاز…",
    sent: "📟 أُرسل الأمر — اطلب من الموظف وضع إصبعه على الجهاز الآن",
    done: "✅ تم تسجيل البصمة بنجاح",
    failed: "❌ فشل التسجيل — حاول مرة أخرى",
  };

  if (!emp) {
    return (
      <Shell>
        <div className="text-slate-500">جارٍ التحميل…</div>
      </Shell>
    );
  }

  return (
    <Shell>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">
          {emp.full_name}{" "}
          <span className="text-base font-normal text-slate-500">
            (كود {emp.employee_code})
          </span>
        </h1>
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={pushToDevice}>
            إرسال للجهاز 📟
          </button>
          <button className="btn-danger" onClick={removeEmployee}>
            حذف
          </button>
        </div>
      </div>

      {msg && (
        <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800">{msg}</div>
      )}

      <div className="mb-6 flex gap-2 border-b border-slate-300">
        {(
          [
            ["data", "البيانات"],
            ["fp", "البصمات"],
            ["attendance", "سجل الحضور"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-4 py-2 text-sm font-semibold ${
              tab === key
                ? "border-b-2 border-red-600 text-red-700"
                : "text-slate-500 hover:text-slate-700"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "data" && (
        <EmployeeForm
          initial={emp}
          onSaved={(e) => {
            setEmp(e);
            setMsg("تم حفظ البيانات بنجاح");
          }}
        />
      )}

      {tab === "fp" && (
        <div className="space-y-6">
          <div className="card">
            <h2 className="mb-4 text-lg font-bold">تسجيل بصمة جديدة من النظام</h2>
            <p className="mb-3 text-sm text-slate-600">
              اختر الإصبع ثم اضغط «بدء التسجيل». سيصدر الجهاز صوتاً ويطلب وضع الإصبع
              ثلاث مرات — يجب أن يكون الموظف بجوار الجهاز.
            </p>
            <div className="flex flex-wrap items-end gap-3">
              <div className="w-48">
                <label>الإصبع</label>
                <select value={finger} onChange={(e) => setFinger(Number(e.target.value))}>
                  {Object.entries(FINGERS).map(([fid, name]) => (
                    <option key={fid} value={fid}>
                      {name}
                    </option>
                  ))}
                </select>
              </div>
              <button className="btn-primary" onClick={enroll}>
                بدء التسجيل
              </button>
            </div>
            {enrollState && (
              <div className="mt-4 rounded-lg bg-slate-50 px-4 py-3 font-semibold">
                {ENROLL_LABELS[enrollState]}
              </div>
            )}
          </div>
          <div className="card">
            <h2 className="mb-4 text-lg font-bold">البصمات المسجلة ({fps.length})</h2>
            {fps.length === 0 ? (
              <div className="text-slate-500">
                لا توجد بصمات محفوظة — سجّل بصمة من الأعلى أو من الجهاز مباشرة
              </div>
            ) : (
              <table className="data">
                <thead>
                  <tr>
                    <th>الإصبع</th>
                    <th>آخر تحديث</th>
                  </tr>
                </thead>
                <tbody>
                  {fps.map((f) => (
                    <tr key={f.id}>
                      <td>
                        {FINGERS[f.finger_id] ?? `إصبع ${f.finger_id}`} ({f.finger_id})
                      </td>
                      <td>{new Date(f.updated_at).toLocaleString("ar-EG")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {tab === "attendance" && (
        <div className="card">
          <h2 className="mb-4 text-lg font-bold">آخر البصمات</h2>
          {punches.length === 0 ? (
            <div className="text-slate-500">لا يوجد سجل حضور بعد</div>
          ) : (
            <table className="data">
              <thead>
                <tr>
                  <th>التاريخ والوقت</th>
                </tr>
              </thead>
              <tbody>
                {punches.map((p) => (
                  <tr key={p.id}>
                    <td>{new Date(p.timestamp).toLocaleString("ar-EG")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </Shell>
  );
}
