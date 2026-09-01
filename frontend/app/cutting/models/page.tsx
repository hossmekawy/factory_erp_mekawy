"use client";

// The model catalogue. The code is unique — the database refuses a duplicate
// and the dialog shows why — and a model any lay points at cannot be deleted.

import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import CrudPage, { CrudConfig, Field } from "@/lib/CrudPage";
import { api } from "@/lib/api";

type GarmentModel = {
  id: number;
  code: string;
  name: string;
  category: string;
  category_label: string;
  fit: number | null;
  fit_name: string;
  default_size_set: number | null;
  notes: string;
  is_active: boolean;
  lay_count: number;
};

export default function Page() {
  const [role, setRole] = useState("");
  const [fits, setFits] = useState<{ value: string; label: string }[]>([]);
  const [sizeSets, setSizeSets] = useState<{ value: string; label: string }[]>([]);

  useEffect(() => {
    api("/api/me/").then((d) => setRole(d.role)).catch(() => {});
    api("/api/cutting/fits/?page_size=200")
      .then((d) =>
        setFits((d.results ?? d).map((f: any) => ({ value: String(f.id), label: f.name })))
      )
      .catch(() => {});
    api("/api/cutting/size-sets/?page_size=200")
      .then((d) =>
        setSizeSets(
          (d.results ?? d).map((s: any) => ({
            value: String(s.id),
            label: `${s.name} (${s.sizes_raw})`,
          }))
        )
      )
      .catch(() => {});
  }, []);

  const fields: Field[] = [
    {
      name: "code",
      label: "الكود",
      required: true,
      ltr: true,
      placeholder: "1749",
      hint: "مينفعش يتكرر",
    },
    { name: "name", label: "اسم الموديل", required: true, placeholder: "karl" },
    {
      name: "category",
      label: "الفئة",
      kind: "select",
      options: [
        { value: "men", label: "رجالي" },
        { value: "women", label: "حريمي" },
        { value: "kids", label: "أطفال" },
      ],
    },
    { name: "fit", label: "القَصّة", kind: "select", options: fits, nullable: true },
    {
      name: "default_size_set",
      label: "طقم المقاسات المعتاد",
      kind: "select",
      options: sizeSets,
      nullable: true,
    },
    { name: "notes", label: "ملاحظات" },
  ];

  const config: CrudConfig<GarmentModel> = {
    title: "الموديلات",
    endpoint: "/api/cutting/models/",
    searchPlaceholder: "ابحث بالكود أو الاسم…",
    emptyText: "مفيش موديلات مسجّلة",
    usageCount: (row) => row.lay_count,
    usageLabel: "فرشة",
    fields,
    columns: [
      {
        label: "الكود",
        ltr: true,
        render: (r) => <span className="font-semibold">{r.code}</span>,
      },
      { label: "الموديل", render: (r) => r.name },
      { label: "القَصّة", render: (r) => r.fit_name || "—" },
      { label: "الفئة", render: (r) => r.category_label || "—" },
      {
        label: "الفرشات",
        ltr: true,
        render: (r) => (
          <span className={r.lay_count ? "" : "text-slate-400"}>{r.lay_count}</span>
        ),
      },
    ],
  };

  return (
    <Shell>
      <CrudPage config={config} canDelete={role === "admin"} />
    </Shell>
  );
}
