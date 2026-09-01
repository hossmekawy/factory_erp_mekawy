"use client";

// The remnant log (SRS 7.6). **View only** — no balance and no "use it"
// button. There is no fabric stock in this phase, so a remnant here is a
// record that so many metres were left over, not an amount anyone can draw
// against. When stock arrives these rows become real balances.

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Loader2, Scissors } from "lucide-react";
import Shell from "@/components/Shell";
import { api, errorText } from "@/lib/api";
import { fmt } from "@/lib/cutting";

type Remnant = {
  id: number;
  lay: number;
  lay_line: number;
  length_m: string;
  shade_note: string;
  disposition: "waste" | "usable";
  disposition_label: string;
  logged_at: string;
};

export default function Page() {
  return (
    <Shell>
      <Suspense fallback={<div className="p-6 text-slate-500">جارٍ التحميل…</div>}>
        <Remnants />
      </Suspense>
    </Shell>
  );
}

function Remnants() {
  const router = useRouter();
  const params = useSearchParams();
  const disposition = params.get("disposition") ?? "";

  const [rows, setRows] = useState<Remnant[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const setParams = useCallback(
    (patch: Record<string, string | null>) => {
      const next = new URLSearchParams(params.toString());
      for (const [k, v] of Object.entries(patch)) {
        if (!v) next.delete(k);
        else next.set(k, v);
      }
      router.replace(`/cutting/remnants${next.toString() ? `?${next}` : ""}`, {
        scroll: false,
      });
    },
    [params, router]
  );

  useEffect(() => {
    setLoading(true);
    api(`/api/cutting/remnants/?${params.toString()}&ordering=-logged_at`)
      .then((d) => {
        setRows(d.results ?? d);
        setCount(d.count ?? (d.results ?? d).length);
      })
      .catch((e) => setError(errorText(e)))
      .finally(() => setLoading(false));
  }, [params]);

  const total = (kind: string) =>
    rows
      .filter((r) => r.disposition === kind)
      .reduce((s, r) => s + Number(r.length_m), 0);

  return (
    <div className="font-tajawal mx-auto max-w-4xl p-3">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h1 className="flex items-center gap-2 text-lg font-bold">
          <Scissors className="h-5 w-5 text-red-600" />
          سجل البواقي
        </h1>
        <Link href="/cutting/reports?r=remnants" className="text-sm text-slate-500 hover:text-red-700">
          تقرير البواقي
        </Link>
      </div>

      <p className="mb-3 text-xs text-slate-500">
        عرض بس — مفيش رصيد ولا استخدام. البواقي بتتسجّل عشان نعرف كام متر بيروح
        هالك، ولما المخزون يشتغل بتتحوّل لأرصدة فعلية.
      </p>

      <div className="mb-3 grid grid-cols-3 gap-2">
        <Card label="السطور" value={String(count)} />
        <Card label="هالك (الصفحة دي)" value={`${fmt(total("waste"))} م`} tone="rose" />
        <Card label="صالح (الصفحة دي)" value={`${fmt(total("usable"))} م`} />
      </div>

      <div className="mb-3 flex gap-1.5">
        {[
          { value: "", label: "الكل" },
          { value: "waste", label: "هالك" },
          { value: "usable", label: "صالح" },
        ].map((o) => (
          <button
            key={o.value || "all"}
            data-testid={`filter-${o.value || "all"}`}
            onClick={() => setParams({ disposition: o.value || null })}
            className={`rounded-full px-3 py-1.5 text-sm font-semibold transition ${
              disposition === o.value
                ? "bg-red-600 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-red-50 hover:text-red-700"
            }`}
          >
            {o.label}
          </button>
        ))}
      </div>

      {error && <p className="card mb-3 text-rose-700">{error}</p>}

      {loading ? (
        <div className="card flex items-center justify-center gap-2 py-10 text-slate-500">
          <Loader2 className="h-5 w-5 animate-spin" />
          جارٍ التحميل…
        </div>
      ) : rows.length === 0 ? (
        <div className="card py-10 text-center text-slate-500">مفيش بواقي مسجّلة</div>
      ) : (
        <div className="card overflow-x-auto">
          <table className="data" data-testid="remnant-table">
            <thead>
              <tr>
                <th>الطول</th>
                <th>التصنيف</th>
                <th>اللون</th>
                <th>القصة</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} data-testid="remnant-row">
                  <td dir="ltr" className="text-right font-semibold">
                    {fmt(Number(r.length_m))} م
                  </td>
                  <td>
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                        r.disposition === "waste"
                          ? "bg-rose-100 text-rose-700"
                          : "bg-emerald-100 text-emerald-700"
                      }`}
                    >
                      {r.disposition_label}
                    </span>
                  </td>
                  <td>{r.shade_note || "—"}</td>
                  <td>
                    {r.lay ? (
                      <Link href={`/cutting/${r.lay}`} className="text-red-700 hover:underline">
                        فتح
                      </Link>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Card({
  label,
  value,
  tone = "slate",
}: {
  label: string;
  value: string;
  tone?: "slate" | "rose";
}) {
  return (
    <div className="rounded-xl bg-white p-3 shadow-sm ring-1 ring-slate-100">
      <div className="text-[11px] text-slate-400">{label}</div>
      <div
        dir="ltr"
        className={`text-right text-lg font-bold ${
          tone === "rose" ? "text-rose-600" : "text-slate-800"
        }`}
      >
        {value}
      </div>
    </div>
  );
}
