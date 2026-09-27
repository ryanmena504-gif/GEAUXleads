import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  Users,
  Mail,
  Phone,
  Lock,
  ExternalLink,
  Sparkles,
  ChevronDown,
  UploadCloud,
  Check,
} from "lucide-react";
import { api } from "@/lib/api";
import DiscoveryNav from "@/components/DiscoveryNav";
import FreshContactBadge from "@/components/FreshContactBadge";
import DaysOnTable from "@/components/DaysOnTable";
import DiscoverySortToggle, { sortByDays } from "@/components/DiscoverySortToggle";
import ResearchPanel from "@/components/ResearchPanel";
import { buildSalutation } from "@/lib/greeting";
import { extractContact } from "@/lib/contactExtract";
import { toast } from "sonner";

/**
 * DiscoveryRealEstateAgents — pre-listing pitch queue for real estate
 * agents. When an agent's Outreach Gate is unlocked (via Make on the
 * Airtable side), the app renders a mailto/sms/tel button pre-loaded
 * with the "photo-ready bathroom" pitch. Until then, the row is a
 * strict read-only preview: agent name, brokerage, why-they're-a-target,
 * plus a collapsible showing the pitch that WILL send when they're
 * unlocked.
 *
 * GEAUXleads respects Claude's Outreach Gate absolutely — no locked
 * agent gets a callable button, even if their phone/email happens to
 * be enriched separately.
 */

// The pre-listing pitch template. Kept in one place so it stays
// consistent across the whole app. Uses the same {name}, {brokerage}
// tokens the mailto builder expects.
const PITCH_SUBJECT = "Photo-ready bathroom before the listing hits MLS";

const buildPitchBody = ({ agent_name, brokerage, sender_name = "Ryan" }) => {
  // Agents are almost always people; route through the shared builder
  // so a brokerage-shaped name like "The Smith Group" falls back to a
  // neutral "Hi there,".
  const salutation = buildSalutation([agent_name], {
    verb: "Hi",
    generic: "there",
  });
  const brokerageLine = brokerage
    ? `I saw you're with ${brokerage} and wanted to reach out about something the top NOLA agents keep asking me for.`
    : `Wanted to reach out about something the top NOLA agents keep asking me for.`;
  return [
    salutation,
    "",
    `I'm ${sender_name} with The Shirtless Handyman. ${brokerageLine}`,
    "",
    `When a bathroom's the reason a listing lingers, I can turn it around in 3–5 days — seamless microcement over the existing tub surround, feature wall, or full wet zone. No demo dust, no grout lines in the photos, and it holds up long after closing. It photographs like a boutique hotel.`,
    "",
    `If you have a listing coming up where the bathroom is holding it back, send me a photo. I'll tell you what it'll cost and when I can be in and out — usually before your photographer arrives.`,
    "",
    `— ${sender_name}`,
  ].join("\n");
};

const GateChip = ({ ready, gate }) => {
  const label = gate || (ready ? "Ready" : "Locked");
  const fg = ready ? "var(--bh-olive)" : "#8a5a45";
  const bg = ready ? "var(--bh-olive-mute)" : "rgba(138,90,69,0.10)";
  const border = ready ? "rgba(107,122,85,0.32)" : "rgba(138,90,69,0.28)";
  return (
    <span
      data-testid={`agent-gate-${ready ? "ready" : "locked"}`}
      className="inline-flex items-center gap-1 rounded-full border px-2 py-[1px] text-[10px] font-medium tracking-tight whitespace-nowrap"
      style={{ color: fg, background: bg, borderColor: border }}
    >
      {!ready && <Lock size={9} strokeWidth={2} />}
      {label}
    </span>
  );
};

