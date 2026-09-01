"use client";

// Saved size runs. The same runs come up again and again — "رجالي: 30 32 34 36
// 38" — and typing them size by size every time is the slowest part of the
// new-lay screen. Attaching a section makes the presets for the model's own
// section sort first there.
//
// Only presets are listed. Typing sizes by hand on a lay also lands a SizeSet
// row (that is how the breakdown gets its snapshot) and those are not offered
// back to anyone.

import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import CrudPage, { CrudConfig, Field } from "@/lib/CrudPage";
import { api } from "@/lib/api";

type SizeSet = {
  id: number;
  name: string;
  sizes_raw: string;
  total_pieces: number;
  category: number | null;
  category_label: string;
  is_active: boolean;
};

export default function Page() {
  const [role, setRole] = useState("");
  const [categories, setCategories] = useState<{ value: string; label: string }[]>([]);

  useEffect(() => {
    api("/api/me/").then((d) => setRole(d.role)).catch(() => {});
    api("/api/cutting/categories/?page_size=200")
      .then((d) =>
        setCategories(
          (d.results ?? d).map((c: any) => ({ value: String(c.id), label: c.name }))
        )
      )
      .catch(() => {});
  }, []);

  const fields: Field[] = [
    {
      name: "name",
      label: "اسم الطقم",
      required: true,
      placeholder: "رجالي عادي",
      hint: "ده اللي هيظهر على الزرار في شاشة القصة",
    },
    {
      name: "sizes_raw",
      label: "المقاسات",
      required: true,
      ltr: true,
      placeholder: "30 32 34 36 38",
      hint: "بمسافات — عدد القطع بيتحسب لوحده",
    },
    {
      name: "category",
      label: "القسم",
      kind: "select",
      options: categories,
      nullable: true,
      hint: "الأطقم بتاعة قسم الموديل بتظهر الأول",
    },
  ];

  const config: CrudConfig<SizeSet> = {
    title: "أطقم المقاسات",
    // Only the saved ones; the rest are leftovers from hand-typed lays.
    endpoint: "/api/cutting/size-sets/?is_preset=true&",
    searchPlaceholder: "ابحث بالاسم أو المقاسات…",
    emptyText: "مفيش أطقم محفوظة — ضيف واحد وهيظهر كزرار في شاشة القصة",
    fields,
    columns: [
      { label: "الطقم", render: (r) => <span className="font-semibold">{r.name}</span> },
      {
        label: "المقاسات",
        ltr: true,
        render: (r) => <span className="text-slate-600">{r.sizes_raw}</span>,
      },
      { label: "عدد القطع", ltr: true, render: (r) => r.total_pieces },
      { label: "القسم", render: (r) => r.category_label || "عام" },
    ],
  };

  return (
    <Shell>
      <CrudPage config={config} canDelete={role === "admin"} />
    </Shell>
  );
}
