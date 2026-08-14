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
  leadsNextBestAction: () =>
    client.get("/leads/next-best-action").then((r) => r.data),
  leadsAction: (id, body) =>
    client.post(`/leads/${id}/action`, body).then((r) => r.data),
  leadsUpdateMessage: (id, message) =>
    client.patch(`/leads/${id}/message`, { message }).then((r) => r.data),
  leadsEligibility: (id) =>
    client.get(`/leads/${id}/eligibility`).then((r) => r.data),
  leadsReadiness: (id) =>
    client.get(`/leads/${id}/readiness`).then((r) => r.data),
  leadsDuplicates: () => client.get("/leads/duplicates").then((r) => r.data),
  opportunityDuplicates: () =>
    client.get("/opportunities/duplicates").then((r) => r.data),
  auditEvents: (params = {}) =>
    client.get("/audit/events", { params }).then((r) => r.data),
  ingestionDiagnostics: () =>
    client.get("/diagnostics/ingestion").then((r) => r.data),

  // NEW: Predictive Intelligence
  predictiveStatus: () => client.get("/intelligence/predictive/status").then((r) => r.data),
  predictiveTrain: () => client.post("/intelligence/predictive/train").then((r) => r.data),
  predictiveForLead: (id) => client.get(`/intelligence/predictive/${id}`).then((r) => r.data),
  predictiveTop: (limit = 20) => client.get(`/intelligence/predictive/batch/top?limit=${limit}`).then((r) => r.data),

  // NEW: Market Intelligence
  marketOverview: () => client.get("/intelligence/market").then((r) => r.data),

  // NEW: Reply Intelligence
  classifyReply: (text, leadId) => client.post("/intelligence/reply/classify", { text, lead_id: leadId }).then((r) => r.data),
  leadsWithReplies: () => client.get("/intelligence/reply/leads-with-replies").then((r) => r.data),
};

export const outreachBlockedFrom = (error) => {
  const data = error?.response?.data;
  if (error?.response?.status === 409 && data?.error === "outreach_blocked") {
    return data.eligibility;
  }
  return null;
};
