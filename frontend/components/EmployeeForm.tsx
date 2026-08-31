"use client";

import { useEffect, useState } from "react";
import { api, errorText } from "@/lib/api";

export type EmployeeData = {
  id?: number;
  employee_code: string;
  full_name: string;
  department: number | null;
  job_title: string;
  national_id: string;
  phone_number: string;
  address: string;
  gender: string;
  birth_date: string | null;
  hire_date: string | null;
  salary: string | null;
  photo?: string | null;
  id_front_image?: string | null;
  id_back_image?: string | null;
  is_active: boolean;
};

const EMPTY: EmployeeData = {
  employee_code: "",
  full_name: "",
  department: null,
  job_title: "",
  national_id: "",
  phone_number: "",
  address: "",
  gender: "male",
  birth_date: null,
  hire_date: null,
  salary: null,
  is_active: true,
};

function ImageField({
  label,
  current,
  onChange,
}: {
  label: string;
  current?: string | null;
  onChange: (f: File | null) => void;
}) {
  const [preview, setPreview] = useState<string | null>(null);
  return (
    <div>
      <label>{label}</label>
      {(preview || current) && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={preview ?? current ?? ""}
          alt={label}
          className="mb-2 h-32 w-full rounded-lg border border-slate-200 object-contain bg-slate-50"
        />
      )}
      <input
        type="file"
        accept="image/*"
        onChange={(e) => {
          const f = e.target.files?.[0] ?? null;
          onChange(f);
          setPreview(f ? URL.createObjectURL(f) : null);
        }}
      />
    </div>
  );
}

export default function EmployeeForm({
  initial,
  onSaved,
}: {
  initial?: EmployeeData;
  onSaved: (emp: EmployeeData) => void;
}) {
  const [form, setForm] = useState<EmployeeData>(initial ?? EMPTY);
  const [departments, setDepartments] = useState<{ id: number; name: string }[]>([]);
  const [files, setFiles] = useState<Record<string, File | null>>({});
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [newDept, setNewDept] = useState("");

  useEffect(() => {
    api("/api/departments/").then(setDepartments).catch(() => {});
  }, []);

  function set<K extends keyof EmployeeData>(key: K, value: EmployeeData[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function addDepartment() {
    if (!newDept.trim()) return;
    try {
      const d = await api("/api/departments/", {
        method: "POST",
        body: JSON.stringify({ name: newDept.trim() }),
      });
      setDepartments((ds) => [...ds, d]);
      set("department", d.id);
      setNewDept("");
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");
    const fd = new FormData();
    const fields: (keyof EmployeeData)[] = [
      "employee_code", "full_name", "job_title", "national_id",
      "phone_number", "address", "gender",
    ];
    fields.forEach((k) => fd.append(k, String(form[k] ?? "")));
    fd.append("is_active", form.is_active ? "true" : "false");
    if (form.department) fd.append("department", String(form.department));
    if (form.birth_date) fd.append("birth_date", form.birth_date);
    if (form.hire_date) fd.append("hire_date", form.hire_date);
    if (form.salary) fd.append("salary", String(form.salary));
    for (const [k, f] of Object.entries(files)) {
      if (f) fd.append(k, f);
    }
    try {
      const saved = form.id
        ? await api(`/api/employees/${form.id}/`, { method: "PATCH", body: fd })
        : await api("/api/employees/", { method: "POST", body: fd });
      onSaved(saved);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-6">
      {error && (
        <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}
      <div className="card">
        <h2 className="mb-4 text-lg font-bold">البيانات الأساسية</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div>
            <label>كود الموظف (رقمه على جهاز البصمة) *</label>
            <input
              value={form.employee_code}
              onChange={(e) => set("employee_code", e.target.value)}
              required
              dir="ltr"
            />
          </div>
          <div className="md:col-span-2">
            <label>الاسم بالكامل *</label>
            <input
              value={form.full_name}
              onChange={(e) => set("full_name", e.target.value)}
              required
            />
          </div>
          <div>
            <label>القسم</label>
            <select
              value={form.department ?? ""}
              onChange={(e) => set("department", e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">— بدون قسم —</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
            <div className="mt-2 flex gap-2">
              <input
                placeholder="قسم جديد…"
                value={newDept}
                onChange={(e) => setNewDept(e.target.value)}
              />
              <button type="button" className="btn-secondary" onClick={addDepartment}>
                إضافة
              </button>
            </div>
          </div>
          <div>
            <label>المسمى الوظيفي</label>
            <input value={form.job_title} onChange={(e) => set("job_title", e.target.value)} />
          </div>
          <div>
            <label>الجنس</label>
            <select value={form.gender} onChange={(e) => set("gender", e.target.value)}>
              <option value="male">ذكر</option>
              <option value="female">أنثى</option>
            </select>
          </div>
          <div>
            <label>تاريخ التعيين</label>
            <input
              type="date"
              value={form.hire_date ?? ""}
              onChange={(e) => set("hire_date", e.target.value || null)}
            />
          </div>
          <div>
            <label>الراتب (اختياري)</label>
            <input
              type="number"
              step="0.01"
              value={form.salary ?? ""}
              onChange={(e) => set("salary", e.target.value || null)}
              dir="ltr"
            />
          </div>
          <div>
            <label>الحالة</label>
            <select
              value={form.is_active ? "1" : "0"}
              onChange={(e) => set("is_active", e.target.value === "1")}
            >
              <option value="1">نشط</option>
              <option value="0">موقوف</option>
            </select>
          </div>
        </div>
      </div>

      <div className="card">
        <h2 className="mb-4 text-lg font-bold">بيانات البطاقة والاتصال</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div>
            <label>الرقم القومي</label>
            <input
              value={form.national_id}
              onChange={(e) => set("national_id", e.target.value)}
              maxLength={14}
              dir="ltr"
            />
          </div>
          <div>
            <label>رقم الهاتف</label>
            <input
              value={form.phone_number}
              onChange={(e) => set("phone_number", e.target.value)}
              dir="ltr"
            />
          </div>
          <div>
            <label>تاريخ الميلاد</label>
            <input
              type="date"
              value={form.birth_date ?? ""}
              onChange={(e) => set("birth_date", e.target.value || null)}
            />
          </div>
          <div className="md:col-span-3">
            <label>العنوان</label>
            <textarea
              rows={2}
              value={form.address}
              onChange={(e) => set("address", e.target.value)}
            />
          </div>
        </div>
      </div>

      <div className="card">
        <h2 className="mb-4 text-lg font-bold">الصور</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <ImageField
            label="صورة الموظف"
            current={form.photo}
            onChange={(f) => setFiles((s) => ({ ...s, photo: f }))}
          />
          <ImageField
            label="صورة وجه البطاقة"
            current={form.id_front_image}
            onChange={(f) => setFiles((s) => ({ ...s, id_front_image: f }))}
          />
          <ImageField
            label="صورة ظهر البطاقة"
            current={form.id_back_image}
            onChange={(f) => setFiles((s) => ({ ...s, id_back_image: f }))}
          />
        </div>
      </div>

      <button className="btn-primary" disabled={saving}>
        {saving ? "جارٍ الحفظ…" : "حفظ البيانات"}
      </button>
    </form>
  );
}
