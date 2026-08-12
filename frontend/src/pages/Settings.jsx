import React, { useEffect, useState } from "react";
import TopHeader from "@/components/TopHeader";
import PlaybookEditor from "@/components/PlaybookEditor";
import { api } from "@/lib/api";
import { Database, Zap, ShieldCheck, Radio, RefreshCw, Command, BookMarked, Mail, Save, Sparkles, PlayCircle } from "lucide-react";
import { toast } from "sonner";
import { fetchUserSettings, saveUserSettings } from "@/hooks/useUserSettings";

/**
 * Sender identity block — Ryan can point mailto: drafts at whichever email
 * address he wants to appear as the sender. This is a display-only value
 * (mailto: cannot force a specific From account on iPhone / Mac Mail), but
 * having the right address visible in the composed body keeps him from
 * hitting Send on the wrong account.
 */
const SenderIdentitySection = () => {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchUserSettings().then((s) => {
      if (!s) return;
      setEmail(s.sender_email || "");
      setName(s.sender_name || "");
      setPhone(s.sender_phone || "");
      setLoaded(true);
    });
  }, []);

  const save = async () => {
    const trimmed = email.trim();
    if (trimmed && (!trimmed.includes("@") || !trimmed.split("@")[1]?.includes("."))) {
      toast.error("That doesn't look like an email address");
      return;
    }
    setSaving(true);
    try {
      await saveUserSettings({
        sender_email: trimmed,
        sender_name: name.trim(),
        sender_phone: phone.trim(),
      });
      toast.success("Sender identity saved");
    } catch (err) {
      const msg = err?.response?.data?.detail || "Save failed";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <section data-testid="section-sender-identity">
      <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 mb-3 inline-flex items-center gap-1.5">
        <Mail size={11} /> Your sender identity
      </div>
      <div className="bh-surface rounded p-5 space-y-4">
        <p className="text-sm text-neutral-400 leading-relaxed">
          Every email draft is signed with this name, phone, and email so
          recipients always see the same contact info from The Shirtless
          Handyman. Change it here if you ever need a different one.
        </p>
        <p className="text-[12px] text-neutral-500 leading-relaxed">
          Note: iPhone and Mac Mail always send from whichever account is set
          as default on your device, and text messages always come from your
          iPhone&rsquo;s own number. Bloodhound cannot pick either one — this
          value just makes sure the right info appears inside the draft
          before you press Send.
        </p>
        <div className="grid sm:grid-cols-3 gap-3">
          <div>
            <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 mb-1">
              Your name
            </div>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              data-testid="settings-sender-name"
              placeholder="Ryan Mena"
              disabled={!loaded}
              className="w-full bg-transparent border bh-hairline rounded h-10 px-3 text-sm text-[var(--bh-ink)] focus:border-[var(--bh-brass)]/60 outline-none disabled:opacity-50"
            />
          </div>
          <div>
            <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 mb-1">
              Sender email
            </div>
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              data-testid="settings-sender-email"
              placeholder="ryanmena@theshirtlesshandyman.com"
              disabled={!loaded}
              type="email"
              className="w-full bg-transparent border bh-hairline rounded h-10 px-3 text-sm text-[var(--bh-ink)] focus:border-[var(--bh-brass)]/60 outline-none disabled:opacity-50"
            />
          </div>
          <div>
            <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 mb-1">
              Sender phone
            </div>
            <input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              data-testid="settings-sender-phone"
              placeholder="(504) 264-4919"
              disabled={!loaded}
              type="tel"
              className="w-full bg-transparent border bh-hairline rounded h-10 px-3 text-sm text-[var(--bh-ink)] focus:border-[var(--bh-brass)]/60 outline-none disabled:opacity-50"
            />
          </div>
        </div>
        <div className="flex items-center justify-end">
          <button
            onClick={save}
            disabled={!loaded || saving}
            data-testid="settings-sender-save"
            className="text-[13px] h-9 px-4 rounded-md font-medium inline-flex items-center gap-1.5 disabled:opacity-50"
            style={{
              background: "var(--bh-brass)",
              color: "var(--bh-surface)",
            }}
          >
            <Save size={13} />
            {saving ? "Saving…" : "Save sender identity"}
          </button>
        </div>
      </div>
    </section>
  );
};

