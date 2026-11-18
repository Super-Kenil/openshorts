import { useCallback, useEffect, useRef, useState } from 'react';
import { apiJson } from './api';

let cache = null;
let loading = null;

export function loadServerSettings() {
  if (!loading) {
    loading = apiJson('/api/settings')
      .then((r) => { cache = r.settings || {}; return cache; })
      .catch(() => { cache = {}; return cache; });
  }
  return loading;
}

export function saveServerSettings(values) {
  cache = { ...(cache || {}), ...values };
  return apiJson('/api/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ settings: values }),
  }).catch(() => {});
}

const readLegacy = (key, parse) => {
  if (!key) return undefined;
  try {
    const raw = localStorage.getItem(key);
    if (raw == null) return undefined;
    return parse ? parse(raw) : raw;
  } catch { return undefined; }
};

export function useServerSetting(key, fallback, legacy) {
  const [value, setValue] = useState(fallback);
  const current = useRef(fallback);
  const [ready, setReady] = useState(false);
  const timer = useRef(null);
  const touched = useRef(false);

  useEffect(() => {
    let alive = true;
    loadServerSettings().then((all) => {
      if (!alive) return;
      if (!touched.current) {
        if (key in all) { current.current = all[key]; setValue(all[key]); }
        else {
          const old = readLegacy(legacy?.key, legacy?.parse);
          if (old !== undefined) {
            current.current = old;
            setValue(old);
            saveServerSettings({ [key]: old });
          }
        }
      }
      setReady(true);
    });
    return () => { alive = false; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const update = useCallback((next) => {
    touched.current = true;
    const v = typeof next === 'function' ? next(current.current) : next;
    current.current = v;
    setValue(v);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => saveServerSettings({ [key]: v }), 350);
  }, [key]);

  useEffect(() => () => clearTimeout(timer.current), []);
  return [value, update, ready];
}
