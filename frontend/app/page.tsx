"use client";

import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api } from "@/lib/api";

type Dashboard = {
  devices: {
    id: number;
    serial_number: string;
    name: string;
    last_seen: string | null;
    online: boolean;
  }[];
  employees_active: number;
  present_today: number;
  latest_punches: {
    id: number;
    employee_code: string;
    employee_name: string;
    timestamp: string;
  }[];
};

function fmt(ts: string | null) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString("ar-EG", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);

  useEffect(() => {
    let stop = false;
    const load = () => api("/api/dashboard/").then((d) => !stop && setData(d)).catch(() => {});
    load();
    const t = setInterval(load, 30000);
    return () => {
      stop = true;
      clearInterval(t);
    };
  }, []);

  return (
    <Shell>
      <h1 className="mb-6 text-2xl font-bold">لوحة التحكم</h1>
      {data && (
        <>
          <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="card">
              <div className="text-sm text-slate-500">الموظفون النشطون</div>
              <div className="mt-1 text-3xl font-bold">{data.employees_active}</div>
            </div>
            <div className="card">
              <div className="text-sm text-slate-500">حضور اليوم</div>
              <div className="mt-1 text-3xl font-bold text-emerald-600">
                {data.present_today}
              </div>
            </div>
            <div className="card">
              <div className="text-sm text-slate-500">حالة جهاز البصمة</div>
              {data.devices.length === 0 ? (
                <div className="mt-1 font-semibold text-amber-600">
                  لم يتصل أي جهاز بعد
                </div>
              ) : (
                data.devices.map((d) => (
                  <div key={d.id} className="mt-1 flex items-center gap-2">
                    <span
                      className={`inline-block h-3 w-3 rounded-full ${
                        d.online ? "bg-emerald-500" : "bg-red-500"
                      }`}
                    />
                    <span className="font-semibold">
                      {d.online ? "متصل" : "غير متصل"}
                    </span>
                    <span className="text-xs text-slate-400">({fmt(d.last_seen)})</span>
                  </div>
                ))
              )}
            </div>
          </div>
          <div className="card">
            <h2 className="mb-3 text-lg font-bold">آخر البصمات</h2>
            {data.latest_punches.length === 0 ? (
              <div className="text-slate-500">لا توجد بصمات مسجلة بعد</div>
            ) : (
              <table className="data">
                <thead>
                  <tr>
                    <th>الكود</th>
                    <th>الاسم</th>
                    <th>الوقت</th>
                  </tr>
                </thead>
                <tbody>
                  {data.latest_punches.map((p) => (
                    <tr key={p.id}>
                      <td>{p.employee_code}</td>
                      <td>{p.employee_name}</td>
                      <td>{fmt(p.timestamp)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </Shell>
  );
}
