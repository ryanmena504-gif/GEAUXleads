import React, { useEffect, useState } from "react";
import { Brain, TrendingUp, TrendingDown, Sparkles } from "lucide-react";
import { api } from "@/lib/api";

/**
 * LearningStrip — a calm read-out of what the app has learned from the
 * outcomes Ryan explicitly confirmed. No LLM, no messaging, no writes.
 *
 *   • Fetches /api/learning/insights on mount.
 *   • Hides silently until at least MIN_TOTAL_OBSERVATIONS outcomes exist.
 *   • Shows up to 3 patterns ranked by |delta| × sqrt(sample size).
 *   • For each pattern: headline (governed field = value + lift phrase),
 *     the raw n/total, and the baseline rate for context.
 *
 * Placement: Home page, just below WonThisMonth. If insights are empty, a
 * small "learning starts after N more outcomes" strip renders instead so
 * Ryan understands why the panel is quiet.
 */

const InsightChip = ({ insight, index }) => {
  const isPositive = insight.focus_rate >= insight.baseline_rate;
  const TrendIcon = isPositive ? TrendingUp : TrendingDown;
  const tone = isPositive
    ? { fg: "var(--bh-olive)", bg: "var(--bh-olive-mute)", border: "rgba(107,122,85,0.32)" }
    : { fg: "var(--bh-brass-2)", bg: "var(--bh-brass-mute)", border: "var(--bh-hair-warm)" };
  return (
    <div
      data-testid={`learning-insight-${index}`}
      className="rounded-md border p-4 flex items-start gap-3 min-w-0"
      style={{ background: tone.bg, borderColor: tone.border }}
    >
      <div
        className="w-8 h-8 shrink-0 rounded-full flex items-center justify-center"
        style={{ background: "var(--bh-surface)", border: `1px solid ${tone.border}` }}
      >
        <TrendIcon size={13} strokeWidth={1.75} style={{ color: tone.fg }} />
      </div>
      <div className="min-w-0 flex-1">
        <div
          className="mono text-[10px] uppercase tracking-widest"
          style={{ color: tone.fg }}
        >
          {insight.kind === "reply_rate" ? "Reply pattern" : "Win pattern"}
        </div>
        <div
          className="mt-1 text-[13.5px] font-medium leading-snug"
          style={{ color: tone.fg }}
          data-testid={`learning-headline-${index}`}
        >
          {insight.headline}
        </div>
        <div className="mt-1 text-[11.5px] text-[var(--bh-ink-3)] leading-relaxed">
          {insight.detail}
        </div>
      </div>
    </div>
  );
};

const NotYetChip = ({ observations }) => {
  const totalOutcomes = (observations?.replies || 0) + (observations?.wins || 0);
  const remaining = Math.max(
    0,
    (observations?.min_required || 6) - Math.max(observations?.replies || 0, observations?.wins || 0),
  );
  return (
    <div
      data-testid="learning-not-yet"
      className="rounded-md border p-4 flex items-start gap-3"
      style={{
        background: "var(--bh-surface-2)",
        borderColor: "var(--bh-hair)",
      }}
    >
      <div
        className="w-8 h-8 shrink-0 rounded-full flex items-center justify-center"
        style={{
          background: "var(--bh-surface)",
          border: "1px solid var(--bh-hair)",
        }}
      >
        <Sparkles size={13} strokeWidth={1.75} className="text-[var(--bh-ink-mute)]" />
      </div>
      <div className="min-w-0">
        <div className="mono text-[10px] uppercase tracking-widest text-[var(--bh-ink-mute)]">
          Learning warm-up
        </div>
        <div className="mt-1 text-[13px] text-[var(--bh-ink-2)] leading-snug">
          The app starts surfacing patterns after {observations?.min_required || 6} confirmed outcomes.
          You have {totalOutcomes} so far{remaining > 0 ? ` — about ${remaining} more to go.` : "."}
        </div>
      </div>
    </div>
  );
};

export const LearningStrip = () => {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let mounted = true;
    api
      .learningInsights(3)
      .then((r) => mounted && setData(r))
      .catch(() => mounted && setFailed(true));
    return () => {
      mounted = false;
    };
  }, []);

  if (failed || !data) return null;

  const insights = data.insights || [];
  const observations = data.observations || {};
  const hasEnough =
    (observations.replies || 0) >= (observations.min_required || 6) ||
    (observations.wins || 0) >= (observations.min_required || 6);

  // Nothing meaningful to show at all — keep the dashboard calm.
  if (!hasEnough && insights.length === 0) {
    // If there is literally zero outcome data on file, don't even render the
    // warm-up strip — that would only add noise on a brand-new install.
    if ((observations.replies || 0) + (observations.wins || 0) === 0) return null;
    return (
      <section
        data-testid="section-learning-strip"
        className="rounded-md border bh-hairline p-1 space-y-2"
      >
        <SectionHeader />
        <NotYetChip observations={observations} />
      </section>
    );
  }

  if (insights.length === 0) return null;

  return (
    <section
      data-testid="section-learning-strip"
      className="space-y-2"
    >
      <SectionHeader observations={observations} baseline={data.baseline} />
      <div
        className={
          "grid gap-3 " +
          (insights.length === 1
            ? "grid-cols-1"
            : insights.length === 2
              ? "grid-cols-1 sm:grid-cols-2"
              : "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3")
        }
      >
        {insights.map((i, idx) => (
          <InsightChip key={idx} insight={i} index={idx} />
        ))}
      </div>
    </section>
  );
};

const SectionHeader = ({ observations, baseline }) => (
  <div className="flex items-center gap-2 flex-wrap" data-testid="learning-header">
    <Brain size={14} strokeWidth={1.75} className="text-[var(--bh-brass)]" />
    <span className="bh-eyebrow" style={{ color: "var(--bh-brass)" }}>
      What the app has learned
    </span>
    {baseline && (
      <span className="text-[11px] text-[var(--bh-ink-mute)] tabular-nums">
        {observations?.replies || 0} replies · baseline{" "}
        {Math.round((baseline.reply_rate || 0) * 100)}%
        {" · "}
        {observations?.wins || 0} closed · baseline{" "}
        {Math.round((baseline.win_rate || 0) * 100)}%
      </span>
    )}
  </div>
);

export default LearningStrip;
