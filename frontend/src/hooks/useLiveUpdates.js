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
        } catch {
          /* ignore malformed frame */
        }
      });
      es.onerror = () => {
        es.close();
        if (closed) return;
        setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 2, 30000);
      };
    };

    connect();
    return () => {
      closed = true;
      if (es) es.close();
    };
  }, []);
};

export default useLiveUpdates;
