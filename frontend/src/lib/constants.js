export const MISSIONS = [
  "Call Today",
  "Send Text",
  "Send Email",
  "Research First",
  "Visit Property",
  "Prepare Estimate",
  "Ask for Referral",
  "Follow Up",
  "Wait",
];

export const STATUSES = [
  "New",
  "Needs research",
  "Ready",
  "Conversation started",
  "Estimate requested",
  "Estimate sent",
  "Won",
  "Lost",
  "Disqualified",
];

export const BANDS = ["A", "B", "C", "D"];

// Only the governed Market Capture lane is exposed as a filter in All
// Projects. Partner and non-permit lanes stay as record-level context but
// are not visible operating buckets — the three governed queues own that.
export const LANES = [
  { key: "market_capture", label: "Projects" },
];

export const LANE_LABEL = {
  market_capture: "Projects",
  partner: "People to Know",
  non_permit: "Projects to Watch",
};

export const SOURCES = [
  "permit",
  "website",
  "referral",
  "nextdoor",
  "google_places",
  "manual",
];

export const PROJECT_TYPES = [
  "Whole-home renovation",
  "Kitchen + bath remodel",
  "Kitchen refresh",
  "Bath remodel",
  "Roof replacement",
  "Historic restoration",
  "ADU / accessory structure",
  "Outdoor structure",
  "Foundation / structural",
  "Bath + laundry remodel",
  "Addition / expansion",
  "Sunroom / addition",
  "Commercial rebuild",
  "Electrical",
];
