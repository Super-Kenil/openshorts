import React, { useEffect, useRef, useState } from 'react';
import { ChevronDown, Loader2, Captions } from 'lucide-react';
import { apiJson } from '../lib/api';
import { CAPTION_LOOKS, DEFAULT_CAPTION_STYLE } from '../lib/captionLooks';

const FONTS = [
    ['Anton', 'Anton'], ['Montserrat ExtraBold', 'Montserrat'], ['Impact', 'Impact'],
    ['Verdana', 'Verdana'], ['Arial', 'Arial'], ['Georgia', 'Georgia'],
];
const EFFECTS = [['pop', 'Pop'], ['highlight', 'Box'], ['glow', 'Glow'], ['box', 'Outline'], ['none', 'None']];
const POSITIONS = [['top', 'Top'], ['middle', 'Middle'], ['bottom', 'Bottom']];

const swatch = 'h-8 w-full cursor-pointer rounded-input border border-rule2 bg-transparent p-0.5';

function Field({ label, children }) {
    return (
        <div>
            <p className="eyebrow mb-1.5">{label}</p>
            {children}
        </div>
    );
}

export default function CaptionStudio({ value, onChange, ready = true }) {
    const style = { ...DEFAULT_CAPTION_STYLE, ...(value || {}) };
    const [open, setOpen] = useState(() => {
        try { return localStorage.getItem('os_caption_studio_open') !== '0'; } catch { return true; }
    });
    const [sample, setSample] = useState('');
    const [frames, setFrames] = useState([]);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const [frame, setFrame] = useState(0);
    const seq = useRef(0);

    const set = (patch) => onChange({ ...style, ...patch });
    const pickLook = (look) => {
        const { id, label: _label, ...fields } = look;
        onChange({ ...style, ...fields, preset: id });
    };

    useEffect(() => {
        try { localStorage.setItem('os_caption_studio_open', open ? '1' : '0'); } catch { /* ignore */ }
    }, [open]);

    const key = JSON.stringify([style, sample]);
    useEffect(() => {
        if (!open || !ready) return undefined;
        const mine = ++seq.current;
        const t = setTimeout(async () => {
            setBusy(true);
            try {
                const r = await apiJson('/api/caption-preview', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ style, text: sample || null }),
                });
                if (mine !== seq.current) return;
                setFrames(r.frames || []);
                setFrame(0);
                setError('');
            } catch (e) {
                if (mine === seq.current) setError((typeof e?.detail === 'string' && e.detail) || 'Preview unavailable');
            } finally {
                if (mine === seq.current) setBusy(false);
            }
        }, 350);
        return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [key, open, ready]);

    useEffect(() => {
        if (frames.length < 2) return undefined;
        const t = setInterval(() => setFrame((f) => (f + 1) % frames.length), 700);
        return () => clearInterval(t);
    }, [frames]);

    return (
        <div className="mt-5">
            <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                className="flex items-center gap-1.5 text-xs text-ink2 hover:text-ink lowercase transition-colors"
            >
                <Captions size={14} />
                captions look
                <ChevronDown size={14} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
            </button>
            {open && (
                <div className="mt-3 rounded-card border border-rule2 p-3 sm:p-4 grid grid-cols-1 sm:grid-cols-[1fr_190px] gap-4 animate-fade">
                    <div className="space-y-3 min-w-0">
                        <div className="flex flex-wrap gap-1.5">
                            {CAPTION_LOOKS.map((l) => (
                                <button
                                    key={l.id}
                                    type="button"
                                    onClick={() => pickLook(l)}
                                    className={`px-2.5 py-1 rounded-input border text-xs transition-colors
                                        ${style.preset === l.id ? 'border-[color:var(--color-accent)] text-ink' : 'border-rule2 text-muted hover:border-[color:var(--color-accent)]'}`}
                                >
                                    {l.label}
                                </button>
                            ))}
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                            <Field label="font">
                                <select className="input-field text-xs py-1.5" value={style.font_name}
                                    onChange={(e) => set({ font_name: e.target.value })}>
                                    {FONTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                                </select>
                            </Field>
                            <Field label="animation">
                                <select className="input-field text-xs py-1.5" value={style.effect}
                                    onChange={(e) => set({ effect: e.target.value })}>
                                    {EFFECTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                                </select>
                            </Field>
                            <Field label={`size · ${style.font_size}`}>
                                <input type="range" min="24" max="90" value={style.font_size}
                                    onChange={(e) => set({ font_size: Number(e.target.value) })}
                                    className="w-full accent-[var(--color-accent)]" />
                            </Field>
                            <Field label={`outline · ${style.border_width}`}>
                                <input type="range" min="0" max="10" value={style.border_width}
                                    onChange={(e) => set({ border_width: Number(e.target.value) })}
                                    className="w-full accent-[var(--color-accent)]" />
                            </Field>
                            <Field label={style.max_chars === 1 ? 'words per line · 1' : `letters per line · ${style.max_chars}`}>
                                <input type="range" min="1" max="30" value={style.max_chars}
                                    onChange={(e) => set({ max_chars: Number(e.target.value) })}
                                    className="w-full accent-[var(--color-accent)]" />
                            </Field>
                            <Field label={`other words · ${Math.round(style.base_opacity * 100)}%`}>
                                <input type="range" min="20" max="100" value={Math.round(style.base_opacity * 100)}
                                    onChange={(e) => set({ base_opacity: Number(e.target.value) / 100 })}
                                    className="w-full accent-[var(--color-accent)]" />
                            </Field>
                        </div>
                        <div className="grid grid-cols-3 gap-3">
                            <Field label="text">
                                <input type="color" className={swatch} value={style.font_color}
                                    onChange={(e) => set({ font_color: e.target.value })} />
                            </Field>
                            <Field label="active word">
                                <input type="color" className={swatch} value={style.highlight_color}
                                    onChange={(e) => set({ highlight_color: e.target.value })} />
                            </Field>
                            <Field label="outline">
                                <input type="color" className={swatch} value={style.border_color}
                                    onChange={(e) => set({ border_color: e.target.value })} />
                            </Field>
                        </div>
                        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
                            <div className="flex gap-1.5">
                                {POSITIONS.map(([v, l]) => (
                                    <button
                                        key={v}
                                        type="button"
                                        onClick={() => set({ position: v })}
                                        className={`px-2.5 py-1 rounded-input border text-xs transition-colors
                                            ${style.position === v ? 'border-[color:var(--color-accent)] text-ink' : 'border-rule2 text-muted hover:border-[color:var(--color-accent)]'}`}
                                    >
                                        {l}
                                    </button>
                                ))}
                            </div>
                            <label className="flex items-center gap-2 text-xs text-ink2 cursor-pointer select-none">
                                <input type="checkbox" checked={!!style.uppercase}
                                    onChange={(e) => set({ uppercase: e.target.checked })}
                                    className="w-4 h-4 accent-[var(--color-accent)] cursor-pointer" />
                                CAPITALS
                            </label>
                            <label className="flex items-center gap-2 text-xs text-ink2 cursor-pointer select-none">
                                <input type="checkbox" checked={!!style.reveal}
                                    onChange={(e) => set({ reveal: e.target.checked })}
                                    className="w-4 h-4 accent-[var(--color-accent)] cursor-pointer" />
                                words appear as spoken
                            </label>
                        </div>
                        <Field label="preview text">
                            <input className="input-field text-xs py-1.5" maxLength={140} value={sample}
                                placeholder="type a sentence to try the look on"
                                onChange={(e) => setSample(e.target.value)} />
                        </Field>
                        <p className="text-[11px] leading-relaxed text-muted">
                            Applied to every clip of this run and saved for the next. The picture is drawn
                            by the same renderer that burns the clips; the real clips use their own words.
                        </p>
                    </div>
                    <div className="mx-auto w-[170px] sm:w-full">
                        <div className="relative aspect-[9/16] w-full overflow-hidden rounded-card border border-rule2 bg-black">
                            {frames[frame] && (
                                <img src={frames[frame]} alt="caption preview" className="h-full w-full object-cover" />
                            )}
                            {(busy || (!frames.length && !error)) && (
                                <div className="absolute inset-0 flex items-center justify-center bg-black/30">
                                    <Loader2 size={18} className="animate-spin text-brass" />
                                </div>
                            )}
                            {error && !frames.length && (
                                <p className="absolute inset-0 flex items-center justify-center px-3 text-center text-[11px] text-muted">{error}</p>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
