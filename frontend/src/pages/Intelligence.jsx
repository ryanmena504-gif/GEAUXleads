import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Brain, MapPin, MessageSquare, RefreshCw, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import PredictiveScoreBadge from "@/components/PredictiveScoreBadge";
import ReplyIntelligencePanel from "@/components/ReplyIntelligencePanel";

const Section = ({ title, icon: Icon, children }) => (
  <section className="bh-surface rounded-lg border-t border-t-white/10 p-5">
    <div className="flex items-center gap-2 mb-4">
      {Icon && <Icon size={14} className="text-amber-400" />}
      <h2 className="font-display text-lg font-semibold text-neutral-100">
        {title}
      </h2>
    </div>
    {children}
  </section>
);

const Stat = ({ label, value, sub }) => (
  <div className="p-3 rounded bg-white/[0.03] border border-white/5">
    <div className="mono text-[9px] uppercase tracking-widest text-neutral-500 mb-1">
      {label}
    </div>
    <div className="font-display text-xl font-bold text-neutral-100">
      {value ?? "—"}
    </div>
    {sub && <div className="text-[10px] text-neutral-500 mt-0.5">{sub}</div>}
  </div>
);

export default function Intelligence() {
  const [market, setMarket] = useState(null);
  const [recommendations, setRecommendations] = useState(null);
  const [replies, setReplies] = useState(null);
  const [learning, setLearning] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [m, r, replyData, learningStatus] = await Promise.all([
        api.marketOverview(),
        api.predictiveTop(12),
        api.leadsWithReplies(),
        api.predictiveStatus(),
      ]);
      setMarket(m);
      setRecommendations(r);
      setReplies(replyData);
      setLearning(learningStatus);
    } catch {
      toast.error("Could not load Bloodhound’s learning view");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96 text-neutral-400 gap-2">
        <Loader2 size={16} className="animate-spin" /> Loading what Bloodhound
        is learning...
      </div>
    );
  }

  const outcomes = learning?.results_recorded || {};
  const resultCount = learning?.training_size || 0;

  return (
    <div className="space-y-6 pb-20">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-neutral-100">
            What Bloodhound is learning
          </h1>
          <p className="mt-1 text-sm text-neutral-400">
            Recommendations improve only from results you record. No guessed win
            rates and no automatic outreach.
          </p>
        </div>
        <button
          onClick={load}
          className="text-xs text-amber-400 hover:text-amber-300 inline-flex items-center gap-1.5"
        >
          <RefreshCw size={11} /> Refresh
        </button>
      </div>

      <Section title="Results that teach Bloodhound" icon={Brain}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat
            label="Confirmed results"
            value={resultCount}
            sub={
              learning?.learning_ready
                ? "Enough to look for early patterns"
                : "Still gathering your real outcomes"
            }
          />
          <Stat label="Replies" value={outcomes.replied || 0} />
          <Stat
            label="Estimates requested"
            value={outcomes.estimate_requested || 0}
          />
          <Stat label="Won work" value={outcomes.won || 0} />
        </div>
        <p className="mt-4 text-xs leading-relaxed text-neutral-400">
          {learning?.note}
        </p>
      </Section>

      {recommendations?.predictions?.length > 0 && (
        <Section title="What is worth your time" icon={Brain}>
          <div className="grid gap-3 md:grid-cols-2">
            {recommendations.predictions.map((recommendation) => (
              <PredictiveScoreBadge
                key={recommendation.lead_id}
                prediction={recommendation}
                showDetails
              />
            ))}
          </div>
        </Section>
      )}

      {market && !market.error && (
        <Section title="Where to keep watching" icon={MapPin}>
          <p className="mb-4 text-xs leading-relaxed text-neutral-400">
            This is a count of the public project signals already in Bloodhound.
            It is not a prediction of revenue.
          </p>
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 mb-2">
                Places with the most signals
              </div>
              <div className="space-y-2">
                {market.geography?.top_cities?.slice(0, 5).map((city) => (
                  <div
                    key={city.city}
                    className="flex items-center justify-between p-2.5 rounded bg-white/[0.02] border border-white/5"
                  >
                    <div className="text-sm text-neutral-200 font-medium">
                      {city.city}
                    </div>
                    <div className="text-xs text-neutral-400">
                      {city.count} signals
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 mb-2">
                Types of work showing up
              </div>
              <div className="space-y-2">
                {market.project_types?.slice(0, 5).map((projectType) => (
                  <div
                    key={projectType.type}
                    className="flex items-center justify-between p-2.5 rounded bg-white/[0.02] border border-white/5"
                  >
                    <div className="text-sm text-neutral-200">
                      {projectType.type}
                    </div>
                    <div className="text-xs text-neutral-400">
                      {projectType.count} signals
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Section>
      )}

      {replies?.classifications?.length > 0 && (
        <Section title="Replies that need your attention" icon={MessageSquare}>
          <div className="space-y-3">
            {replies.classifications.slice(0, 5).map((classification) => (
              <ReplyIntelligencePanel
                key={classification.lead_id}
                classification={classification}
              />
            ))}
          </div>
        </Section>
      )}
    </div>
  );
}
