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

  // Manual result-tracking — Ryan taps AFTER a real-world touch.
  recordResult: (opp_id, result, note) =>
    client
      .post(`/opportunities/${opp_id}/result`, { result, note })
      .then((r) => r.data),

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

  // User preferences — sender email that appears on mailto: drafts, etc.
  getUserSettings: () =>
    client.get("/settings/user").then((r) => r.data),
  updateUserSettings: (patch) =>
    client.patch("/settings/user", patch).then((r) => r.data),

  // AI Contact Enrichment — Gemini + Google Search grounding, manual only.
  enrichmentStatus: () =>
    client.get("/enrichment/status").then((r) => r.data),
  runEnrichment: () =>
    client.post("/enrichment/run").then((r) => r.data),
  enrichLead: (opp_id) =>
    client.post(`/opportunities/${opp_id}/enrich`).then((r) => r.data),

  // Bloodhound learning loop — evidence-first, no invented probabilities.
  predictiveStatus: () =>
    client.get("/intelligence/predictive/status").then((r) => r.data),
  predictiveTrain: () =>
    client.post("/intelligence/predictive/train").then((r) => r.data),
  predictiveForOpp: (opp_id) =>
    client.get(`/intelligence/predictive/${opp_id}`).then((r) => r.data),
  predictiveTop: (limit = 20) =>
    client.get(`/intelligence/predictive/batch/top?limit=${limit}`).then((r) => r.data),
  marketOverview: () =>
    client.get("/intelligence/market").then((r) => r.data),
  classifyReply: (text, lead_id) =>
    client.post("/intelligence/reply/classify", { text, lead_id }).then((r) => r.data),
  leadsWithReplies: () =>
    client.get("/intelligence/reply/leads-with-replies").then((r) => r.data),
};
