"use client";

// In-system alerts (SRS 11.1). Each person sees only their own.

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, Bell, Check, ClipboardList, Loader2, Scissors } from "lucide-react";
import Shell from "@/components/Shell";
import { api, errorText } from "@/lib/api";

type Notification = {
  id: number;
  kind: "shortage" | "pieces_loss" | "awaiting_count";
  kind_label: string;
  lay: number | null;
  lay_code: string;
  title: string;
  body: string;
  is_read: boolean;
  created_at: string;
};

const ICON = {
  shortage: Scissors,
  pieces_loss: AlertTriangle,
  awaiting_count: ClipboardList,
};

const TONE = {
  shortage: "bg-rose-100 text-rose-700",
  pieces_loss: "bg-amber-100 text-amber-700",
  awaiting_count: "bg-sky-100 text-sky-700",
};

export default function Page() {
  const [rows, setRows] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [onlyUnread, setOnlyUnread] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    api(`/api/cutting/notifications/${onlyUnread ? "?is_read=false" : ""}`)
      .then((d) => setRows(d.results ?? d))
      .catch((e) => setError(errorText(e)))
      .finally(() => setLoading(false));
  }, [onlyUnread]);

  useEffect(load, [load]);

  const markAll = async () => {
    try {
      await api("/api/cutting/notifications/mark-read/", {
        method: "POST",
        body: JSON.stringify({}),
      });
      load();
    } catch (e) {
      setError(errorText(e));
    }
  };

  const unread = rows.filter((r) => !r.is_read).length;

  return (
    <Shell>
      <div className="font-tajawal mx-auto max-w-3xl p-3">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h1 className="flex items-center gap-2 text-lg font-bold">
            <Bell className="h-5 w-5 text-red-600" />
            التنبيهات
          </h1>
          {unread > 0 && (
            <button data-testid="mark-all-read" className="btn-secondary" onClick={markAll}>
              <Check className="h-4 w-4" />
              علّم الكل كمقروء
            </button>
          )}
        </div>

        <label className="mb-3 flex items-center gap-2 text-sm">
          <input
            data-testid="only-unread"
            type="checkbox"
            className="!w-auto"
            checked={onlyUnread}
            onChange={(e) => setOnlyUnread(e.target.checked)}
          />
          <span className="font-normal text-slate-600">غير المقروء بس</span>
        </label>

        {error && <p className="card mb-3 text-rose-700">{error}</p>}

        {loading ? (
          <div className="card flex items-center justify-center gap-2 py-10 text-slate-500">
            <Loader2 className="h-5 w-5 animate-spin" />
            جارٍ التحميل…
          </div>
        ) : rows.length === 0 ? (
          <div className="card py-10 text-center">
            <Check className="mx-auto h-12 w-12 rounded-full bg-emerald-100 p-2.5 text-emerald-600" />
            <p className="mt-3 font-semibold">مفيش تنبيهات</p>
          </div>
        ) : (
          <div className="space-y-2">
            {rows.map((n) => {
              const Icon = ICON[n.kind] ?? Bell;
              const inner = (
                <div
                  data-testid="notification"
                  data-read={n.is_read}
                  className={`card flex gap-3 ${n.is_read ? "opacity-60" : ""}`}
                >
                  <span
                    className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${
                      TONE[n.kind] ?? "bg-slate-100"
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-2">
                      <span className="font-semibold">{n.title}</span>
                      {!n.is_read && (
                        <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-red-600" />
                      )}
                    </div>
                    {n.body && <p className="mt-1 text-sm text-slate-600">{n.body}</p>}
                    <p className="mt-1 text-xs text-slate-400" dir="ltr">
                      {new Date(n.created_at).toLocaleString("ar-EG")}
                    </p>
                  </div>
                </div>
              );
              return n.lay ? (
                <Link key={n.id} href={`/cutting/${n.lay}`} className="block">
                  {inner}
                </Link>
              ) : (
                <div key={n.id}>{inner}</div>
              );
            })}
          </div>
        )}
      </div>
    </Shell>
  );
}
