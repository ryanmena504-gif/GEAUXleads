import React from "react";
import { FlaskConical } from "lucide-react";

/**
 * Marks illustrative content for unbuilt features. Anything rendered inside
 * must be inert: no record ids, no scoring inputs, no action handlers. See
 * docs/INTEGRATIONS.md.
 */
export const PreviewNotice = ({
  detail,
  children,
  testId = "preview-notice",
}) => (
  <div
    data-testid={testId}
    data-preview="true"
    className="rounded border border-dashed border-amber-500/30 bg-amber-500/[0.03] p-3"
  >
    <div className="flex items-center gap-2">
      <FlaskConical size={11} className="text-amber-400" />
      <span className="mono text-[9px] uppercase tracking-widest text-amber-300">
        Preview — not live data
      </span>
    </div>
    <p className="mt-1 text-[11px] text-neutral-500 leading-relaxed">
      {detail ||
        "Illustrative example of a planned feature. Nothing here is drawn from your records, and none of it feeds scoring, eligibility, or outreach decisions."}
    </p>
    {children ? <div className="mt-3">{children}</div> : null}
  </div>
);

export default PreviewNotice;
