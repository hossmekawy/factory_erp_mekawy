"use client";

// The sections the factory sorts its models into — رجالي · حريمي · مواليد ·
// رجالي جامبو … Renaming one here renames it on every model that carries it,
// and every model must carry one: it is the axis the reports are read along.

import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import CrudPage, { CrudConfig } from "@/lib/CrudPage";
import { api } from "@/lib/api";

type Category = {
  id: number;
  name: string;
  notes: string;
  order: number;
  is_active: boolean;
  model_count: number;
};

const config: CrudConfig<Category> = {
  title: "الأقسام",
  endpoint: "/api/cutting/categories/",
  searchPlaceholder: "ابحث عن قسم…",
  emptyText: "مفيش أقسام مسجّلة",
  usageCount: (row) => row.model_count,
  usageLabel: "موديل",
  fields: [
    { name: "name", label: "القسم", required: true, placeholder: "رجالي خاص" },
    { name: "order", label: "الترتيب", kind: "number", ltr: true,
      hint: "الأصغر بيظهر الأول في القوايم" },
    { name: "notes", label: "ملاحظات" },
  ],
  columns: [
    { label: "القسم", render: (r) => <span className="font-semibold">{r.name}</span> },
    { label: "ملاحظات", render: (r) => r.notes || "—" },
    {
      label: "الموديلات",
      ltr: true,
      render: (r) => (
        <span className={r.model_count ? "" : "text-slate-400"}>{r.model_count}</span>
      ),
    },
  ],
};

export default function Page() {
  const [role, setRole] = useState("");
  useEffect(() => {
    api("/api/me/").then((d) => setRole(d.role)).catch(() => {});
  }, []);
  return (
    <Shell>
      <CrudPage config={config} canDelete={role === "admin"} />
    </Shell>
  );
}
