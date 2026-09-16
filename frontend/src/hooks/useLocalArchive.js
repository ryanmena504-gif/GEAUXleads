import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

/**
 * Manages Bloodhound-local archive state via /api/local-state.
 * Archives HIDE records in the UI only — never mutates Airtable/Make.
 */
export const useLocalArchive = (feed) => {
  const [archived, setArchived] = useState(() => new Set());
  const [showArchived, setShowArchived] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const { archived_ids } = await api.listLocalArchive(feed);
      setArchived(new Set(archived_ids || []));
    } catch {
      /* non-blocking */
    }
  }, [feed]);

  useEffect(() => { refresh(); }, [refresh]);

  const archive = useCallback(async (recordIds) => {
    await api.archiveLocal(feed, recordIds);
    setArchived((prev) => {
      const next = new Set(prev);
      recordIds.forEach((id) => next.add(id));
      return next;
    });
  }, [feed]);

  const unarchive = useCallback(async (recordIds) => {
    await api.unarchiveLocal(feed, recordIds);
    setArchived((prev) => {
      const next = new Set(prev);
      recordIds.forEach((id) => next.delete(id));
      return next;
    });
  }, [feed]);

  return { archived, showArchived, setShowArchived, archive, unarchive, refresh };
};

export default useLocalArchive;
