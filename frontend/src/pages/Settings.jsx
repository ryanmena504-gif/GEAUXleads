import React, { useEffect, useState } from "react";
import TopHeader from "@/components/TopHeader";
import { api } from "@/lib/api";
import { Database, Zap, ShieldCheck, Radio, RefreshCw, Command } from "lucide-react";
import { toast } from "sonner";

const Row = ({ icon: Icon, title, subtitle, right }) => (
  <div className="bh-surface rounded p-4 flex items-center gap-4">
    <div className="w-10 h-10 rounded bh-surface-2 flex items-center justify-center">
      <Icon size={16} className="text-amber-400" />
    </div>
    <div className="flex-1">
      <div className="font-medium text-neutral-100">{title}</div>
      <div className="text-xs text-neutral-500 mt-0.5">{subtitle}</div>
    </div>
    {right}
  </div>
);

const Pill = ({ tone, children, ...rest }) => (
  <span
    {...rest}
    className={
      "mono text-[10px] uppercase tracking-widest px-2 py-1 rounded border " +
      (tone === "on"
        ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/25"
        : tone === "warn"
          ? "bg-amber-500/10 text-amber-300 border-amber-500/25"
          : "bg-neutral-500/10 text-neutral-400 border-neutral-500/25")
    }
  >
    {children}
  </span>
);

