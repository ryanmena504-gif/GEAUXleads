import React from "react";
import { useSearchParams } from "react-router-dom";
import { Flame, Snowflake, Sparkles, Clock, Plus, Download } from "lucide-react";
import { toast } from "sonner";
import { authHeaders, noteUnauthorized } from "@/lib/password";

/**
 * URL-driven saved-view chips. Bookmarkable. Does not create a second
 * source of truth — flips existing filter query params on the current
 * route. 44px min tap target on mobile (h-11), tightened on wider views.
 */
const VIEWS = {
  opportunities: [
    { key: "hot",     label: "Hot",              icon: Flame,     params: { view: "hot" } },
    { key: "enrich",  label: "Needs enrichment", icon: Snowflake, params: { view: "needs-enrichment" } },
    { key: "fresh",   label: "Fresh",            icon: Sparkles,  params: { view: "fresh" } },
    { key: "stale",   label: "Stale",            icon: Clock,     params: { view: "stale" } },
    { key: "recent",  label: "Recently added",   icon: Plus,      params: { view: "recently-added" } },
  ],
};

export const SavedViewsBar = ({ scope = "opportunities", exportHref, testId = "saved-views" }) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeView = searchParams.get("view") || "";
  const views = VIEWS[scope] || [];

  const exportCsv = async (event) => {
    event.preventDefault();
    try {
      const res = await fetch(exportHref, { headers: authHeaders() });
      const body = await res.clone().json().catch(() => ({}));
      if (noteUnauthorized(res.status, body)) return;
      if (!res.ok) throw new Error("export failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "opportunities.csv";
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Couldn't download the CSV");
    }
  };

  const applyView = (params) => {
    const next = new URLSearchParams(searchParams);
    ["view"].forEach((k) => next.delete(k));
    Object.entries(params).forEach(([k, v]) => next.set(k, v));
    setSearchParams(next);
  };
  const clearView = () => {
    const next = new URLSearchParams(searchParams);
    next.delete("view");
    setSearchParams(next);
  };

  return (
    <div
      data-testid={testId}
      className="flex items-center gap-1.5 flex-wrap py-1"
    >
      <button
        type="button"
        onClick={clearView}
        data-testid={`${testId}-all`}
        className={`inline-flex items-center h-11 sm:h-8 px-3 rounded-md text-[12px] font-medium border transition-colors ${
          activeView === ""
            ? "border-[var(--bh-brass)] text-[var(--bh-brass)] bg-[var(--bh-brass-mute)]"
            : "bh-hairline text-[var(--bh-ink-3)] hover:text-[var(--bh-ink)]"
        }`}
      >
        All
      </button>
      {views.map((v) => {
        const active = activeView === v.params.view;
        return (
          <button
            key={v.key}
            type="button"
            onClick={() => applyView(v.params)}
            data-testid={`${testId}-${v.key}`}
            className={`inline-flex items-center gap-1.5 h-11 sm:h-8 px-3 rounded-md text-[12px] font-medium border transition-colors ${
              active
                ? "border-[var(--bh-brass)] text-[var(--bh-brass)] bg-[var(--bh-brass-mute)]"
                : "bh-hairline text-[var(--bh-ink-3)] hover:text-[var(--bh-ink)]"
            }`}
          >
            <v.icon size={11} strokeWidth={1.75} /> {v.label}
          </button>
        );
      })}
      {exportHref && (
        <button
          type="button"
          onClick={exportCsv}
          data-testid={`${testId}-export`}
          className="ml-auto inline-flex items-center gap-1.5 h-11 sm:h-8 px-3 rounded-md text-[12px] font-medium border bh-hairline text-[var(--bh-ink-2)] hover:text-[var(--bh-ink)]"
        >
          <Download size={11} strokeWidth={1.75} /> Export CSV
        </button>
      )}
    </div>
  );
};

export default SavedViewsBar;
