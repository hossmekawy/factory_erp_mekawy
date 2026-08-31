"use client";

import { useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api, errorText } from "@/lib/api";

type Device = {
  id: number;
  serial_number: string;
  name: string;
  last_seen: string | null;
  push_version: string;
  online: boolean;
  pending_commands: number;
};

type Command = {
  id: number;
  description: string;
  command: string;
  status: string;
  created_at: string;
  finished_at: string | null;
};

const STATUS_AR: Record<string, string> = {
  pending: "قيد الانتظار",
  sent: "أُرسل للجهاز",
  done: "تم ✅",
  failed: "فشل ❌",
};

export default function DevicesPage() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [commands, setCommands] = useState<Command[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [msg, setMsg] = useState("");
  const [role, setRole] = useState("");

  useEffect(() => {
    api("/api/dashboard/").then((d) => setRole(d.me.role)).catch(() => {});
  }, []);

  const load = useCallback(() => {
    api("/api/devices/")
      .then((ds: Device[]) => {
        setDevices(ds);
        if (ds.length && selected === null) setSelected(ds[0].id);
      })
      .catch(() => {});
  }, [selected]);

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    if (selected === null) return;
    const loadCmds = () =>
      api(`/api/devices/${selected}/commands/`).then(setCommands).catch(() => {});
    loadCmds();
    const t = setInterval(loadCmds, 10000);
    return () => clearInterval(t);
  }, [selected]);

  async function act(id: number, action: "sync" | "reboot") {
    setMsg("");
    if (action === "reboot" && !confirm("إعادة تشغيل الجهاز؟")) return;
    try {
      await api(`/api/devices/${id}/${action}/`, { method: "POST" });
      setMsg("تم إرسال الأمر — سينفذه الجهاز في الاتصال القادم");
    } catch (e) {
      setMsg(errorText(e));
    }
  }

  async function wipe(id: number) {
    setMsg("");
    if (
      !confirm(
        "⚠️ مسح شامل: سيتم حذف كل الموظفين والبصمات وسجلات الحضور من قاعدة البيانات ومن جهاز البصمة نفسه، والبدء من جديد.\n\nهذا الإجراء لا يمكن التراجع عنه. هل أنت متأكد؟"
      )
    )
      return;
    if (prompt('للتأكيد النهائي اكتب كلمة "مسح" ثم اضغط موافق:') !== "مسح") {
      setMsg("تم إلغاء المسح");
      return;
    }
    try {
      const res = await api(`/api/devices/${id}/wipe/`, { method: "POST" });
      const r = res.removed;
      setMsg(
        `تم مسح قاعدة البيانات (${r.employees} موظف، ${r.fingerprints} بصمة، ${r.attendance} سجل حضور). ` +
          "أمر مسح الجهاز أُرسل — سيُنفَّذ خلال ثوانٍ عند اتصال الجهاز."
      );
      load();
    } catch (e) {
      setMsg(errorText(e));
    }
  }

  return (
    <Shell>
      <h1 className="mb-6 text-2xl font-bold">أجهزة البصمة</h1>
      {msg && (
        <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800">{msg}</div>
      )}
      {devices.length === 0 && (
        <div className="card text-slate-600">
          <p className="mb-2 font-bold">لم يتصل أي جهاز بعد.</p>
          <p className="text-sm leading-7">
            على شاشة جهاز البصمة: القائمة ← الاتصال (Comm.) ← إعداد الخادم السحابي (Cloud
            Server Setting) ثم اضبط:
            <br />• عنوان الخادم (Server Address): <b dir="ltr">167.86.71.246</b>
            <br />• المنفذ (Server Port): <b dir="ltr">8090</b>
            <br />• Enable Domain Name: <b>OFF</b> — HTTPS: <b>OFF</b>
            <br />
            ثم أعد تشغيل الجهاز وسيظهر هنا تلقائياً خلال دقيقة.
          </p>
        </div>
      )}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {devices.map((d) => (
          <div key={d.id} className="card">
            <div className="mb-2 flex items-center justify-between">
              <div className="text-lg font-bold">{d.name || "جهاز بصمة"}</div>
              <span
                className={`rounded-full px-3 py-1 text-xs font-bold ${
                  d.online
                    ? "bg-emerald-100 text-emerald-700"
                    : "bg-red-100 text-red-700"
                }`}
              >
                {d.online ? "● متصل" : "● غير متصل"}
              </span>
            </div>
            <div className="space-y-1 text-sm text-slate-600">
              <div>
                الرقم التسلسلي: <b dir="ltr">{d.serial_number}</b>
              </div>
              <div>
                آخر اتصال:{" "}
                {d.last_seen ? new Date(d.last_seen).toLocaleString("ar-EG") : "—"}
              </div>
              <div>أوامر قيد التنفيذ: {d.pending_commands}</div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <button className="btn-secondary" onClick={() => act(d.id, "sync")}>
                🔄 مزامنة البيانات
              </button>
              <button className="btn-secondary" onClick={() => act(d.id, "reboot")}>
                إعادة تشغيل
              </button>
              {role === "admin" && (
                <button className="btn-danger" onClick={() => wipe(d.id)}>
                  🗑 مسح شامل (جهاز + قاعدة بيانات)
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {selected !== null && commands.length > 0 && (
        <div className="card mt-6 overflow-x-auto">
          <h2 className="mb-3 text-lg font-bold">آخر الأوامر</h2>
          <table className="data min-w-[500px]">
            <thead>
              <tr>
                <th>الوصف</th>
                <th>الحالة</th>
                <th>أُنشئ</th>
              </tr>
            </thead>
            <tbody>
              {commands.map((c) => (
                <tr key={c.id}>
                  <td>{c.description || c.command.slice(0, 60)}</td>
                  <td>{STATUS_AR[c.status] ?? c.status}</td>
                  <td>{new Date(c.created_at).toLocaleString("ar-EG")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Shell>
  );
}
