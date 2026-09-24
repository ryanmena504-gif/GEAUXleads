import { useEffect, useState } from "react";
import { api } from "@/lib/api";

// In-memory cache so every OpenInMessages that mounts on a page doesn't
// re-fetch the same singleton doc. Refreshed after any PATCH via the
// setUserSettings() setter returned by this hook.
let _cache = null;
let _pending = null;
const _listeners = new Set();

const notify = (value) => {
  _cache = value;
  _listeners.forEach((cb) => {
    try { cb(value); } catch (err) {
      // Never let one listener break the rest of the fan-out.
      console.warn("useUserSettings listener error:", err);
    }
  });
};

export const fetchUserSettings = async () => {
  if (_cache) return _cache;
  if (_pending) return _pending;
  _pending = api.getUserSettings()
    .then((r) => {
      notify(r.settings || {});
      return _cache;
    })
    .catch(() => {
      notify({});
      return _cache;
    })
    .finally(() => { _pending = null; });
  return _pending;
};

export const saveUserSettings = async (patch) => {
  const r = await api.updateUserSettings(patch);
  notify(r.settings || {});
  return _cache;
};

export const useUserSettings = () => {
  const [settings, setSettings] = useState(_cache || {});
  useEffect(() => {
    _listeners.add(setSettings);
    if (!_cache && !_pending) fetchUserSettings();
    else if (_cache) setSettings(_cache);
    return () => { _listeners.delete(setSettings); };
  }, []);
  return { settings, save: saveUserSettings };
};

export default useUserSettings;