/**
 * AI Contact Enrichment — Gemini + Google Search grounding sweep that fills
 * missing phone / email on Leads that have neither. Manual only:
 *   • Toggle turns the feature on/off (persisted in user_settings)
 *   • Enrich now button kicks off one sweep against the current Airtable data
 *   • Status card shows the last run's numbers
 */
const EnrichmentSection = () => {
  const [enabled, setEnabled] = useState(false);
  const [status, setStatus] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);

  const refreshStatus = React.useCallback(() => {
    api
      .enrichmentStatus()
      .then((r) => setStatus(r))
      .catch(() => setStatus({ available: false }));
  }, []);

  useEffect(() => {
    Promise.all([fetchUserSettings(), api.enrichmentStatus().catch(() => ({ available: false }))])
      .then(([s, e]) => {
        setEnabled(Boolean(s?.enrichment_enabled));
        setStatus(e);
        setLoaded(true);
      });
  }, []);

  const toggle = async () => {
    const next = !enabled;
    setSaving(true);
    setEnabled(next);
    try {
      await saveUserSettings({ enrichment_enabled: next });
      toast.success(next ? "AI enrichment enabled" : "AI enrichment disabled");
      refreshStatus();
    } catch (err) {
      setEnabled(!next);
      const msg = err?.response?.data?.detail || "Save failed";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const run = async () => {
    if (running) return;
    setRunning(true);
    toast.info("Enrichment started · this may take a minute or two.");
    try {
      const r = await api.runEnrichment();
      if (r?.reason === "already_running") {
        toast.warning("A sweep is already running.");
      }
      // Poll status until it finishes (or 5 minutes elapses, whichever first).
      const started = Date.now();
      const poll = async () => {
        const s = await api.enrichmentStatus().catch(() => null);
        setStatus(s);
        if (!s?.running) {
          const l = s?.last_run;
          if (l) {
            toast.success(
              `Enrichment done · ${l.enriched ?? 0} filled · ${l.failed ?? 0} failed`,
            );
          }
          setRunning(false);
          return;
        }
        if (Date.now() - started > 5 * 60 * 1000) {
          toast.warning("Sweep still running — check back shortly.");
          setRunning(false);
          return;
        }
        setTimeout(poll, 3000);
      };
      setTimeout(poll, 2500);
    } catch (err) {
      const msg = err?.response?.data?.detail || "Enrichment run failed";
      toast.error(msg);
      setRunning(false);
    }
  };

  const available = status?.available !== false;
  const last = status?.last_run;
  const modelLabel = status?.model || "gemini-2.5-flash";

  return (
    <section data-testid="section-ai-enrichment">
      <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 mb-3 inline-flex items-center gap-1.5">
        <Sparkles size={11} /> AI contact enrichment
      </div>
      <div className="bh-surface rounded p-5 space-y-4">
        <p className="text-sm text-neutral-400 leading-relaxed">
          When a new lead lands with no phone or email, tap{" "}
          <span className="text-amber-300">Enrich now</span> and Bloodhound
          will use Gemini with Google Search grounding to find their public
          business phone or email and write it straight to Airtable. Leads
          without a hit stay in the pool so the AI can keep re-trying them on
          the next sweep — nothing gets archived automatically.
        </p>
        <p className="text-[12px] text-neutral-500 leading-relaxed">
          Runs manually only. Only targets leads missing BOTH phone and email.
          Uses <span className="mono">{modelLabel}</span> · powered by your
          Emergent LLM key.
        </p>

        <div className="flex items-center justify-between gap-3 pt-2 border-t bh-hairline">
          <div>
            <div className="text-sm text-[var(--bh-ink)] font-medium">
              Enable AI enrichment
            </div>
            <div className="text-[12px] text-neutral-500">
              Must be on before the Enrich-now button can run.
            </div>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={enabled}
            onClick={toggle}
            disabled={!loaded || saving || !available}
            data-testid="settings-enrichment-toggle"
            className={
              "relative inline-flex h-7 w-12 items-center rounded-full transition-colors duration-150 disabled:opacity-40 " +
              (enabled ? "bg-emerald-500/70" : "bg-neutral-700")
            }
          >
            <span
              className={
                "inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform duration-150 " +
                (enabled ? "translate-x-6" : "translate-x-1")
              }
            />
          </button>
        </div>

        <div className="flex items-center justify-between gap-3">
          <div className="text-[12.5px] text-neutral-400 leading-relaxed max-w-md">
            {available
              ? `Tap Enrich now to sweep every lead missing both phone and email. Up to ${status?.max_per_sweep ?? 15} leads per sweep.`
              : "Enrichment isn't available — the Emergent LLM key or Airtable connection is missing."}
          </div>
          <button
            type="button"
            onClick={run}
            disabled={!enabled || running || !available}
            data-testid="settings-enrichment-run"
            className="text-[13px] h-9 px-4 rounded-md font-medium inline-flex items-center gap-1.5 disabled:opacity-40"
            style={{ background: "var(--bh-brass)", color: "var(--bh-surface)" }}
          >
            <PlayCircle size={14} />
            {running ? "Enriching…" : "Enrich now"}
          </button>
        </div>

        {last && (
          <div
            data-testid="settings-enrichment-last-run"
            className="border-t bh-hairline pt-3 grid grid-cols-2 sm:grid-cols-3 gap-3 text-[13px]"
          >
            <div>
              <div className="mono text-[10px] uppercase tracking-widest text-neutral-500">
                Last run
              </div>
              <div className="text-neutral-200 mt-0.5">
                {last.finished_at
                  ? new Date(last.finished_at).toLocaleString(undefined, {
                      month: "short",
                      day: "numeric",
                      hour: "numeric",
                      minute: "2-digit",
                    })
                  : "—"}
              </div>
            </div>
            <div>
              <div className="mono text-[10px] uppercase tracking-widest text-neutral-500">
                Scanned
              </div>
              <div className="text-neutral-200 mt-0.5 tabular-nums">
                {last.scanned ?? 0}
              </div>
            </div>
            <div>
              <div className="mono text-[10px] uppercase tracking-widest text-emerald-400">
                Enriched
              </div>
              <div className="text-emerald-300 mt-0.5 tabular-nums">
                {last.enriched ?? 0}
              </div>
            </div>
            {(last.failed ?? 0) > 0 && (
              <div className="col-span-2 sm:col-span-3 text-[12px] text-red-300">
                {last.failed} failed · {last.errors?.[0] || "check backend logs"}
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
};

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
      <TopHeader pageTitle="Settings" subtitle="Configure your account preferences" />
      <div className="px-4 lg:px-8 py-6 space-y-6 max-w-5xl">
        <section>
          <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 mb-3">
            Data sources
          </div>
          <div className="flex items-baseline justify-end mb-3">
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
            How Bloodhound connects to Airtable
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
              Live Airtable schema
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

        <SenderIdentitySection />

        <EnrichmentSection />

        <section data-testid="section-playbooks">
          <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 mb-3 inline-flex items-center gap-1.5">
            <BookMarked size={11} /> Message playbooks
          </div>
          <PlaybookEditor />
        </section>

        <section>
          <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 mb-3">
            Your account
          </div>
          <div className="bh-surface rounded p-5 space-y-4">
            <div>
              <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 mb-1">
                Account name
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
