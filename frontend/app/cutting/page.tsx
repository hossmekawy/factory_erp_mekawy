"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import Shell from "@/components/Shell";
import { api } from "@/lib/api";

type Row = {
  id: number;
  code: string;
  model_name: string;
  color: string;
  production_order_no: string;
  cutting_date: string;
  created_by_name: string;
  rolls_count: number;
  total_meters: number | null;
  has_shortage: boolean;
};

export default function CuttingListPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState({ code: "", model_name: "", color: "", date_from: "", date_to: "" });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const t = setTimeout(() => {
      const qs = new URLSearchParams({ page: String(page) });
      for (const [k, v] of Object.entries(filters)) if (v) qs.set(k, v);
      api(`/api/cuttings/?${qs}`)
        .then((d) => {
          setRows(d.results);
          setCount(d.count);
        })
        .catch(() => {})
        .finally(() => setLoading(false));
    }, 300);
    return () => clearTimeout(t);
  }, [filters, page]);

  const pages = Math.max(1, Math.ceil(count / 50));

  function setF(k: string, v: string) {
    setPage(1);
    setFilters((f) => ({ ...f, [k]: v }));
  }

  return (
    <Shell>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">مرحلة القص</h1>
        <Link href="/cutting/new" className="btn-primary">
          <Plus className="h-4 w-4" /> قصة جديدة
        </Link>
      </div>

      <div className="card mb-4">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <div>
            <label>الكود</label>
            <input value={filters.code} onChange={(e) => setF("code", e.target.value)} />
          </div>
          <div>
            <label>الموديل</label>
            <input value={filters.model_name} onChange={(e) => setF("model_name", e.target.value)} />
          </div>
          <div>
            <label>اللون</label>
            <input value={filters.color} onChange={(e) => setF("color", e.target.value)} />
          </div>
          <div>
            <label>من تاريخ</label>
            <input type="date" value={filters.date_from} onChange={(e) => setF("date_from", e.target.value)} />
          </div>
          <div>
            <label>إلى تاريخ</label>
            <input type="date" value={filters.date_to} onChange={(e) => setF("date_to", e.target.value)} />
          </div>
        </div>
      </div>

      {/* Mobile: cards instead of a wide table */}
      <div className="space-y-3 md:hidden">
        {loading ? (
          <div className="card py-8 text-center text-slate-400">جارٍ التحميل…</div>
        ) : rows.length === 0 ? (
          <div className="card py-8 text-center text-slate-400">لا توجد قصات</div>
        ) : (
          rows.map((r) => (
            <Link key={r.id} href={`/cutting/${r.id}`} className="card block">
              <div className="mb-1 flex items-center justify-between">
                <span className="font-bold text-red-700">{r.code}</span>
                <span className="text-xs text-slate-500" dir="ltr">{r.cutting_date}</span>
              </div>
              <div className="text-sm text-slate-700">
                {r.model_name}
                {r.color && <span className="text-slate-400"> — {r.color}</span>}
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
                <span>👷 {r.created_by_name}</span>
                <span>🧵 {r.rolls_count} توب</span>
                <span>📏 {r.total_meters ?? "—"} م</span>
                {r.production_order_no && <span>أمر: {r.production_order_no}</span>}
                {r.has_shortage && <span className="font-bold text-red-600">⚠️ عجز</span>}
              </div>
            </Link>
          ))
        )}
      </div>

      {/* Desktop: full table */}
      <div className="card hidden overflow-x-auto p-0 md:block">
        <table className="data min-w-[720px]">
          <thead>
            <tr>
              <th>الكود</th>
              <th>الموديل</th>
              <th>اللون</th>
              <th>أمر الإنتاج</th>
              <th>التاريخ</th>
              <th>موظف القص</th>
              <th>الأتواب</th>
              <th>الأمتار</th>
              <th>عجز</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={9} className="py-8 text-center text-slate-400">جارٍ التحميل…</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={9} className="py-8 text-center text-slate-400">لا توجد قصات</td></tr>
            ) : (
              rows.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link href={`/cutting/${r.id}`} className="font-bold text-red-700 hover:underline">
                      {r.code}
                    </Link>
                  </td>
                  <td>{r.model_name}</td>
                  <td>{r.color || "—"}</td>
                  <td>{r.production_order_no || "—"}</td>
                  <td dir="ltr">{r.cutting_date}</td>
                  <td>{r.created_by_name}</td>
                  <td>{r.rolls_count}</td>
                  <td>{r.total_meters ?? "—"}</td>
                  <td>{r.has_shortage ? <span className="font-bold text-red-600">نعم</span> : "لا"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {pages > 1 && (
        <div className="mt-4 flex items-center justify-center gap-3">
          <button className="btn-secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>السابق</button>
          <span className="text-sm text-slate-600">{page} / {pages}</span>
          <button className="btn-secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>التالي</button>
        </div>
      )}
    </Shell>
  );
}
