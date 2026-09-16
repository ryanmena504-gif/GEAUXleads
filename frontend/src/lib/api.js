import axios from "axios";

const BASE = process.env.REACT_APP_BACKEND_URL;
export const API = `${BASE}/api`;

const client = axios.create({ baseURL: API });

export const api = {
  listOpportunities: (params = {}) =>
    client.get("/opportunities", { params }).then((r) => r.data),
  getOpportunity: (id) =>
    client.get(`/opportunities/${id}`).then((r) => r.data),
  summary: () => client.get("/opportunities/summary").then((r) => r.data),
  missions: () => client.get("/opportunities/missions").then((r) => r.data),
  pipeline: () => client.get("/opportunities/pipeline").then((r) => r.data),
  recent: (limit = 10) =>
    client.get("/opportunities/recent", { params: { limit } }).then((r) => r.data),
  top: (limit = 10) =>
    client.get("/opportunities/top", { params: { limit } }).then((r) => r.data),
  updateStatus: (id, status) =>
    client.patch(`/opportunities/${id}/status`, { status }).then((r) => r.data),
  updateMission: (id, daily_mission) =>
    client
      .patch(`/opportunities/${id}/mission`, { daily_mission })
      .then((r) => r.data),
  updateFields: (id, patch) =>
    client.patch(`/opportunities/${id}/fields`, patch).then((r) => r.data),
  recordResult: (id, payload) =>
    client.post(`/opportunities/${id}/result`, payload).then((r) => r.data),
  addActivity: (id, type, note) =>
    client
      .post(`/opportunities/${id}/activity`, { type, note })
      .then((r) => r.data),
  config: () => client.get("/config").then((r) => r.data),
  schema: () => client.get("/schema").then((r) => r.data),
  cacheStatus: () => client.get("/cache-status").then((r) => r.data),
  refreshCache: () => client.post("/cache-refresh").then((r) => r.data),
  laneBreakdown: () =>
    client.get("/opportunities/lanes").then((r) => r.data),
  topByLane: (limit = 4) =>
    client.get("/opportunities/top-by-lane", { params: { limit } }).then((r) => r.data),
  leadsNextBestAction: () =>
    client.get("/leads/next-best-action").then((r) => r.data),
  leadsAction: (id, body) =>
    client.post(`/leads/${id}/action`, body).then((r) => r.data),
  leadsUpdateMessage: (id, message) =>
    client.patch(`/leads/${id}/message`, { message }).then((r) => r.data),

  // Perplexity research (feature-flagged; returns 503 when key missing)
  research: (payload) =>
    client.post("/research", payload).then((r) => r.data),
  researchStatus: () =>
    axios.get(`${BASE}/api/research/status`).then((r) => r.data),

  // Twilio Number Lookup — read-only carrier / line type / caller name.
  // Feature-flagged; returns 503 when TWILIO_ACCOUNT_SID / TOKEN missing.
  twilioLookup: (number) =>
    axios
      .get(`${BASE}/api/lookup/twilio/${encodeURIComponent(number)}`)
      .then((r) => r.data),
  twilioLookupStatus: () =>
    axios.get(`${BASE}/api/lookup/twilio/status`).then((r) => r.data),

  // Draft a Note — playbooks (read-only Airtable) + drafts (Mongo-backed)
  listPlaybooks: () =>
    client.get("/message-playbooks").then((r) => r.data),
  updatePlaybook: (id, patch) =>
    client.patch(`/message-playbooks/${id}`, patch).then((r) => r.data),
  listDrafts: (opportunity_id) =>
    client.get("/drafts", { params: { opportunity_id } }).then((r) => r.data),
  listDraftQueue: (status = "Ready for Ryan review", limit = 200) =>
    client
      .get("/drafts/queue", { params: { status, limit } })
      .then((r) => r.data),
  createDraft: (payload) =>
    client.post("/drafts", payload).then((r) => r.data),
  getDraft: (id) => client.get(`/drafts/${id}`).then((r) => r.data),
  updateDraft: (id, patch) =>
    client.patch(`/drafts/${id}`, patch).then((r) => r.data),
  deleteDraft: (id) => client.delete(`/drafts/${id}`).then((r) => r.data),

  logHandoff: (opp_id, payload) =>
    client
      .post(`/opportunities/${opp_id}/handoff`, payload)
      .then((r) => r.data),
  listHandoffs: (opp_id, limit = 50) =>
    client
      .get(`/opportunities/${opp_id}/handoffs`, { params: { limit } })
      .then((r) => r.data),

  // Follow-ups + monthly KPIs — surface the leads Ryan touched but never
  // nudged, and show how the pipeline is trending.
  dueFollowUps: (limit = 20) =>
    client.get("/follow-ups/due", { params: { limit } }).then((r) => r.data),
  monthlyKpis: () => client.get("/kpis/monthly").then((r) => r.data),

  // Learning loop — top patterns the app has learned from Ryan's confirmed
  // outcomes. Read-only. Silent if there aren't enough observations yet.
  learningInsights: (limit = 3) =>
    client.get("/learning/insights", { params: { limit } }).then((r) => r.data),

  // Reverse Lookup — matches an inbound call/text number back to a lead.
  lookupByPhone: (number) =>
    client.get(`/opportunities/by-phone/${encodeURIComponent(number)}`).then((r) => r.data),

  // Landlord Portfolio Roll-Up — sibling properties owned by the same
  // landlord (matched by shared email > phone tail > name). Returns
  // { portfolio: [], match_key, count } — safe to call on non-landlord
  // records (returns empty).
  landlordPortfolio: (opp_id) =>
    client.get(`/opportunities/${opp_id}/portfolio`).then((r) => r.data),

  // Morning brief — same content that ships in the 7am email. Used by the
  // in-app MorningBrief panel and by Settings' "test send" button.
  morningBrief: () =>
    client.get("/morning-brief/preview").then((r) => r.data),
  sendMorningBriefNow: () =>
    client.post("/morning-brief/send-now").then((r) => r.data),

  // User preferences — sender email that appears on mailto: drafts, etc.
  getUserSettings: () =>
    client.get("/settings/user").then((r) => r.data),
  updateUserSettings: (patch) =>
    client.patch("/settings/user", patch).then((r) => r.data),

  // Property Manager Discovery Queue — Claude owns Review Status on the
  // Airtable side. Bloodhound is a strictly-read viewer. Default filter
  // is "worth_a_look"; pass status: "all" to see every record.
  discoveryPropertyManagers: (status = "worth_a_look") =>
    client.get("/discovery/property-managers", { params: { status } }).then((r) => r.data),

  // Real Estate Agent Outreach — 10 curated agents for the pre-listing
  // "photo-ready bathroom" pitch. Outreach Gate on the Airtable side
  // controls whether a mailto/sms can render — if Locked, the app shows
  // the pitch as read-only preview.
  discoveryRealEstateAgents: (status = "all") =>
    client.get("/discovery/real-estate-agents", { params: { status } }).then((r) => r.data),

  // Auto-fill contact — the ONE Discovery-side write in the app.
  // Writes verified email/phone to the Real Estate Agent Outreach table.
  // Never touches governed fields (Outreach Gate is still Claude's).
  enrichRealEstateAgentContact: (recordId, payload) =>
    client
      .post(`/discovery/real-estate-agents/${encodeURIComponent(recordId)}/enrich`, payload)
      .then((r) => r.data),

  // Bloodhound-local archive (UI hide only — never mutates Airtable/Make)
  listLocalArchive: (feed) =>
    client.get(`/local-state/${feed}/archived`).then((r) => r.data),
  archiveLocal: (feed, recordIds) =>
    client.post(`/local-state/${feed}/archive`, { record_ids: recordIds }).then((r) => r.data),
  unarchiveLocal: (feed, recordIds) =>
    client.post(`/local-state/${feed}/unarchive`, { record_ids: recordIds }).then((r) => r.data),

  // CSV exports (server-generated; whitelist per feed; formula-injection safe)
  csvOpportunitiesUrl: () => `${BASE}/api/exports/opportunities.csv`,
  csvDiscoveryUrl: (feed) => `${BASE}/api/exports/discovery/${feed}.csv`,

  // Landlords — 63 STR-license property owners, no phone/email yet.
  // Bloodhound generates printable letters for USPS drop; ids param
  // (comma-separated) pulls an exact batch for the print view.
  discoveryLandlords: ({ status = "not_contacted", ids = null } = {}) =>
    client.get("/discovery/landlords", {
      params: { status, ids: ids ? ids.join(",") : undefined },
    }).then((r) => r.data),

  // Investor Intelligence — real estate investors / LLC entities tracking
  // multi-property portfolios. Bloodhound is a read-only viewer.
  discoveryInvestors: (status = "all") =>
    client.get("/discovery/investors", { params: { status } }).then((r) => r.data),
};
