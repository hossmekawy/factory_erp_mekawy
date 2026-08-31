"use client";

import { useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api, downloadFile, errorText } from "@/lib/api";

type DayCell = {
  date: string;
  status: "present" | "absent" | "future" | "not_hired" | "";
  in: string | null;
  out: string | null;
  hours: number;
};

type Report = {
  week_start: string;
  week_end: string;
  workdays: { date: string; name: string }[];
  schedule: { work_start: string; work_end: string };
  employees: {
    id: number;
    employee_code: string;
    full_name: string;
    department: string;
    days: Record<string, DayCell>;
    totals: { present: number; absent: number; hours: number };
  }[];
};

function shiftWeek(anchor: string, weeks: number): string {
  const d = new Date(anchor);
  d.setDate(d.getDate() + weeks * 7);
  return d.toISOString().slice(0, 10);
}

export default function WeeklyReportPage() {
  const [anchor, setAnchor] = useState(() => new Date().toISOString().slice(0, 10));
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");

  const load = useCallback((a: string) => {
    setError("");
    api(`/api/reports/weekly/?week=${a}`)
      .then(setReport)
      .catch((e) => setError(errorText(e)));
  }, []);

  useEffect(() => {
    load(anchor);
  }, [anchor, load]);

  return (
    <Shell>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">التقرير الأسبوعي</h1>
        <div className="flex flex-wrap items-center gap-2">
          <button className="btn-secondary" onClick={() => setAnchor(shiftWeek(anchor, -1))}>
            → الأسبوع السابق
          </button>
          <input
            type="date"
            className="!w-auto"
            value={anchor}
            onChange={(e) => e.target.value && setAnchor(e.target.value)}
          />
          <button className="btn-secondary" onClick={() => setAnchor(shiftWeek(anchor, 1))}>
            الأسبوع التالي ←
          </button>
          <button
            className="btn-secondary"
            onClick={() =>
              report &&
              downloadFile(
                `/api/reports/weekly/export/?week=${anchor}`,
                `تقرير-اسبوع-${report.week_start}.xlsx`
              )
            }
          >
            ⬇ Excel
          </button>
          <button
            className="btn-primary"
            onClick={() =>
              report &&
              downloadFile(
                `/api/reports/weekly/pdf/?week=${anchor}&size=a4`,
                `تقرير-اسبوع-${report.week_start}-A4.pdf`
              )
            }
          >
            ⬇ PDF (A4 بالصور)
          </button>
          <button
            className="btn-primary"
            onClick={() =>
              report &&
              downloadFile(
                `/api/reports/weekly/pdf/?week=${anchor}&size=a5`,
                `تقرير-اسبوع-${report.week_start}-A5.pdf`
              )
            }
          >
            ⬇ PDF (A5 مختصر)
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      {report && (
        <div className="card overflow-x-auto">
          <div className="mb-4 text-sm text-slate-600">
            من <b>{report.week_start}</b> إلى <b>{report.week_end}</b> — الدوام{" "}
            {report.schedule.work_start} إلى {report.schedule.work_end}، الجمعة إجازة
          </div>
          <table className="data min-w-[900px]">
            <thead>
              <tr>
                <th>الكود</th>
                <th>الاسم</th>
                {report.workdays.map((d) => (
                  <th key={d.date} className="text-center">
                    {d.name}
                    <div className="text-xs font-normal text-slate-300">
                      {d.date.slice(5)}
                    </div>
                  </th>
                ))}
                <th className="text-center">حضور</th>
                <th className="text-center">غياب</th>
                <th className="text-center">الساعات</th>
              </tr>
            </thead>
            <tbody>
              {report.employees.map((emp) => (
                <tr key={emp.id}>
                  <td>{emp.employee_code}</td>
                  <td className="whitespace-nowrap font-semibold">{emp.full_name}</td>
                  {report.workdays.map((d) => {
                    const cell = emp.days[d.date];
                    return (
                      <td key={d.date} className="text-center">
                        {cell.status === "present" ? (
                          <div className="rounded bg-emerald-50 px-1 py-0.5 text-emerald-800">
                            <div dir="ltr" className="text-xs font-semibold">
                              {cell.in}
                              {cell.out ? ` - ${cell.out}` : ""}
                            </div>
                            <div className="text-xs">
                              {cell.out ? `${cell.hours} ساعة` : "بصمة واحدة"}
                            </div>
                          </div>
                        ) : cell.status === "absent" ? (
                          <span className="rounded bg-red-50 px-2 py-0.5 text-xs font-semibold text-red-700">
                            غياب
                          </span>
                        ) : (
                          <span className="text-slate-300">—</span>
                        )}
                      </td>
                    );
                  })}
                  <td className="text-center font-bold text-emerald-700">
                    {emp.totals.present}
                  </td>
                  <td className="text-center font-bold text-red-600">{emp.totals.absent}</td>
                  <td className="text-center font-bold">{emp.totals.hours}</td>
                </tr>
              ))}
              {report.employees.length === 0 && (
                <tr>
                  <td
                    colSpan={report.workdays.length + 5}
                    className="py-8 text-center text-slate-500"
                  >
                    لا يوجد موظفون نشطون
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </Shell>
  );
}
