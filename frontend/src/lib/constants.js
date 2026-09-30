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
  landlord: "Landlords",
  non_permit: "Projects to Watch",
};

// Lead sources — the exact option values of the Airtable Leads "Source"
// field (the backend passes them through unchanged, and the Source filter
// matches them exactly). "Other " really has a trailing space in Airtable.
export const SOURCES = [
  "Permit Issued",
  "Permit",
  "Property Sale Record",
  "Website",
  "Google maps",
  "Instagram",
  "Referral",
  "Manuals research",
  "Other ",
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