const PitchPreview = ({ agent, senderName }) => {
  const [open, setOpen] = useState(false);
  const body = useMemo(
    () => buildPitchBody({ agent_name: agent.name, brokerage: agent.brokerage, sender_name: senderName }),
    [agent.name, agent.brokerage, senderName],
  );
  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        data-testid={`agent-pitch-toggle-${agent.id}`}
        className="inline-flex items-center gap-1.5 text-[11px] font-medium text-[var(--bh-ink-2)] hover:text-[var(--bh-ink)]"
      >
        <Sparkles size={11} className="text-[var(--bh-brass)]" />
        Preview pitch template
        <ChevronDown
          size={11}
          className="transition-transform"
          style={{ transform: open ? "rotate(180deg)" : "rotate(0deg)" }}
        />
      </button>
      {open && (
        <div
          className="mt-2 rounded-sm p-3 border bh-hairline bg-[var(--bh-surface-2)]"
          data-testid={`agent-pitch-body-${agent.id}`}
        >
          <div className="mono text-[9.5px] uppercase tracking-widest text-[var(--bh-ink-mute)]">
            Subject
          </div>
          <div className="text-[12.5px] text-[var(--bh-ink)] font-medium mt-0.5">
            {PITCH_SUBJECT}
          </div>
          <div className="mono text-[9.5px] uppercase tracking-widest text-[var(--bh-ink-mute)] mt-2.5">
            Body
          </div>
          <pre className="whitespace-pre-wrap text-[12px] text-[var(--bh-ink-2)] leading-snug mt-0.5 font-body">
            {body}
          </pre>
        </div>
      )}
    </div>
  );
};

