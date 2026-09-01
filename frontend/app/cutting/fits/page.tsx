"use client";

// The cut catalogue. Renaming a cut here renames it on every model that uses
// it, which is why it stopped being free text on GarmentModel.

import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import CrudPage, { CrudConfig } from "@/lib/CrudPage";
import { api } from "@/lib/api";

type Fit = {
  id: number;
  name: string;
  notes: string;
  is_active: boolean;
  model_count: number;
};

const config: CrudConfig<Fit> = {
  title: "القَصّات",
  endpoint: "/api/cutting/fits/",
  searchPlaceholder: "ابحث عن قَصّة…",
  emptyText: "مفيش قَصّات مسجّلة",
  usageCount: (row) => row.model_count,
  usageLabel: "موديل",
  fields: [
    { name: "name", label: "القَصّة", required: true, placeholder: "سليم" },
    { name: "notes", label: "ملاحظات" },
  ],
  columns: [
    { label: "القَصّة", render: (r) => <span className="font-semibold">{r.name}</span> },
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
