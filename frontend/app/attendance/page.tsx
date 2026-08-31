"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api } from "@/lib/api";

type Log = {
  id: number;
  employee_code: string;
  employee_name: string;
  local_time: string;
  verify_type: number;
};

export default function AttendancePage() {
  const [rows, setRows] = useState<Log[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  useEffect(() => {
    const params = new URLSearchParams({ page: String(page) });
    if (search) params.set("search", search);
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    const t = setTimeout(() => {
      api(`/api/attendance/?${params}`)
        .then((d) => {
          setRows(d.results);
          setCount(d.count);
        })
        .catch(() => {});
    }, 300);
    return () => clearTimeout(t);
  }, [page, search, dateFrom, dateTo]);

  const pages = Math.max(1, Math.ceil(count / 50));

  return (
    <Shell>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">سجل الحضور ({count})</h1>
        <Link href="/attendance/manual" className="btn-primary">
          ✍️ تسجيل حضور يدوي
        </Link>
      </div>
      <div className="card">
        <div className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-3">
          <div>
            <label>بحث (اسم أو كود)</label>
            <input
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
            />
          </div>
          <div>
            <label>من تاريخ</label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => {
                setDateFrom(e.target.value);
                setPage(1);
              }}
            />
          </div>
          <div>
            <label>إلى تاريخ</label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => {
                setDateTo(e.target.value);
                setPage(1);
              }}
            />
          </div>
        </div>
        <div className="overflow-x-auto">
        <table className="data min-w-[480px]">
          <thead>
            <tr>
              <th>الكود</th>
              <th>الاسم</th>
              <th>التاريخ والوقت</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.employee_code}</td>
                <td>{r.employee_name || "—"}</td>
                <td>{new Date(r.local_time).toLocaleString("ar-EG")}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={3} className="py-8 text-center text-slate-500">
                  لا توجد سجلات
                </td>
              </tr>
            )}
          </tbody>
        </table>
        </div>
        {pages > 1 && (
          <div className="mt-4 flex items-center justify-center gap-2">
            <button
              className="btn-secondary"
              disabled={page <= 1}
              onClick={() => setPage(page - 1)}
            >
              السابق
            </button>
            <span className="text-sm text-slate-600">
              صفحة {page} من {pages}
            </span>
            <button
              className="btn-secondary"
              disabled={page >= pages}
              onClick={() => setPage(page + 1)}
            >
              التالي
            </button>
          </div>
        )}
      </div>
    </Shell>
  );
}
