"use client";

import { useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api, errorText } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/roles";

type SystemUser = {
  id: number;
  username: string;
  first_name: string;
  is_active: boolean;
  role: string;
};

export default function UsersPage() {
  const [users, setUsers] = useState<SystemUser[]>([]);
  const [msg, setMsg] = useState("");
  const [form, setForm] = useState({
    username: "",
    first_name: "",
    password: "",
    role_input: "hr",
  });

  const load = useCallback(() => {
    api("/api/users/").then(setUsers).catch(() => {});
  }, []);

  useEffect(load, [load]);

  async function createUser(e: React.FormEvent) {
    e.preventDefault();
    setMsg("");
    try {
      await api("/api/users/", { method: "POST", body: JSON.stringify(form) });
      setForm({ username: "", first_name: "", password: "", role_input: "hr" });
      setMsg("تم إنشاء المستخدم بنجاح");
      load();
    } catch (err) {
      setMsg(errorText(err));
    }
  }

  async function resetPassword(u: SystemUser) {
    const pw = prompt(`كلمة مرور جديدة للمستخدم ${u.username}:`);
    if (!pw) return;
    try {
      await api(`/api/users/${u.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ password: pw }),
      });
      setMsg("تم تغيير كلمة المرور");
    } catch (err) {
      setMsg(errorText(err));
    }
  }

  async function toggleActive(u: SystemUser) {
    try {
      await api(`/api/users/${u.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !u.is_active }),
      });
      load();
    } catch (err) {
      setMsg(errorText(err));
    }
  }

  return (
    <Shell>
      <h1 className="mb-6 text-2xl font-bold">مستخدمو النظام</h1>
      {msg && (
        <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800">{msg}</div>
      )}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="card">
          <h2 className="mb-4 text-lg font-bold">إضافة مستخدم جديد</h2>
          <form onSubmit={createUser} className="space-y-4">
            <div>
              <label>اسم المستخدم *</label>
              <input
                value={form.username}
                onChange={(e) => setForm({ ...form, username: e.target.value })}
                required
                dir="ltr"
              />
            </div>
            <div>
              <label>الاسم</label>
              <input
                value={form.first_name}
                onChange={(e) => setForm({ ...form, first_name: e.target.value })}
              />
            </div>
            <div>
              <label>كلمة المرور *</label>
              <input
                type="password"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                required
                minLength={6}
              />
            </div>
            <div>
              <label>الصلاحية</label>
              <select
                value={form.role_input}
                onChange={(e) => setForm({ ...form, role_input: e.target.value })}
              >
                <option value="hr">شؤون عاملين (موظفون وتقارير فقط)</option>
                <option value="cutting">موظف قص (قصاته فقط)</option>
                <option value="cutting_supervisor">مشرف قص (كل القصات)</option>
                <option value="production_manager">مدير إنتاج (كل القصات والتقارير)</option>
                <option value="admin">مدير (صلاحيات كاملة)</option>
              </select>
            </div>
            <button className="btn-primary">إنشاء المستخدم</button>
          </form>
        </div>
        <div className="card">
          <h2 className="mb-4 text-lg font-bold">المستخدمون الحاليون</h2>
          <div className="overflow-x-auto">
          <table className="data min-w-[520px]">
            <thead>
              <tr>
                <th>المستخدم</th>
                <th>الصلاحية</th>
                <th>الحالة</th>
                <th>إجراءات</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>
                    <b>{u.username}</b>
                    {u.first_name && (
                      <span className="text-slate-500"> — {u.first_name}</span>
                    )}
                  </td>
                  <td>{ROLE_LABEL[u.role] ?? "—"}</td>
                  <td>{u.is_active ? "نشط" : "موقوف"}</td>
                  <td>
                    <div className="flex gap-2">
                      <button
                        className="text-sm text-red-700 hover:underline"
                        onClick={() => resetPassword(u)}
                      >
                        تغيير كلمة المرور
                      </button>
                      <button
                        className="text-sm text-red-600 hover:underline"
                        onClick={() => toggleActive(u)}
                      >
                        {u.is_active ? "إيقاف" : "تفعيل"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      </div>
    </Shell>
  );
}
