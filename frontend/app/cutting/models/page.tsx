"use client";

// The model catalogue. Models are identified by NAME ("كارل رجالي") — the
// number in the notebook belongs to the cutting run, not to the model, so the
// code here is generated and shown but never typed. Every model carries a
// section, and one any lay points at cannot be deleted.

import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import CrudPage, { CrudConfig, Field } from "@/lib/CrudPage";
import { api } from "@/lib/api";

type GarmentModel = {
  id: number;
  code: string;
  name: string;
  category: number | null;
  category_label: string;
  default_size_set: number | null;
  notes: string;
  is_active: boolean;
  lay_count: number;
};

export default function Page() {
  const [role, setRole] = useState("");
  const [categories, setCategories] = useState<{ value: string; label: string }[]>([]);
  const [sizeSets, setSizeSets] = useState<{ value: string; label: string }[]>([]);

  useEffect(() => {
    api("/api/me/").then((d) => setRole(d.role)).catch(() => {});
    api("/api/cutting/categories/?page_size=200")
      .then((d) =>
        setCategories(
          (d.results ?? d).map((c: any) => ({ value: String(c.id), label: c.name }))
        )
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
      name: "name",
      label: "اسم الموديل",
      required: true,
      placeholder: "كارل رجالي",
      hint: "ده اللي هتدوّر بيه بعدين",
    },
    {
      name: "category",
      label: "القسم",
      kind: "select",
      options: categories,
      required: true,
      hint: "مطلوب — عليه بتتبني الفلاتر والتقارير",
    },
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
      { label: "الموديل", render: (r) => <span className="font-semibold">{r.name}</span> },
      { label: "القسم", render: (r) => r.category_label || "—" },
      {
        label: "الكود",
        ltr: true,
        render: (r) => <span className="text-slate-400">{r.code}</span>,
      },
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
