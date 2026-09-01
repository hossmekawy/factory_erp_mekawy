"use client";

// A small CRUD screen shared by the two catalogue pages. Both are the same
// shape — list rows, add one, correct one, delete one that nothing uses — and
// the interesting parts (which fields, what a row looks like) are passed in.

import { useCallback, useEffect, useState } from "react";
import { Loader2, Pencil, Plus, Trash2, X } from "lucide-react";
import { ApiError, api, errorText } from "@/lib/api";
import { issuesOf } from "@/lib/cutting";

export type Field = {
  name: string;
  label: string;
  kind?: "text" | "number" | "select";
  options?: { value: string; label: string }[];
  placeholder?: string;
  required?: boolean;
  ltr?: boolean;
  hint?: string;
  /** Empty means null (a relation that is not set) rather than "" (a blank
   *  string). Getting this wrong makes the API reject the whole row. */
  nullable?: boolean;
};

export type CrudConfig<T> = {
  title: string;
  endpoint: string;
  fields: Field[];
  /** Columns shown in the table, in display order. */
  columns: { label: string; render: (row: T) => React.ReactNode; ltr?: boolean }[];
  /** How many things depend on this row; blocks delete when > 0. */
  usageCount?: (row: T) => number;
  usageLabel?: string;
  searchPlaceholder?: string;
  emptyText: string;
};

/** "/api/x/?flag=1&" -> "/api/x/" — the collection without its list filter. */
function baseUrl(endpoint: string): string {
  return endpoint.split("?")[0];
}

/** The detail URL for one row, ignoring any list filter on the endpoint. */
function itemUrl(endpoint: string, id: number): string {
  return `${baseUrl(endpoint)}${id}/`;
}

