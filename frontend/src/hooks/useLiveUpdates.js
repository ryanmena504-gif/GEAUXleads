/**
 * useLiveUpdates
 *
 * Subscribes to /api/live/stream (SSE) and invokes `onUpdate` every time
 * Airtable pings us with a data change. Reconnects automatically if the
 * connection drops.
 */
import { useEffect, useRef } from "react";

const BASE = process.env.REACT_APP_BACKEND_URL;

export const useLiveUpdates = (onUpdate) => {
  const cbRef = useRef(onUpdate);
  cbRef.current = onUpdate;

  useEffect(() => {
    if (!BASE) return undefined;
    let es;
    let retryDelay = 1500;
    let closed = false;

    const connect = () => {
      es = new EventSource(`${BASE}/api/live/stream`);
      es.addEventListener("ready", () => {
        retryDelay = 1500;
      });
      es.addEventListener("update", (e) => {
        try {
          const data = JSON.parse(e.data);
          cbRef.current && cbRef.current(data);
        } catch (err) {
          // Malformed SSE frame — log but keep the connection alive.
          console.warn("useLiveUpdates: malformed frame", err);
        }
      });
      es.onerror = () => {
        es.close();
        if (closed) return;
        setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 2, 30000);
      };
    };

    // Probe the backend once — if the Airtable webhook wasn't registered
    // (missing scope on the PAT, webhooks disabled, etc.) the SSE endpoint
    // will only ever return 503. Skip the reconnect loop entirely so we
    // don't hammer the server with retries.
    let cancelled = false;
    fetch(`${BASE}/api/live/status`)
      .then((r) => (r.ok ? r.json() : { registered: false }))
      .then((s) => {
        if (cancelled) return;
        if (s && s.registered) connect();
      })
      .catch(() => {
        // Network hiccup — try connecting anyway; onerror will back off.
        if (!cancelled) connect();
      });

    return () => {
      cancelled = true;
      closed = true;
      if (es) es.close();
    };
  }, []);
};

export default useLiveUpdates;
