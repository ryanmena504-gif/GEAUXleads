import React from "react";
import { TrendingUp, TrendingDown, Minus, Brain } from "lucide-react";

export const PredictiveScoreBadge = ({ prediction, showDetails = false }) => {
  if (!prediction) return null;

  const { conversion_probability, expected_value, confidence, feature_importance } = prediction;
  const prob = Math.round((conversion_probability || 0) * 100);
  const ev = expected_value;

  let color = "text-neutral-400";
  let bg = "bg-white/[0.03]";
  let Icon = Minus;
  if (prob >= 70) { color = "text-emerald-400"; bg = "bg-emerald-500/10"; Icon = TrendingUp; }
  else if (prob >= 40) { color = "text-amber-400"; bg = "bg-amber-500/10"; Icon = TrendingUp; }
  else { color = "text-red-400"; bg = "bg-red-500/10"; Icon = TrendingDown; }

  return (
    <div className={`rounded-md border border-white/10 ${bg} p-3`} data-testid="predictive-score">
      <div className="flex items-center gap-2 mb-2">
        <Brain size={13} className={color} />
        <span className="mono text-[10px] uppercase tracking-widest text-neutral-500">
          AI Prediction · {confidence} confidence
        </span>
      </div>
      <div className="flex items-baseline gap-3">
        <div className={`font-display text-3xl font-bold ${color}`}>{prob}%</div>
        <div className="text-sm text-neutral-400">conversion probability</div>
      </div>
      {ev !== null && ev !== undefined && (
        <div className="mt-1 text-sm text-neutral-300">
          Expected value: <span className="font-mono text-amber-400">${ev.toLocaleString()}</span>
        </div>
      )}
      {showDetails && feature_importance && feature_importance.length > 0 && (
        <div className="mt-3 space-y-1.5 border-t border-white/10 pt-2">
          <div className="mono text-[9px] uppercase tracking-widest text-neutral-500">Top drivers</div>
          {feature_importance.slice(0, 4).map((f) => (
            <div key={f.feature} className="flex items-center justify-between text-xs">
              <span className="text-neutral-300 capitalize">{f.feature.replace(/_/g, " ")}</span>
              <span className={`font-mono ${f.lift > 1 ? "text-emerald-400" : "text-neutral-500"}`}>
                {f.lift > 1 ? "+" : ""}{Math.round((f.lift - 1) * 100)}%
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default PredictiveScoreBadge;
