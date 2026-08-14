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
      <h2 className="font-display text-lg font-semibold text-neutral-100">{title}</h2>
    </div>
    {children}
  </section>
);

const Stat = ({ label, value, sub }) => (
  <div className="p-3 rounded bg-white/[0.03] border border-white/5">
    <div className="mono text-[9px] uppercase tracking-widest text-neutral-500 mb-1">{label}</div>
    <div className="font-display text-xl font-bold text-neutral-100">{value ?? "—"}</div>
    {sub && <div className="text-[10px] text-neutral-500 mt-0.5">{sub}</div>}
  </div>
);

export default function Intelligence() {
  const [market, setMarket] = useState(null);
  const [predictions, setPredictions] = useState(null);
  const [replies, setReplies] = useState(null);
  const [modelStatus, setModelStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [training, setTraining] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [m, p, r, ms] = await Promise.all([
        api.marketOverview(),
        api.predictiveTop(10),
        api.leadsWithReplies(),
        api.predictiveStatus(),
      ]);
      setMarket(m);
      setPredictions(p);
      setReplies(r);
      setModelStatus(ms);
    } catch (err) {
      toast.error("Failed to load intelligence data");
    } finally {
      setLoading(false);
    }
  };

  const train = async () => {
    setTraining(true);
    try {
      await api.predictiveTrain();
      toast.success("Model retrained");
      await load();
    } catch (err) {
      toast.error("Training failed");
    } finally {
      setTraining(false);
    }
  };

  useEffect(() => { load(); }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96 text-neutral-400 gap-2">
        <Loader2 size={16} className="animate-spin" /> Loading intelligence...
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-20">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-bold text-neutral-100">Intelligence Center</h1>
        <button onClick={load} className="text-xs text-amber-400 hover:text-amber-300 inline-flex items-center gap-1.5">
          <RefreshCw size={11} /> Refresh
        </button>
      </div>

      <Section title="Predictive Model" icon={Brain}>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-4 text-sm text-neutral-400">
            <span>Version: <span className="text-neutral-200 font-mono">{modelStatus?.model_version}</span></span>
            <span>Training: <span className="text-neutral-200 font-mono">{modelStatus?.training_size}</span></span>
            <span>Baseline: <span className="text-neutral-200 font-mono">{Math.round((modelStatus?.baseline_rate || 0) * 100)}%</span></span>
          </div>
          <button onClick={train} disabled={training}
            className="h-8 px-3 rounded bg-amber-500 text-neutral-950 hover:bg-amber-400 text-xs font-semibold disabled:opacity-50 inline-flex items-center gap-1.5">
            {training ? <Loader2 size={12} className="animate-spin" /> : <Brain size={12} />}
            {training ? "Training..." : "Retrain Model"}
          </button>
        </div>

        {predictions?.predictions && (
          <div className="space-y-3">
            <div className="mono text-[10px] uppercase tracking-widest text-neutral-500">Top by Expected Value</div>
            <div className="grid gap-3 md:grid-cols-2">
              {predictions.predictions.map((p) => (
                <PredictiveScoreBadge key={p.lead_id} prediction={p} showDetails />
              ))}
            </div>
          </div>
        )}
      </Section>

      {market && !market.error && (
        <Section title="Market Intelligence" icon={MapPin}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
            <Stat label="Total Pipeline" value={market.revenue?.total_pipeline_estimate ? `$${Math.round(market.revenue.total_pipeline_estimate).toLocaleString()}` : null} />
            <Stat label="Avg Deal" value={market.revenue?.average_deal_size ? `$${Math.round(market.revenue.average_deal_size).toLocaleString()}` : null} />
            <Stat label="Win Rate" value={`${market.pipeline_health?.win_rate}%`} sub={`${market.pipeline_health?.total_records} total`} />
            <Stat label="Trend" value={market.permit_velocity?.trend} sub={`${market.permit_velocity?.change_percent > 0 ? "+" : ""}${market.permit_velocity?.change_percent}%`} />
          </div>

          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 mb-2">Hot Zones</div>
              <div className="space-y-2">
                {market.geography?.hot_zones?.map((z) => (
                  <div key={z.city} className="flex items-center justify-between p-2.5 rounded bg-white/[0.02] border border-white/5">
                    <div>
                      <div className="text-sm text-neutral-200 font-medium">{z.city}</div>
                      <div className="text-[10px] text-neutral-500">{z.permit_count} permits</div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm text-amber-400 font-mono">
                        {z.total_estimated_value ? `$${Math.round(z.total_estimated_value).toLocaleString()}` : "—"}
                      </div>
                      <div className="text-[10px] text-neutral-500">total value</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 mb-2">Top Project Types</div>
              <div className="space-y-2">
                {market.project_types?.slice(0, 6).map((pt) => (
                  <div key={pt.type} className="flex items-center justify-between p-2.5 rounded bg-white/[0.02] border border-white/5">
                    <div className="text-sm text-neutral-200">{pt.type}</div>
                    <div className="flex items-center gap-2">
                      <div className="w-24 h-1.5 rounded-full bg-white/[0.05] overflow-hidden">
                        <div className="h-full bg-amber-500/60 rounded-full" style={{ width: `${pt.percentage}%` }} />
                      </div>
                      <span className="text-xs text-neutral-400 font-mono w-8 text-right">{pt.percentage}%</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Section>
      )}

      {replies?.classifications && replies.classifications.length > 0 && (
        <Section title="Reply Intelligence" icon={MessageSquare}>
          <div className="space-y-3">
            {replies.classifications.slice(0, 5).map((c) => (
              <ReplyIntelligencePanel key={c.lead_id} classification={c} />
            ))}
          </div>
        </Section>
      )}
    </div>
  );
}
