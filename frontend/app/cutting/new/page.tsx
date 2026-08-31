"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import Shell from "@/components/Shell";
import { api, errorText } from "@/lib/api";

export default function NewCuttingPage() {
  const router = useRouter();
  const [msg, setMsg] = useState("");
  const [saving, setSaving] = useState(false);
  const [photo, setPhoto] = useState<File | null>(null);
  const [form, setForm] = useState({
    code: "",
    model_name: "",
    color: "",
    production_order_no: "",
    cutting_date: new Date().toISOString().slice(0, 10),
  });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMsg("");
    try {
      const body = new FormData();
      for (const [k, v] of Object.entries(form)) body.append(k, v);
      if (photo) body.append("worksheet_photo", photo);
      const d = await api("/api/cuttings/", { method: "POST", body });
      router.replace(`/cutting/${d.id}`);
    } catch (err) {
      setMsg(errorText(err));
      setSaving(false);
    }
  }

  return (
    <Shell>
      <h1 className="mb-6 text-2xl font-bold">قصة جديدة</h1>
      <form onSubmit={submit} className="card max-w-2xl space-y-4">
        {msg && <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800">{msg}</div>}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label>كود القصة *</label>
            <input
              value={form.code}
              onChange={(e) => setForm({ ...form, code: e.target.value })}
              required
              autoFocus
            />
          </div>
          <div>
            <label>اسم الموديل *</label>
            <input
              value={form.model_name}
              onChange={(e) => setForm({ ...form, model_name: e.target.value })}
              required
            />
          </div>
          <div>
            <label>اللون</label>
            <input value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value })} />
          </div>
          <div>
            <label>رقم أمر الإنتاج</label>
            <input
              value={form.production_order_no}
              onChange={(e) => setForm({ ...form, production_order_no: e.target.value })}
            />
          </div>
          <div>
            <label>تاريخ القص</label>
            <input
              type="date"
              value={form.cutting_date}
              onChange={(e) => setForm({ ...form, cutting_date: e.target.value })}
            />
          </div>
          <div>
            <label>صورة ورقة القصة (اختياري)</label>
            <input type="file" accept="image/*" onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} />
          </div>
        </div>
        <button className="btn-primary w-full sm:w-auto" disabled={saving}>
          {saving ? "جارٍ الحفظ…" : "إنشاء القصة والمتابعة"}
        </button>
      </form>
    </Shell>
  );
}
