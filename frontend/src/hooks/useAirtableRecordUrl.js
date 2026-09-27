/**
 * useAirtableRecordUrl — one-off hook that returns a builder for
 * "Open in Airtable" deeplinks. Fetches /api/config once, caches
 * the base + table IDs in a module-scoped promise, and hands back
 * a `(recordId) => url | null` function.
 *
 * Purpose: give operators a fast path to Airtable when GEAUXleads's
 * read-through layer intentionally blocks an action (e.g. record is
 * in All Projects — the queue can only be changed inside Airtable).
 *
 * Never used to write anything from GEAUXleads. Pure navigation.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

let _cache = null; // Promise<{ base_id, table_id } | null>

const fetchIds = () => {
  if (_cache) return _cache;
  _cache = api.config()
    .then((c) => ({
      base_id: c?.airtable_base_id || null,
      table_id: c?.airtable_leads_table_id || null,
    }))
    .catch(() => null);
  return _cache;
};

export const useAirtableRecordUrl = () => {
  const [ids, setIds] = useState(null);
  useEffect(() => {
    let alive = true;
    fetchIds().then((v) => { if (alive) setIds(v); });
    return () => { alive = false; };
  }, []);
  return (recordId) => {
    if (!ids || !ids.base_id || !recordId) return null;
    // Airtable's canonical record URL. Works even without a view ID.
    if (ids.table_id) return `https://airtable.com/${ids.base_id}/${ids.table_id}/${recordId}`;
    return `https://airtable.com/${ids.base_id}/${recordId}`;
  };
};

export default useAirtableRecordUrl;