export default function CrudPage<T extends { id: number }>({
  config,
  canDelete,
}: {
  config: CrudConfig<T>;
  canDelete: boolean;
}) {
  const [rows, setRows] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<T | "new" | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    // The endpoint may already carry a filter (it ends with "&" when it does).
    const join = config.endpoint.includes("?") ? "" : "?";
    api(`${config.endpoint}${join}search=${encodeURIComponent(q)}&page_size=200`)
      .then((d) => setRows(d.results ?? d))
      .catch((e) => setError(errorText(e)))
      .finally(() => setLoading(false));
  }, [config.endpoint, q]);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  const remove = async (row: T) => {
    const used = config.usageCount?.(row) ?? 0;
    if (used > 0) {
      setError(`مينفعش يتمسح — مستخدم في ${used} ${config.usageLabel ?? "حاجة"}`);
      return;
    }
    if (!confirm("متأكد إنك عايز تمسحه؟")) return;
    setError("");
    try {
      await api(`${itemUrl(config.endpoint, row.id)}`, { method: "DELETE" });
      load();
    } catch (e) {
      const found = issuesOf((e as ApiError).data);
      setError(found[0]?.message ?? errorText(e));
    }
  };

  return (
    <div className="font-tajawal mx-auto max-w-4xl p-3">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h1 className="text-lg font-bold">{config.title}</h1>
        <button className="btn-primary" onClick={() => setEditing("new")}>
          <Plus className="h-4 w-4" />
          إضافة
        </button>
      </div>

      <input
        className="mb-3"
        placeholder={config.searchPlaceholder ?? "ابحث…"}
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />

      {error && (
        <p className="card mb-3 flex items-center justify-between text-rose-700">
          {error}
          <button onClick={() => setError("")} aria-label="إغلاق">
            <X className="h-4 w-4" />
          </button>
        </p>
      )}

      {loading ? (
        <div className="card flex items-center justify-center gap-2 py-10 text-slate-500">
          <Loader2 className="h-5 w-5 animate-spin" />
          جارٍ التحميل…
        </div>
      ) : rows.length === 0 ? (
        <div className="card py-10 text-center text-slate-500">{config.emptyText}</div>
      ) : (
        <div className="card overflow-x-auto">
          <table className="data">
            <thead>
              <tr>
                {config.columns.map((c) => (
                  <th key={c.label}>{c.label}</th>
                ))}
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  {config.columns.map((c) => (
                    <td
                      key={c.label}
                      dir={c.ltr ? "ltr" : undefined}
                      className={c.ltr ? "text-right" : undefined}
                    >
                      {c.render(row)}
                    </td>
                  ))}
                  <td className="whitespace-nowrap">
                    <button
                      data-testid="edit-row"
                      className="p-1 text-slate-400 hover:text-red-700"
                      onClick={() => setEditing(row)}
                      aria-label="تعديل"
                    >
                      <Pencil className="h-4 w-4" />
                    </button>
                    {canDelete && (
                      <button
                        data-testid="delete-row"
                        className="p-1 text-slate-400 hover:text-rose-700"
                        onClick={() => remove(row)}
                        aria-label="حذف"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing && (
        <EditDialog
          config={config}
          row={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}
    </div>
  );
}

function EditDialog<T extends { id: number }>({
  config,
  row,
  onClose,
  onSaved,
}: {
  config: CrudConfig<T>;
  row: T | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      config.fields.map((f) => [f.name, row ? String((row as any)[f.name] ?? "") : ""])
    )
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const save = async () => {
    setBusy(true);
    setError("");
    setFieldErrors({});
    try {
      await api(row ? itemUrl(config.endpoint, row.id) : baseUrl(config.endpoint), {
        method: row ? "PATCH" : "POST",
        body: JSON.stringify(
          Object.fromEntries(
            config.fields.flatMap((f) => {
              const raw = values[f.name] ?? "";
              if (raw !== "") return [[f.name, raw]];
              // An empty number is not the string "" — the API rejects that
              // outright. Leave the key out and let the model's default stand.
              if (f.kind === "number") return [];
              return [[f.name, f.nullable ? null : ""]];
            })
          )
        ),
      });
      onSaved();
    } catch (e) {
      const data = (e as ApiError).data as Record<string, unknown> | null;
      const found = issuesOf(data);
      if (found.length) {
        setError(found[0].message);
      } else if (data && typeof data === "object") {
        // DRF field errors, e.g. a duplicate code
        const perField: Record<string, string> = {};
        for (const [k, v] of Object.entries(data)) {
          if (Array.isArray(v)) perField[k] = String(v[0]);
        }
        setFieldErrors(perField);
        if (!Object.keys(perField).length) setError(errorText(e));
      } else {
        setError(errorText(e));
      }
    } finally {
      setBusy(false);
    }
  };

  const missing = config.fields.some((f) => f.required && !values[f.name]?.trim());

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-0 sm:items-center sm:p-4">
      <div className="w-full max-w-md rounded-t-2xl bg-white p-4 sm:rounded-2xl">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-bold">{row ? "تعديل" : "إضافة"}</h2>
          <button onClick={onClose} aria-label="إغلاق">
            <X className="h-5 w-5 text-slate-400" />
          </button>
        </div>

        <div className="space-y-3">
          {config.fields.map((f) => (
            <div key={f.name}>
              <label>
                {f.label}
                {f.required && <span className="text-rose-600"> *</span>}
              </label>
              {f.kind === "select" ? (
                <select
                  data-testid={`field-${f.name}`}
                  value={values[f.name] ?? ""}
                  onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}
                >
                  <option value="">—</option>
                  {f.options!.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  data-testid={`field-${f.name}`}
                  dir={f.ltr ? "ltr" : undefined}
                  className={`min-h-11 ${f.ltr ? "ltr-num" : ""}`}
                  inputMode={f.kind === "number" ? "numeric" : undefined}
                  placeholder={f.placeholder}
                  value={values[f.name] ?? ""}
                  onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}
                />
              )}
              {f.hint && <p className="mt-1 text-xs text-slate-400">{f.hint}</p>}
              {fieldErrors[f.name] && (
                <p data-testid={`error-${f.name}`} className="mt-1 text-sm text-rose-600">
                  {fieldErrors[f.name]}
                </p>
              )}
            </div>
          ))}
        </div>

        {error && <p className="mt-3 text-sm font-semibold text-rose-700">{error}</p>}

        <div className="mt-4 flex gap-2">
          <button className="btn-secondary flex-1" onClick={onClose}>
            إلغاء
          </button>
          <button
            data-testid="save-row"
            className="btn-primary flex-1"
            disabled={busy || missing}
            onClick={save}
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "حفظ"}
          </button>
        </div>
      </div>
    </div>
  );
}
