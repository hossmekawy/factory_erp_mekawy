"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api } from "@/lib/api";

type Employee = {
  id: number;
  employee_code: string;
  full_name: string;
  department_name: string;
  job_title: string;
  phone_number: string;
  photo: string | null;
  is_active: boolean;
  fingerprint_count: number;
};

export default function EmployeesPage() {
  const [rows, setRows] = useState<Employee[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");

  useEffect(() => {
    const t = setTimeout(() => {
      api(`/api/employees/?page=${page}&search=${encodeURIComponent(search)}`)
        .then((d) => {
          setRows(d.results);
          setCount(d.count);
        })
        .catch(() => {});
    }, 300);
    return () => clearTimeout(t);
  }, [page, search]);

  const pages = Math.max(1, Math.ceil(count / 50));

  return (
    <Shell>
      <div className="mb-6 flex items-center justify-between gap-4">
        <h1 className="text-2xl font-bold">الموظفون ({count})</h1>
        <Link href="/employees/new" className="btn-primary">
          + إضافة موظف
        </Link>
      </div>
      <div className="card">
        <input
          placeholder="بحث بالاسم أو الكود أو الرقم القومي أو الهاتف…"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          className="mb-4"
        />
        <div className="overflow-x-auto">
        <table className="data min-w-[720px]">
          <thead>
            <tr>
              <th>الصورة</th>
              <th>الكود</th>
              <th>الاسم</th>
              <th>القسم</th>
              <th>الوظيفة</th>
              <th>الهاتف</th>
              <th>البصمات</th>
              <th>الحالة</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((e) => (
              <tr key={e.id}>
                <td>
                  {e.photo ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={e.photo}
                      alt=""
                      className="h-10 w-10 rounded-full object-cover"
                    />
                  ) : (
                    <span className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-200 text-slate-500">
                      👤
                    </span>
                  )}
                </td>
                <td>{e.employee_code}</td>
                <td>
                  <Link
                    href={`/employees/${e.id}`}
                    className="font-semibold text-red-700 hover:underline"
                  >
                    {e.full_name}
                  </Link>
                </td>
                <td>{e.department_name || "—"}</td>
                <td>{e.job_title || "—"}</td>
                <td dir="ltr">{e.phone_number || "—"}</td>
                <td>{e.fingerprint_count > 0 ? `${e.fingerprint_count} ✔` : "لا يوجد"}</td>
                <td>
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                      e.is_active
                        ? "bg-emerald-100 text-emerald-700"
                        : "bg-red-100 text-red-700"
                    }`}
                  >
                    {e.is_active ? "نشط" : "موقوف"}
                  </span>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={8} className="py-8 text-center text-slate-500">
                  لا يوجد موظفون — أضف موظفاً أو انتظر مزامنة الجهاز
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
