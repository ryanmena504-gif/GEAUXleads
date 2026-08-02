import React from "react";
import TopHeader from "@/components/TopHeader";
import PreviewNotice from "@/components/PreviewNotice";
import { Network, Users, GitBranch, Handshake } from "lucide-react";

const Card = ({ icon: Icon, title, body }) => (
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

const Relationships = () => (
  <>
    <TopHeader
      pageTitle="Relationships"
      subtitle="The strongest path to every opportunity"
    />
    <div className="px-4 lg:px-8 py-6 space-y-6">
      <section
        data-testid="relationships-hero"
        className="bh-surface rounded p-6 border-t border-t-amber-500/60"
      >
        <div className="mono text-[10px] uppercase tracking-widest text-amber-400">
          Coming soon
        </div>
        <h2 className="mt-2 font-display text-3xl font-bold text-neutral-100 tracking-tight max-w-2xl">
          Who is the strongest relationship path to help win this opportunity?
        </h2>
        <p className="mt-3 text-sm text-neutral-400 max-w-2xl leading-relaxed">
          A living graph of your past clients, subs, suppliers, and mutual
          connections — Bloodhound will surface the warmest introduction path to
          any lead so you never have to cold-outreach a high-value opportunity again.
        </p>
      </section>

      <section className="grid md:grid-cols-2 xl:grid-cols-4 gap-3">
        <Card
          icon={Users}
          title="Past Clients"
          body="Every past client becomes a node. Bloodhound looks for shared streets, ZIPs, and property types with new opportunities."
        />
        <Card
          icon={Network}
          title="Mutual Connections"
          body="Find the one person who can send a text and turn a cold lead into a warm intro."
        />
        <Card
          icon={GitBranch}
          title="Referral Paths"
          body="Ranked intro paths with an estimated close-rate lift for each."
        />
        <Card
          icon={Handshake}
          title="Trade Partners"
          body="Track subs, architects, and suppliers who consistently push work your way."
        />
      </section>

      <section className="bh-surface rounded p-6" data-testid="relationships-mock">
        <PreviewNotice detail="Fictional names and a fictional intro path, shown to illustrate the intended layout. No relationship graph is computed yet.">
          <h3 className="font-display text-xl font-bold text-neutral-400">
            Example opportunity
          </h3>
          <div className="mt-4 flex items-center gap-3 flex-wrap">
            {["You", "Example contact", "Example owner"].map((n, i) => (
              <React.Fragment key={n}>
                <div className="bh-surface-2 rounded px-3 py-2 min-w-[140px]">
                  <div className="mono text-[9px] uppercase tracking-widest text-neutral-500">
                    Node {i + 1}
                  </div>
                  <div className="text-sm text-neutral-400">{n}</div>
                </div>
                {i < 2 && <div className="text-amber-400/50 mono text-xs">──▶</div>}
              </React.Fragment>
            ))}
          </div>
          <div className="mt-4 text-xs text-neutral-600">
            Each path will carry a computed confidence once the graph is built.
          </div>
        </PreviewNotice>
      </section>
    </div>
  </>
);

export default Relationships;
