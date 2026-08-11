import React from "react";

const laneLabels = {
  partner: "Person to know",
  project: "Project",
  watch: "Project to watch",
};

const LaneBadge = ({ lane }) => (
  <span
    data-testid={`lane-badge-${lane || "unknown"}`}
    className="inline-flex rounded border border-sky-500/25 bg-sky-500/10 px-2 py-0.5 text-[11px] font-medium text-sky-300"
  >
    {laneLabels[lane] || "Project"}
  </span>
);

export default LaneBadge;
