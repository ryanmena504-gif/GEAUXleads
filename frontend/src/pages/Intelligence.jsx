import React from "react";
import TopHeader from "@/components/TopHeader";
import PreviewNotice from "@/components/PreviewNotice";
import { Radar, TrendingUp, Map, LineChart } from "lucide-react";

const Tile = ({ icon: Icon, title, body }) => (
  <div className="bh-surface rounded p-5">
    <div className="w-9 h-9 rounded bh-surface-2 flex items-center justify-center">
      <Icon size={16} className="text-amber-400" />
    </div>
    <div className="mt-3 font-display text-lg font-semibold text-neutral-100">
      {title}
    </div>
    <p className="mt-1 text-sm text-neutral-400 leading-relaxed">{body}</p>
  </div>
);

const Intelligence = () => (
  <>
    <TopHeader
      pageTitle="Intelligence"
      subtitle="Patterns, markets, and forecasts"
    />
    <div className="px-4 lg:px-8 py-6 space-y-6">
      <section className="bh-surface rounded p-6 border-t border-t-amber-500/60">
        <div className="mono text-[10px] uppercase tracking-widest text-amber-400">
          Coming soon
        </div>
        <h2 className="mt-2 font-display text-3xl font-bold text-neutral-100 tracking-tight max-w-2xl">
          Where is the next wave of demand forming?
        </h2>
        <p className="mt-3 text-sm text-neutral-400 max-w-2xl leading-relaxed">
          Weekly permit velocity, neighborhood heat maps, category trend lines,
          and a running record of which signal types convert best for you.
        </p>
      </section>

      <section className="grid md:grid-cols-2 xl:grid-cols-4 gap-3">
        <Tile
          icon={LineChart}
          title="Signal Trends"
          body="Volume by source over time — spot the permit spikes before your competitors do."
        />
        <Tile
          icon={Map}
          title="Neighborhood Heat"
          body="Which ZIPs are lighting up this week and how they compare to your win-rate profile."
        />
        <Tile
          icon={TrendingUp}
          title="Win-Rate Explainer"
          body="Which project types, sizes, and sources you actually close best."
        />
        <Tile
          icon={Radar}
          title="Radar"
          body="Anomaly detection on the permit feed — surface unusual filings the moment they appear."
        />
      </section>

      <section className="bh-surface rounded p-6" data-testid="intelligence-mock">
        {/* Placeholder values rather than plausible ones: a market figure that
            looks real is indistinguishable from a live one at a glance. */}
        <PreviewNotice detail="The market metrics below are not yet computed. Labels show what this panel will report once the permit feed is aggregated.">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              "Permits filed",
              "Residential share",
              "Median value",
              "Owner-filed %",
            ].map((label) => (
              <div key={label}>
                <div className="mono text-[10px] uppercase tracking-widest text-neutral-500">
                  {label}
                </div>
                <div className="mt-1 font-display text-3xl font-bold text-neutral-700 tabular-nums">
                  —
                </div>
                <div className="mono text-[10px] text-neutral-600 mt-0.5">
                  Not yet measured
                </div>
              </div>
            ))}
          </div>
        </PreviewNotice>
      </section>
    </div>
  </>
);

export default Intelligence;