const Settings = () => {
  const [cfg, setCfg] = useState(null);
  const [schema, setSchema] = useState(null);
  const [reloading, setReloading] = useState(false);

  const load = () => {
    api.config().then(setCfg);
    api.schema().then(setSchema).catch(() => setSchema(null));
  };

  useEffect(() => {
    load();
  }, []);

  const reload = async () => {
    setReloading(true);
    try {
      const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/admin/reload`, {
        method: "POST",
      });
      const data = await res.json();
      toast.success(`Backend reloaded — now on ${data.backend}`);
      load();
    } catch {
      toast.error("Reload failed");
    } finally {
      setReloading(false);
    }
  };

  const isLive = cfg?.backend === "airtable";
  const tone = isLive ? "on" : cfg?.airtable_configured ? "warn" : "off";
  const label = isLive
    ? "Live"
    : cfg?.airtable_configured
      ? "Configured · not enabled"
      : "Sample";

  const mapped = schema?.mapped_fields || [];
  const unmapped = schema?.unmapped_expected || [];
  const editable = schema?.editable_allowlist || [];

  return (
    <>
      <TopHeader pageTitle="Settings" subtitle="Configure your operator profile" />
      <div className="px-4 lg:px-8 py-6 space-y-6 max-w-5xl">
        <section>
          <div className="flex items-baseline justify-between mb-3">
            <div className="mono text-[10px] uppercase tracking-widest text-neutral-500">
              Section / 01 · Data Sources
            </div>
            <button
              onClick={reload}
              disabled={reloading}
              data-testid="settings-reload"
              className="mono text-[10px] uppercase tracking-widest text-amber-400 hover:text-amber-300 inline-flex items-center gap-1.5 disabled:opacity-50"
            >
              <RefreshCw size={11} className={reloading ? "animate-spin" : ""} />
              Reload service
            </button>
          </div>
          <div className="space-y-2">
            <Row
              icon={Database}
              title="Airtable"
              subtitle={
                isLive
                  ? `Connected · reading from base ${schema?.base_id?.slice(0, 8) ?? ""}… / ${schema?.table_name ?? ""}`
                  : cfg?.airtable_configured
                    ? "Credentials present but AIRTABLE_ENABLED is not true"
                    : "Not activated. Bloodhound is running on sample data."
              }
              right={<Pill tone={tone} data-testid="airtable-pill">{label}</Pill>}
            />
            <Row
              icon={Radio}
              title="New Orleans Permits"
              subtitle="Primary discovery source · daily refresh via Make.com"
              right={<Pill tone="on">Live</Pill>}
            />
            <Row
              icon={Zap}
              title="OpenAI Analysis"
              subtitle="Prioritization, evidence summary, next best action"
              right={<Pill tone="on">Active</Pill>}
            />
            <Row
              icon={Command}
              title="Command Palette"
              subtitle="Press ⌘K (Ctrl+K on Windows) anywhere to jump between opportunities and pages"
              right={<Pill tone="on">⌘K</Pill>}
            />
          </div>
        </section>

        <section>
          <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 mb-3">
            Section / 02 · Airtable Connection
          </div>
          <div className="bh-surface rounded p-5 space-y-3">
            <p className="text-sm text-neutral-400 leading-relaxed">
              Bloodhound reads opportunities from Airtable through a server-side
              data layer — no keys are ever shipped to the browser. To activate
              the live connection, set the following environment variables on
              the backend and click <span className="text-amber-300">Reload service</span>.
            </p>
            <div className="bh-surface-2 rounded p-4 mono text-xs text-neutral-300 space-y-1">
              <div><span className="text-amber-300">AIRTABLE_API_KEY</span>=your-personal-access-token</div>
              <div><span className="text-amber-300">AIRTABLE_BASE_ID</span>=appXXXXXXXXXXXXXX</div>
              <div><span className="text-amber-300">AIRTABLE_OPPORTUNITIES_TABLE</span>=Opportunities</div>
              <div><span className="text-amber-300">AIRTABLE_ENABLED</span>=true</div>
            </div>
            <p className="text-xs text-neutral-500 leading-relaxed flex items-start gap-2">
              <ShieldCheck size={12} className="text-emerald-400 mt-0.5" />
              Required token scopes: <span className="mono">data.records:read</span>, <span className="mono">data.records:write</span>, <span className="mono">schema.bases:read</span>. Writes are strictly limited to Status, Ryan&rsquo;s Decision, Next Follow Up, and Outcome.
            </p>
          </div>
        </section>

        {isLive && schema && (
          <section data-testid="section-schema">
            <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 mb-3">
              Section / 03 · Live Airtable Schema
            </div>
            <div className="bh-surface rounded p-5">
              <div className="grid md:grid-cols-3 gap-4 mb-4">
                <div>
                  <div className="mono text-[10px] uppercase tracking-widest text-neutral-500">
                    Fields mapped
                  </div>
                  <div className="font-display text-3xl font-bold text-neutral-100 tabular-nums">
                    {mapped.length}
                  </div>
                </div>
                <div>
                  <div className="mono text-[10px] uppercase tracking-widest text-neutral-500">
                    Expected but not in base
                  </div>
                  <div className="font-display text-3xl font-bold text-amber-300 tabular-nums">
                    {unmapped.length}
                  </div>
                </div>
                <div>
                  <div className="mono text-[10px] uppercase tracking-widest text-neutral-500">
                    Editable (write allowlist)
                  </div>
                  <div className="font-display text-3xl font-bold text-emerald-400 tabular-nums">
                    {editable.length}
                  </div>
                </div>
              </div>

              <div className="border-t bh-hairline pt-4">
                <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 mb-2">
                  Mapping
                </div>
                <div className="grid md:grid-cols-2 gap-x-6 gap-y-1 text-[13px]">
                  {mapped.map((m) => (
                    <div key={m.airtable} className="flex items-center gap-2">
                      <span className="mono text-neutral-100 truncate">{m.airtable}</span>
                      <span className="text-neutral-600">→</span>
                      <span className="mono text-neutral-500 truncate">{m.internal}</span>
                      {m.readonly && (
                        <span className="mono text-[9px] uppercase tracking-widest text-amber-400 ml-auto">
                          read-only
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {unmapped.length > 0 && (
                <div className="border-t bh-hairline pt-4 mt-4">
                  <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 mb-2">
                    Expected fields not found in base
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {unmapped.map((u) => (
                      <span key={u} className="mono text-[11px] px-2 py-0.5 rounded border bh-hairline text-amber-300">
                        {u}
                      </span>
                    ))}
                  </div>
                  <div className="text-xs text-neutral-500 mt-2 leading-relaxed">
                    These fields exist in Bloodhound&rsquo;s spec but weren&rsquo;t present in your Airtable schema. Add them to the base to enable those UI sections, or ignore.
                  </div>
                </div>
              )}
            </div>
          </section>
        )}

        <section>
          <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 mb-3">
            Section / 04 · Operator Preferences
          </div>
          <div className="bh-surface rounded p-5 space-y-4">
            <div>
              <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 mb-1">
                Operator name
              </div>
              <input
                defaultValue="Ryan C."
                data-testid="settings-name"
                className="w-full bg-transparent border bh-hairline rounded h-9 px-3 text-sm text-neutral-100 focus:border-amber-500/50 outline-none"
              />
            </div>
            <div>
              <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 mb-1">
                Primary market
              </div>
              <input
                defaultValue="New Orleans, LA"
                data-testid="settings-market"
                className="w-full bg-transparent border bh-hairline rounded h-9 px-3 text-sm text-neutral-100 focus:border-amber-500/50 outline-none"
              />
            </div>
          </div>
        </section>
      </div>
    </>
  );
};

export default Settings;
