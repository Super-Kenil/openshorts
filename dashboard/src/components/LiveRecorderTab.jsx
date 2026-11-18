import React, { useCallback, useEffect, useState } from 'react';
import { Radio, FolderOpen, Loader2, Pause, Play, Square, Film, AlertTriangle } from 'lucide-react';
import { apiJson } from '../lib/api';
import { getApiUrl } from '../config';
import { LIVE_ACTIVE_STATES, liveStartEpoch, fmtWhen } from '../lib/live';
import { useServerSetting } from '../lib/serverSettings';
import FolderBrowser from './FolderBrowser';

const STATE_TEXT = {
  scheduled: 'scheduled',
  waiting: 'waiting for the stream',
  recording: 'recording',
  paused: 'paused',
  ended: 'stream ended',
  finished: 'finished',
  stopped: 'stopped',
  error: 'error',
};

const PRESETS = [10, 20, 30, 60];

const fmtDuration = (secs) => {
  const s = Math.max(0, Math.round(secs || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h ? `${h}h ${String(m).padStart(2, '0')}m` : `${m}m ${String(s % 60).padStart(2, '0')}s`;
};

const errText = (e, fallback) => (typeof e?.detail === 'string' && e.detail) || fallback;

function SessionCard({ s, onAct, busy }) {
  const active = LIVE_ACTIVE_STATES.includes(s.state);
  const parts = (s.chunks || []).slice().reverse();
  return (
    <div className="card p-4 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className={`eyebrow ${s.state === 'recording' ? 'text-ok' : s.state === 'error' ? 'text-danger' : s.state === 'paused' ? 'text-warn' : ''}`}>
            {s.state === 'recording' && <span className="inline-block w-2 h-2 rounded-full bg-danger animate-pulse mr-1.5 align-middle" />}
            {STATE_TEXT[s.state] || s.state}
            {s.state === 'scheduled' && s.startAt ? ` · starts ${fmtWhen(s.startAt * 1000)}` : ''}
            {` · ${fmtDuration(s.recordedSeconds)} recorded · ${s.chunkMinutes} min parts`}
          </p>
          <p className="text-ink text-sm truncate">{s.title || s.url}</p>
          <p className="text-muted text-[11px] flex items-center gap-1.5 mt-0.5 break-all">
            <FolderOpen size={11} className="shrink-0" /> {s.dir}
          </p>
        </div>
        {active && (
          <div className="flex gap-2">
            {s.state === 'recording' && (
              <button className="btn-ghost px-3 py-1.5 text-xs" onClick={() => onAct(s.id, 'pause')} disabled={!!busy}>
                {busy === `${s.id}pause` ? <Loader2 size={13} className="animate-spin" /> : <Pause size={13} />} pause
              </button>
            )}
            {s.state === 'paused' && (
              <button className="btn-primary px-3 py-1.5 text-xs" onClick={() => onAct(s.id, 'resume')} disabled={!!busy}>
                {busy === `${s.id}resume` ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />} resume
              </button>
            )}
            <button className="btn-ghost px-3 py-1.5 text-xs" onClick={() => onAct(s.id, 'stop')} disabled={!!busy}>
              {busy === `${s.id}stop` ? <Loader2 size={13} className="animate-spin" /> : <Square size={13} />} stop
            </button>
          </div>
        )}
      </div>
      {s.error && <p className="text-warn text-sm flex items-center gap-2"><AlertTriangle size={14} /> {s.error}</p>}
      {parts.length > 0 && (
        <div className="space-y-1">
          {parts.map((c) => (
            <div key={c.index} className="flex items-center justify-between gap-3 text-xs px-2 py-1.5 rounded-input border border-rule">
              <span className="flex items-center gap-2 text-ink2">
                <Film size={12} /> part {c.index + 1} · {fmtDuration(c.duration)}
              </span>
              {c.available ? (
                <a className="text-brass hover:underline" href={getApiUrl(`/api/live/${s.id}/recording/${c.index}`)} target="_blank" rel="noopener noreferrer">
                  play
                </a>
              ) : (
                <span className="text-muted">file missing</span>
              )}
            </div>
          ))}
        </div>
      )}
      {(s.log || []).length > 0 && (
        <pre className="text-[11px] text-muted whitespace-pre-wrap max-h-28 overflow-y-auto custom-scrollbar font-mono">{s.log.slice(-6).join('\n')}</pre>
      )}
    </div>
  );
}

export default function LiveRecorderTab() {
  const [url, setUrl] = useState('');
  const [saveDir, setSaveDir] = useServerSetting('recorder_save_dir', '');
  const [minutes, setMinutes] = useServerSetting('recorder_chunk_minutes', 20);
  const [startNow, setStartNow] = useState(true);
  const [startTime, setStartTime] = useState('');
  const [browsing, setBrowsing] = useState(false);
  const [probe, setProbe] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');

  const refresh = useCallback(() => apiJson('/api/live')
    .then((d) => setSessions((d.sessions || []).filter((x) => x.recordOnly)))
    .catch(() => {}), []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, [refresh]);

  useEffect(() => {
    const target = url.trim();
    if (!/^https?:\/\//i.test(target)) { setProbe(null); return undefined; }
    let cancelled = false;
    setProbe({ checking: true });
    const t = setTimeout(() => {
      apiJson(`/api/live/probe?url=${encodeURIComponent(target)}`)
        .then((r) => { if (!cancelled) setProbe(r); })
        .catch(() => { if (!cancelled) setProbe(null); });
    }, 600);
    return () => { cancelled = true; clearTimeout(t); };
  }, [url]);

  const startMs = startNow ? null : liveStartEpoch(startTime);
  const mins = Number(minutes);
  const valid = url.trim() && saveDir.trim() && mins >= 1 && mins <= 720 && (startNow || startMs);

  const start = async (e) => {
    e.preventDefault();
    if (!valid) return;
    setStarting(true);
    setError('');
    try {
      await apiJson('/api/live/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: url.trim(),
          save_dir: saveDir.trim(),
          chunk_minutes: mins,
          start_at: startMs ? startMs / 1000 : null,
          record_only: true,
        }),
      });
      setUrl('');
      await refresh();
    } catch (err) {
      setError(errText(err, 'Could not start recording.'));
    } finally {
      setStarting(false);
    }
  };

  const act = async (id, action) => {
    setBusy(`${id}${action}`);
    try {
      await apiJson(`/api/live/${id}/${action}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
      });
      await refresh();
    } catch (err) {
      setError(errText(err, `Could not ${action}.`));
    } finally {
      setBusy('');
    }
  };

  const probeText = !probe ? '' : probe.checking ? 'checking…'
    : probe.live ? (probe.status === 'is_upcoming' ? 'upcoming stream: recording starts when it goes live' : 'live now')
      : 'not live right now: recording starts when it goes live';

  return (
    <div className="space-y-6">
      <div>
        <p className="eyebrow">record</p>
        <h1 className="font-display lowercase text-3xl text-ink">live recorder</h1>
        <p className="text-muted text-sm mt-1">
          Records a live stream in full and saves it in parts of the length you choose. No clipping, nothing is deleted.
        </p>
      </div>

      <form onSubmit={start} className="card p-4 sm:p-5 space-y-4">
        <div>
          <p className="eyebrow mb-1.5">live stream link</p>
          <input className="input-field" type="url" placeholder="https://www.twitch.tv/..." value={url}
            onChange={(e) => setUrl(e.target.value)} />
          {probeText && (
            <p className={`text-[11px] mt-1 ${probe?.live ? 'text-ok' : 'text-muted'}`}>
              {probe?.live && <Radio size={11} className="inline mr-1" />}{probeText}
            </p>
          )}
        </div>

        <div>
          <p className="eyebrow mb-1.5">save recordings in folder</p>
          <div className="flex gap-2">
            <input className="input-field" placeholder="D:\Recordings" value={saveDir}
              onChange={(e) => setSaveDir(e.target.value)} />
            <button type="button" className="btn-ghost px-3 py-2 text-xs shrink-0" onClick={() => setBrowsing((v) => !v)}>
              <FolderOpen size={13} /> browse
            </button>
          </div>
          {browsing && (
            <FolderBrowser initial={saveDir} onPick={(p) => { setSaveDir(p); setBrowsing(false); }} onClose={() => setBrowsing(false)} />
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <p className="eyebrow mb-1.5">record in parts of (minutes)</p>
            <input className="input-field" type="number" min={1} max={720} value={minutes}
              onChange={(e) => setMinutes(e.target.value)} />
            <div className="flex flex-wrap gap-1.5 mt-2">
              {PRESETS.map((p) => (
                <button key={p} type="button" onClick={() => setMinutes(p)}
                  className={`px-2.5 py-1 rounded-input border text-xs transition-colors
                    ${mins === p ? 'border-[color:var(--color-accent)] text-ink' : 'border-rule2 text-muted hover:border-[color:var(--color-accent)]'}`}>
                  {p} min
                </button>
              ))}
            </div>
            <p className="text-[11px] text-muted mt-1">A stream of 65 minutes in 20-minute parts gives 20, 20, 20 and 5.</p>
          </div>
          <div>
            <p className="eyebrow mb-1.5">start recording</p>
            <label className="flex items-center gap-2 text-xs text-ink2 cursor-pointer select-none mb-2">
              <input type="checkbox" checked={startNow} onChange={(e) => setStartNow(e.target.checked)}
                className="w-4 h-4 accent-[var(--color-accent)] cursor-pointer" />
              now
            </label>
            <input className="input-field disabled:opacity-40" type="time" value={startTime} disabled={startNow}
              onChange={(e) => setStartTime(e.target.value)} />
            <p className="text-[11px] text-muted mt-1">
              {startNow ? 'records from the live edge as soon as you start' : startMs ? `starts ${fmtWhen(startMs)}` : 'pick a time'}
            </p>
          </div>
        </div>

        {error && <p className="text-warn text-sm flex items-center gap-2"><AlertTriangle size={14} /> {error}</p>}

        <button type="submit" className="w-full btn-primary" disabled={!valid || starting}>
          {starting ? <Loader2 size={16} className="animate-spin" /> : <Radio size={16} />}
          {startMs ? 'Schedule recording' : 'Start recording'}
        </button>
      </form>

      {sessions.length > 0 && (
        <div className="space-y-4">
          <p className="eyebrow">recordings</p>
          {sessions.map((s) => <SessionCard key={s.id} s={s} onAct={act} busy={busy} />)}
        </div>
      )}
    </div>
  );
}
