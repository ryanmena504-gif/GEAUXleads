import { useEffect } from "react";

/**
 * Refreshes read-only dashboard data when the page becomes active again and
 * periodically while it remains open. This is intentionally display-only:
 * it never changes an opportunity, records outreach, or starts a message.
 */
export const useLiveUpdates = (reload, intervalMs = 60000) => {
  useEffect(() => {
    if (typeof reload !== "function") return undefined;

    const onFocus = () => reload();
    window.addEventListener("focus", onFocus);
    const timer = window.setInterval(reload, intervalMs);

    return () => {
      window.removeEventListener("focus", onFocus);
      window.clearInterval(timer);
    };
  }, [reload, intervalMs]);
};