const Row = ({ agent, senderName, researchOpen, onToggleResearch, onEnriched }) => {
  const [extracted, setExtracted] = useState({ email: "", phone: "" });
  const [autofill, setAutofill] = useState({ status: "idle", error: null });
  const hasExisting = Boolean(agent.email || agent.phone);

  const handleResearchResult = (result) => {
    const c = extractContact(result?.answer || "");
    setExtracted({
      email: c.email || "",
      phone: c.phone || "",
    });
  };

  const sendToAirtable = async () => {
    const email = (extracted.email || "").trim();
    const phone = (extracted.phone || "").trim();
    if (!email && !phone) {
      toast.error("Nothing to send — need at least email or phone.");
      return;
    }
    setAutofill({ status: "sending", error: null });
    try {
      const updated = await api.enrichRealEstateAgentContact(agent.id, { email, phone });
      setAutofill({ status: "done", error: null });
      toast.success("Sent to Airtable — Claude will see it on the next classifier pass.");
      if (onEnriched) onEnriched(updated);
    } catch (err) {
      const detail =
        err?.response?.data?.detail || err?.message || "Airtable write failed";
      setAutofill({ status: "error", error: detail });
      toast.error(detail);
    }
  };

  const pitchBody = useMemo(
    () => buildPitchBody({ agent_name: agent.name, brokerage: agent.brokerage, sender_name: senderName }),
    [agent.name, agent.brokerage, senderName],
  );
  const mailto =
    agent.outreach_ready && agent.email
      ? `mailto:${encodeURIComponent(agent.email)}?subject=${encodeURIComponent(PITCH_SUBJECT)}&body=${encodeURIComponent(pitchBody)}`
      : null;
  const tel =
    agent.outreach_ready && agent.phone
      ? `tel:${(agent.phone || "").replace(/[^\d+]/g, "")}`
      : null;
  return (
    <div
      data-testid={`agent-row-${agent.id}`}
      data-fresh={agent.is_freshly_actionable ? "true" : "false"}
      className="bh-surface rounded-md p-4"
      style={{
        border: agent.is_freshly_actionable ? "1px solid var(--bh-brass)" : "1px solid var(--bh-hair)",
        background: agent.is_freshly_actionable ? "var(--bh-brass-mute)" : "var(--bh-surface)",
      }}
    >
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <Users size={13} className="text-[var(--bh-brass)] shrink-0" />
            <div
              className="font-display text-[16px] font-semibold text-[var(--bh-ink)] leading-tight truncate"
              data-testid={`agent-row-name-${agent.id}`}
            >
              {agent.name || "Unnamed agent"}
            </div>
            {agent.is_freshly_actionable && <FreshContactBadge testId={`agent-fresh-${agent.id}`} />}
            <DaysOnTable days={agent.days_on_table} testId={`agent-days-${agent.id}`} />
          </div>
          {agent.brokerage && (
            <div className="mt-0.5 text-[12px] text-[var(--bh-ink-3)] truncate">
              {agent.brokerage}
            </div>
          )}
          {hasExisting && (
            <div className="mt-1 flex items-center gap-3 text-[11px] text-[var(--bh-ink-2)] flex-wrap">
              {agent.email && (
                <span className="inline-flex items-center gap-1">
                  <Mail size={10} strokeWidth={1.75} /> {agent.email}
                </span>
              )}
              {agent.phone && (
                <span className="inline-flex items-center gap-1">
                  <Phone size={10} strokeWidth={1.75} /> {agent.phone}
                </span>
              )}
            </div>
          )}
        </div>
        <GateChip ready={agent.outreach_ready} gate={agent.outreach_gate} />
      </div>

      {agent.why_target && (
        <div className="mt-3 text-[12.5px] text-[var(--bh-ink-2)] leading-snug bh-surface-2 rounded-sm p-2.5">
          <span className="mono text-[9.5px] uppercase tracking-widest text-[var(--bh-ink-mute)] mr-1.5">
            Why:
          </span>
          {agent.why_target}
        </div>
      )}

      {agent.outreach_ready ? (
        <div className="mt-3 flex items-center gap-2 flex-wrap">
          {mailto && (
            <a
              href={mailto}
              data-testid={`agent-mailto-${agent.id}`}
              className="inline-flex items-center gap-1.5 h-11 px-4 rounded-md text-[13px] font-semibold border"
              style={{
                background: "var(--bh-brass)",
                color: "var(--bh-surface)",
                borderColor: "var(--bh-brass)",
              }}
            >
              <Mail size={13} strokeWidth={2} /> Send pitch email
            </a>
          )}
          {tel && (
            <a
              href={tel}
              data-testid={`agent-call-${agent.id}`}
              className="inline-flex items-center gap-1.5 h-11 px-4 rounded-md text-[13px] font-semibold border"
              style={{
                background: "var(--bh-surface)",
                color: "var(--bh-ink-2)",
                borderColor: "var(--bh-hair-strong)",
              }}
            >
              <Phone size={13} strokeWidth={2} /> Call {agent.phone}
            </a>
          )}
          {!mailto && !tel && (
            <span className="text-[11px] text-[var(--bh-ink-mute)] italic">
              Outreach unlocked but no contact yet.
            </span>
          )}
        </div>
      ) : (
        <div
          className="mt-3 flex items-center gap-1.5 text-[11px] text-[var(--bh-ink-3)]"
          data-testid={`agent-locked-note-${agent.id}`}
        >
          <Lock size={10} strokeWidth={1.75} />
          {agent.contact_enrichment_status || "Waiting on contact enrichment"} · pitch preview only
        </div>
      )}

      <PitchPreview agent={agent} senderName={senderName} />

      <div className="mt-3 pt-3 border-t bh-hairline flex items-center justify-end">
        <button
          type="button"
          onClick={onToggleResearch}
          data-testid={`agent-research-toggle-${agent.id}`}
          className="inline-flex items-center gap-1 text-[11px] font-medium text-[var(--bh-ink-3)] hover:text-[var(--bh-brass)]"
        >
          <Sparkles size={11} strokeWidth={1.75} />
          {researchOpen ? "Hide research" : "Research this agent"}
        </button>
      </div>
      {researchOpen && (
        <div className="mt-2 space-y-2" data-testid={`agent-research-panel-${agent.id}`}>
          <ResearchPanel
            researchType="re_agent_background"
            recordId={agent.id}
            query={`Real estate agent in New Orleans. Name: ${agent.name || "(unknown)"}. Brokerage: ${agent.brokerage || "(unknown)"}. Target notes: ${agent.why_target || "(none)"}. Find verified public business email + phone (brokerage site / their own site / Realtor.com / Zillow profile — no personal-looking numbers), recent NOLA listings, approximate 12-month sold volume, brokerage tenure, and whether they specialize in flips / historic renos / higher-end listings. Cite every source URL.`}
            label="Look up this agent"
            hint="Public listings + verified business contact + deal volume with citations."
            testId={`research-agent-${agent.id}`}
            onResult={handleResearchResult}
          />

          {(extracted.email || extracted.phone) && (
            <div
              className="rounded-md border bh-hairline p-3 space-y-2"
              style={{ background: "var(--bh-surface-2)" }}
              data-testid={`agent-autofill-${agent.id}`}
            >
              <div className="flex items-center gap-1.5">
                <UploadCloud size={12} className="text-[var(--bh-brass)]" />
                <span className="bh-eyebrow" style={{ color: "var(--bh-brass)" }}>
                  Auto-fill contact
                </span>
                <span className="ml-auto text-[10px] mono uppercase tracking-widest text-[var(--bh-ink-mute)]">
                  writes to Airtable
                </span>
              </div>
              <p className="text-[11.5px] text-[var(--bh-ink-3)] leading-relaxed">
                Extracted from Perplexity's answer. Edit before sending —
                nothing writes until you tap Send. GEAUXleads only touches
                Email + Phone; the Outreach Gate stays Claude's.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <label className="text-[11px] text-[var(--bh-ink-mute)]">
                  Email
                  <input
                    type="email"
                    value={extracted.email}
                    onChange={(e) => setExtracted((v) => ({ ...v, email: e.target.value }))}
                    placeholder="name@brokerage.com"
                    data-testid={`agent-autofill-email-${agent.id}`}
                    className="mt-1 w-full h-9 px-2 rounded-sm bg-[var(--bh-surface)] border bh-hairline text-[12.5px] text-[var(--bh-ink)]"
                  />
                </label>
                <label className="text-[11px] text-[var(--bh-ink-mute)]">
                  Phone
                  <input
                    type="tel"
                    value={extracted.phone}
                    onChange={(e) => setExtracted((v) => ({ ...v, phone: e.target.value }))}
                    placeholder="(504) 555-1212"
                    data-testid={`agent-autofill-phone-${agent.id}`}
                    className="mt-1 w-full h-9 px-2 rounded-sm bg-[var(--bh-surface)] border bh-hairline text-[12.5px] text-[var(--bh-ink)]"
                  />
                </label>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={sendToAirtable}
                  disabled={autofill.status === "sending" || autofill.status === "done"}
                  data-testid={`agent-autofill-send-${agent.id}`}
                  className="inline-flex items-center gap-1.5 h-11 px-4 rounded-md text-[13px] font-semibold border disabled:opacity-60"
                  style={{
                    background: "var(--bh-brass)",
                    color: "var(--bh-surface)",
                    borderColor: "var(--bh-brass)",
                  }}
                >
                  {autofill.status === "done" ? (
                    <>
                      <Check size={13} strokeWidth={2} /> Sent
                    </>
                  ) : autofill.status === "sending" ? (
                    "Sending…"
                  ) : (
                    <>
                      <UploadCloud size={13} strokeWidth={2} /> Send to Airtable
                    </>
                  )}
                </button>
                {autofill.status === "error" && (
                  <span className="text-[11px]" style={{ color: "#a67055" }}>
                    {autofill.error}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const STATUS_TABS = [
  { key: "all", label: "All" },
  { key: "ready", label: "Ready to pitch" },
  { key: "locked", label: "Locked" },
];

const DiscoveryRealEstateAgents = () => {
  const [status, setStatus] = useState("all");
  const [state, setState] = useState({ loading: true, items: [], counts: {} });
  const [senderName, setSenderName] = useState("Ryan");
  const [sortDir, setSortDir] = useState("fresh");
  const [researchOpenId, setResearchOpenId] = useState(null);

  useEffect(() => {
    // Sender name comes from the user settings so the pitch signs off correctly.
    let mounted = true;
    api.getUserSettings()
      .then((s) => mounted && s?.sender_name && setSenderName(s.sender_name))
      .catch(() => { /* keep default */ });
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    let mounted = true;
    setState((s) => ({ ...s, loading: true }));
    api.discoveryRealEstateAgents(status)
      .then((r) => mounted && setState({
        loading: false,
        items: r?.items || [],
        counts: r?.status_counts || {},
      }))
      .catch(() => mounted && setState({ loading: false, items: [], counts: {} }));
    return () => { mounted = false; };
  }, [status]);

  const tabCount = (key) => state.counts?.[key] ?? 0;
  const sortedItems = useMemo(() => sortByDays(state.items, sortDir), [state.items, sortDir]);

  return (
    <div className="px-4 lg:px-8 py-6" data-testid="discovery-agents-page">
      <Link
        to="/"
        className="inline-flex items-center gap-1 text-[12px] text-[var(--bh-ink-mute)] hover:text-[var(--bh-ink)] mb-4"
      >
        <ArrowLeft size={13} /> Home
      </Link>

      <DiscoveryNav />

      <div className="mono text-[10px] uppercase tracking-widest text-[var(--bh-brass)]">
        Discovery · Real estate agents
      </div>
      <h1
        className="mt-1 font-display text-[28px] font-bold text-[var(--bh-ink)] tracking-tight"
        data-testid="discovery-agents-headline"
      >
        Photo-ready bathroom · pre-listing pitch
      </h1>
      <p className="mt-1 text-[13px] text-[var(--bh-ink-3)] max-w-3xl">
        Top-rated New Orleans agents Claude curated for the &ldquo;before it hits MLS&rdquo;
        pitch. Every row previews the exact email that will send once
        Airtable&apos;s Outreach Gate unlocks — until then, they&apos;re read-only.
        No message opens without the gate.
      </p>

      {/* Status tabs + sort */}
      <div className="mt-5 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-1.5 flex-wrap" data-testid="discovery-agents-tabs">
          {STATUS_TABS.map((tab) => {
            const n = tabCount(tab.key);
            const active = status === tab.key;
            return (
              <button
                key={tab.key}
                type="button"
                onClick={() => setStatus(tab.key)}
                data-testid={`discovery-agents-tab-${tab.key}`}
                className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md text-[11.5px] font-medium border transition-colors"
                style={{
                  background: active ? "var(--bh-brass)" : "var(--bh-surface)",
                  color: active ? "var(--bh-surface)" : "var(--bh-ink-2)",
                  borderColor: active ? "var(--bh-brass)" : "var(--bh-hair-strong)",
                }}
              >
                {tab.label} <span className="tabular-nums opacity-70">{n}</span>
              </button>
            );
          })}
        </div>
        <DiscoverySortToggle value={sortDir} onChange={setSortDir} testId="discovery-agents-sort" />
      </div>

      {/* List */}
      {state.loading ? (
        <div className="mt-6 text-[13px] text-[var(--bh-ink-3)]">Loading agent queue…</div>
      ) : state.items.length === 0 ? (
        <div
          className="mt-6 bh-surface rounded-md p-6 text-[13px] text-[var(--bh-ink-3)] text-center"
          data-testid="discovery-agents-empty"
        >
          {status === "ready"
            ? "No agents are cleared to pitch yet. Claude will flip the Outreach Gate on the Airtable side once contact info lands."
            : "No agents match this filter."}
        </div>
      ) : (
        <div className="mt-5 space-y-3">
          {sortedItems.map((agent) => (
            <Row
              key={agent.id}
              agent={agent}
              senderName={senderName}
              researchOpen={researchOpenId === agent.id}
              onToggleResearch={() =>
                setResearchOpenId((cur) => (cur === agent.id ? null : agent.id))
              }
              onEnriched={(updated) => {
                setState((prev) => ({
                  ...prev,
                  items: prev.items.map((a) => (a.id === updated.id ? { ...a, ...updated } : a)),
                }));
              }}
            />
          ))}
        </div>
      )}

      <div className="mt-5 text-[10.5px] text-[var(--bh-ink-mute)] leading-snug">
        <ExternalLink size={9} className="inline mr-1 -mt-0.5" />
        Outreach Gate is owned by Airtable + Make. GEAUXleads never sends
        without the gate cleared.
      </div>
    </div>
  );
};

export default DiscoveryRealEstateAgents;
