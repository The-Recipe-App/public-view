import React, { useEffect, useState, useRef, useCallback, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useNavigate } from "react-router-dom";
import backendUrlV1 from "../urls/backendUrl";
import { useMe } from "../hooks/useMe";
import Cropper from "react-easy-crop";
import { Upload, Edit2, ShieldCheck, Trash2, Settings, Info } from "lucide-react";
import { useContextManager } from "../features/ContextProvider";
import { lazy, Suspense } from "react";
import LazyErrorBoundary from "../components/LazyLoadError";
import PanelSkeleton from "../components/PanelSkeleton";
import SoftCrashPanel from "../components/SoftCrashPanel";

const SecurityCenterExpanded = lazy(() =>
    import("../components/profile/SecurityPanel")
);

/* ------------------------- Utility: debounce hook ------------------------- */
function useDebounced(value, ms = 400) {
    const [v, setV] = useState(value);
    useEffect(() => {
        const t = setTimeout(() => setV(value), ms);
        return () => clearTimeout(t);
    }, [value, ms]);
    return v;
}

/* ------------------------- Username availability (debounced, robust) ------------------------- */
const USERNAME_RE = /^[a-zA-Z0-9_]{3,30}$/;

export function useUsernameAvailabilitySimple(username, enabled = true) {
    const debounced = useDebounced(username, 400);
    const [status, setStatus] = useState(null);
    const controller = useRef(null);

    useEffect(() => {
        if (!enabled) return;
        if (!debounced) {
            setStatus(null);
            return;
        }

        if (!USERNAME_RE.test(debounced)) {
            setStatus("invalid");
            return;
        }

        controller.current?.abort();
        const ctrl = new AbortController();
        controller.current = ctrl;

        let mounted = true;
        setStatus("checking");

        fetch(`${backendUrlV1}/profile/${encodeURIComponent(debounced)}`, {
            method: "GET",
            credentials: "include",
            signal: ctrl.signal,
        })
            .then(async (res) => {
                if (!mounted) return;
                if (res.status === 404) {
                    setStatus("available");
                    return;
                }
                if (res.ok) {
                    setStatus("taken");
                    return;
                }

                setStatus(null);
            })
            .catch((err) => {
                if (err.name === "AbortError") return;
                setStatus(null);
            });

        return () => {
            mounted = false;
            ctrl.abort();
        };
    }, [debounced, enabled]);

    return status;
}

/* ------------------------- Reputation bar (refreshed visuals) ------------------------- */
function ReputationBar({ rep = {} }) {
    const pct = Math.max(0, Math.min(100, rep.progress_pct ?? 0.5));

    return (
        <div className="p-4 rounded-2xl">
            <div className="flex items-center justify-between gap-3">
                <div>
                    <div className="text-xs text-zinc-400">Reputation</div>
                    <div className="flex items-center gap-3">
                        <div className="text-2xl font-bold tracking-tight">
                            {(rep.score ?? 0).toLocaleString()}
                        </div>
                        <div className="text-xs px-2 py-0.5 rounded-full bg-white/6">
                            {rep.level ?? "--"}
                        </div>
                    </div>
                </div>

                <div className="text-xs text-zinc-400 text-right">
                    Next: <div className="text-zinc-200">{rep.next_level ?? "--"}</div>
                </div>
            </div>

            <div className="mt-4">
                <div className="bg-white/6 h-3 rounded-full overflow-hidden relative">
                    <div
                        style={{ width: `${pct}%` }}
                        className="h-full bg-gradient-to-r from-orange-700 via-orange-400 to-orange-200 shadow-[0_6px_20px_rgba(250,204,21,0.12)] transition-all duration-700"
                    />
                </div>
                <div className="mt-2 text-[12px] text-zinc-400">{pct.toFixed(2)}% of the way to the next level</div>
            </div>
        </div>
    );
}

/* ------------------------- Badges list ------------------------- */
function BadgesList({ badges = [] }) {
    if (!badges || !badges.length) return <div className="text-sm text-zinc-500">No badges yet</div>;
    return (
        <div className="flex gap-2 flex-wrap">
            {badges.map((b) => (
                <div key={b.code} className="px-3 py-1 rounded-full bg-white/6 text-sm">
                    <strong className="mr-2">{b.title}</strong>
                    <span className="text-xs text-zinc-400">{b.awarded_at ? new Date(b.awarded_at).toLocaleDateString() : ""}</span>
                </div>
            ))}
        </div>
    );
}

/* ------------------------- Activity helper ------------------------- */
// ── Type config ───────────────────────────────────────────────────────────

const TYPE_META = {
    "recipe.create": { icon: "✦", tag: "recipe", color: "text-zinc-400" },
    "recipe.publish": { icon: "🚀", tag: "recipe", color: "text-emerald-400" },
    "recipe.fork": { icon: "⑂", tag: "recipe", color: "text-sky-400" },
    "recipe.bookmark": { icon: "🔖", tag: "social", color: "text-amber-400" },
    "recipe.unbookmark": { icon: "✕", tag: null, color: "" }, // suppressed
    "recipe.like": { icon: "♥", tag: "social", color: "text-rose-400" },
    "comment.create": { icon: "💬", tag: "social", color: "text-violet-400" },
    "user.follow": { icon: "+", tag: "social", color: "text-teal-400" },
    recipe_published: { icon: "🚀", tag: "recipe", color: "text-emerald-400" },
    fork_received: { icon: "⑂", tag: "recipe", color: "text-sky-400" },
    comment: { icon: "💬", tag: "social", color: "text-violet-400" },
    comment_received: { icon: "💬", tag: "social", color: "text-violet-400" },
    bookmark: { icon: "🔖", tag: "social", color: "text-amber-400" },
    share: { icon: "↗", tag: "social", color: "text-teal-400" },
    badge_earned: { icon: "🏅", tag: "milestone", color: "text-yellow-300" },
    draft_updated: { icon: "✎", tag: "recipe", color: "text-zinc-400" },
};

const SUPPRESSED = new Set(["recipe.unbookmark"]);
const ALIAS = {
    "recipe.publish": "recipe_published",
    "recipe.bookmark": "bookmark",
    "recipe.fork": "fork_received",
    "comment.create": "comment",
};

const FILTERS = [
    { key: "all", label: "All" },
    { key: "recipe", label: "Recipes" },
    { key: "social", label: "Social" },
    { key: "milestone", label: "Milestones" },
];


// ── Helpers ───────────────────────────────────────────────────────────────

function relTime(iso) {
    const d = Date.now() - new Date(iso).getTime();
    const m = Math.floor(d / 60_000);
    const h = Math.floor(d / 3_600_000);
    const dy = Math.floor(d / 86_400_000);
    if (m < 1) return "just now";
    if (m < 60) return `${m}m ago`;
    if (h < 24) return `${h}h ago`;
    if (dy < 7) return `${dy}d ago`;
    return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

function deduplicateItems(items) {
    const seen = new Map();
    const result = [];
    for (const item of items) {
        if (SUPPRESSED.has(item.type)) continue;
        const type = ALIAS[item.type] ?? item.type;
        const key = `${type}:${item.recipe_id ?? "x"}`;
        const ms = new Date(item.when).getTime();
        if (seen.has(key)) {
            const prev = seen.get(key);
            if (Math.abs(ms - new Date(prev.when).getTime()) < 60_000) {
                if (item.title.length > prev.title.length) seen.set(key, { ...item, type });
                continue;
            }
        }
        const deduped = { ...item, type };
        seen.set(key, deduped);
        result.push(deduped);
    }
    return result.sort((a, b) => new Date(b.when) - new Date(a.when));
}


// ── Single row ────────────────────────────────────────────────────────────

function ActivityItem({ item, isNew }) {
    const navigate = useNavigate();
    const meta = TYPE_META[item.type] ?? { icon: "·", tag: "recipe", color: "text-zinc-500" };
    const href = item.recipe_id ? `/recipes/${item.recipe_id}` : null;

    const [timeLabel, setTimeLabel] = useState(() => relTime(item.when));
    useEffect(() => {
        const t = setInterval(() => setTimeLabel(relTime(item.when)), 30_000);
        return () => clearInterval(t);
    }, [item.when]);

    const inner = (
        <>
            <div className={`mt-0.5 w-7 h-7 rounded-lg bg-white/5 flex items-center
                            justify-content-center text-sm flex-shrink-0 ${meta.color}`}
                style={{ justifyContent: "center" }}>
                {meta.icon}
            </div>
            <div className="flex-1 min-w-0">
                <p className="text-sm text-zinc-200 leading-snug truncate">{item.title}</p>
                <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-[11px] text-zinc-500 tabular-nums">{timeLabel}</span>
                    {meta.tag && (
                        <span className="text-[10px] px-1.5 py-px rounded-full border border-white/10 text-zinc-500">
                            {meta.tag}
                        </span>
                    )}
                </div>
            </div>
            {href && (
                <span className="text-zinc-600 group-hover:text-zinc-300 transition-colors
                                 text-sm flex-shrink-0 mt-1 select-none">
                    ›
                </span>
            )}
        </>
    );

    const cls = `group flex items-start gap-3 py-2.5 px-2 border-b border-white/[0.2]
                    last:border-0 transition-all duration-150 hover:bg-white/[0.1]
                    ${isNew ? "animate-[slideIn_.3s_ease-out]" : ""}
                    ${href ? "cursor-pointer" : ""}`;

    if (href) {
        return (
            <div className={cls} onClick={() => navigate(href)} role="link" tabIndex={0}
                onKeyDown={e => e.key === "Enter" && navigate(href)}>
                {inner}
            </div>
        );
    }
    return <div className={cls}>{inner}</div>;
}


// ── Feed ──────────────────────────────────────────────────────────────────

function ActivityFeed({ username }) {
    const [cursor, setCursor] = useState(null);
    const [allItems, setAllItems] = useState([]);
    const [pending, setPending] = useState([]);   // new items waiting to be surfaced
    const [filter, setFilter] = useState("all");
    const [newItemIds, setNewItemIds] = useState(new Set());
    const [lastRefreshed, setLastRefreshed] = useState(Date.now());
    const [refreshLabel, setRefreshLabel] = useState("updated just now");

    // Refresh label ticker
    useEffect(() => {
        const t = setInterval(() => {
            const s = Math.round((Date.now() - lastRefreshed) / 1000);
            if (s < 10) setRefreshLabel("updated just now");
            else if (s < 60) setRefreshLabel(`updated ${s}s ago`);
            else setRefreshLabel(`updated ${Math.floor(s / 60)}m ago`);
        }, 5000);
        return () => clearInterval(t);
    }, [lastRefreshed]);

    const q = useQuery({
        queryKey: ["profile", username, "activity", cursor],
        enabled: Boolean(username),
        queryFn: async () => {
            const params = new URLSearchParams();
            if (cursor) params.set("before", cursor);
            const qs = params.toString();
            const url = `${backendUrlV1}/profile/${encodeURIComponent(username)}/activity${qs ? `?${qs}` : ""}`;
            const res = await fetch(url, { credentials: "include" });
            if (!res.ok) return { items: [], next_cursor: null };
            return res.json();
        },
        retry: false,
        staleTime: 1000 * 60 * 5,
        refetchInterval: 1000 * 60,   // background refetch every minute
    });

    // Accumulate pages + detect new items on refetch
    useEffect(() => {
        if (!q.data?.items) return;
        const incoming = deduplicateItems(q.data.items);

        if (cursor === null && allItems.length > 0) {
            // This is a background refetch - find genuinely new items
            const existingWhens = new Set(allItems.map(i => i.when));
            const brandNew = incoming.filter(i => !existingWhens.has(i.when));
            if (brandNew.length > 0) {
                setPending(prev => deduplicateItems([...brandNew, ...prev]));
                return; // don't merge yet - wait for user to click "Show new"
            }
        }

        setAllItems(prev =>
            cursor === null
                ? incoming
                : deduplicateItems([...prev, ...incoming])
        );
        setLastRefreshed(Date.now());
        setRefreshLabel("updated just now");
    }, [q.data]);

    function flushPending() {
        const ids = new Set(pending.map(i => i.when));
        setNewItemIds(ids);
        setAllItems(prev => deduplicateItems([...pending, ...prev]));
        setPending([]);
        setTimeout(() => setNewItemIds(new Set()), 2000); // clear highlight after 2s
    }

    const visible = useMemo(() => {
        if (filter === "all") return allItems;
        return allItems.filter(it => (TYPE_META[it.type]?.tag ?? "recipe") === filter);
    }, [allItems, filter]);

    if (q.isLoading && allItems.length === 0) {
        return (
            <div className="flex flex-col items-center gap-3 py-8">
                <div className="w-8 h-8 rounded-full border-2 border-white/10 border-t-orange-400 animate-spin" />
                <span className="text-xs text-zinc-500">Loading activity…</span>
            </div>
        );
    }

    if (q.isError) return <p className="text-sm text-zinc-500 py-4">Activity unavailable.</p>;

    return (
        <div>
            {/* Header row */}
            <div className="flex items-center justify-between mb-3">
                {/* Pending new items banner */}
                {pending.length > 0 && (
                    <button
                        onClick={flushPending}
                        className="text-xs px-2.5 py-1 rounded-full bg-emerald-900/40 text-emerald-400
                                    border border-emerald-500/30 hover:bg-emerald-900/60 transition"
                    >
                        + {pending.length} new
                    </button>
                )}
            </div>

            {/* Filter tabs */}
            <div className="flex gap-2 flex-wrap mb-3">
                {FILTERS.map(f => (
                    <button
                        key={f.key}
                        onClick={() => setFilter(f.key)}
                        className={`text-xs px-3 py-1 rounded-full border transition
                            ${filter === f.key
                                ? "bg-white/10 border-white/20 text-white"
                                : "border-white/80 text-zinc-200 hover:border-orange-300/60 hover:text-white"
                            }`}
                    >
                        {f.label}
                    </button>
                ))}
            </div>

            {/* Items */}
            {visible.length === 0
                ? <p className="text-sm text-zinc-500 py-4 text-center">Nothing here yet.</p>
                : (
                    <div>
                        {visible.map(item => (
                            <ActivityItem
                                key={`${item.type}-${item.recipe_id}-${item.when}`}
                                item={item}
                                isNew={newItemIds.has(item.when)}
                            />
                        ))}
                    </div>
                )
            }

            {/* Load more */}
            {q.data?.next_cursor && (
                <button
                    onClick={() => setCursor(q.data.next_cursor)}
                    disabled={q.isFetching}
                    className="mt-3 w-full py-2 rounded-lg text-xs text-zinc-500 border border-white/8
                               hover:bg-white/4 hover:text-zinc-300 disabled:opacity-40 transition"
                >
                    {q.isFetching ? "Loading…" : "Load more"}
                </button>
            )}
        </div>
    );
}
/* ------------------------- Edit Profile Modal (unchanged logic, refreshed look) ------------------------- */

function EditProfileModal({ open, onClose, user }) {
    const qc = useQueryClient();
    const navigate = useNavigate();
    const usernameRef = useRef(null);

    const { windowWidth } = useContextManager();

    const buildInitialForm = () => ({
        username: user.username,
        bio: user.bio || "",
        location: user.location || "",
        website: user.website || "",
        twitter: user.twitter || "",
        youtube: user.youtube || ""
    });

    const [form, setForm] = useState(buildInitialForm);
    const [serverError, setServerError] = useState(null);
    const [shake, setShake] = useState(false);

    const originalUsername = user.username;

    useEffect(() => {
        if (!open) return;
        setForm(buildInitialForm());
        setServerError(null);
        setShake(false);
        setTimeout(() => usernameRef.current?.focus(), 80);
    }, [open, user]);

    const usernameStatus = useUsernameAvailabilitySimple(
        form.username,
        open && form.username !== originalUsername
    );

    const isUsernameChanged = form.username !== originalUsername;
    const isDirty = JSON.stringify(form) !== JSON.stringify(buildInitialForm());

    const canSave =
        open &&
        isDirty &&
        (!isUsernameChanged || usernameStatus === "available");

    const mutation = useMutation(
        async (payload) => {
            const res = await fetch(`${backendUrlV1}/profile/me`, {
                method: "PATCH",
                credentials: "include",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });

            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                const err = new Error(data.detail || data.message || "Save failed");
                err.status = res.status;
                throw err;
            }
            return data;
        },
        {
            onSuccess: () => {
                qc.invalidateQueries({ queryKey: ["profile", "me"] });
                qc.invalidateQueries({ queryKey: ["profile"] });
                if (form.username !== originalUsername) {
                    navigate(`/profile/${encodeURIComponent(form.username)}`, { replace: true });
                }
                onClose();
            },
            onError: (err) => {
                setServerError(err.message || "Save failed");
                setShake(true);
                setTimeout(() => setShake(false), 450);
            }
        }
    );

    const parseHandle = (value, domain, maxLen = 30) => {
        let raw = value.trim();
        try {
            if (raw.includes(domain)) {
                const url = new URL(raw.startsWith("http") ? raw : "https://" + raw);
                raw = url.pathname.split("/").filter(Boolean)[0] || "";
            }
        } catch { }

        return raw.replace(/^@+/, "").toLowerCase().replace(/[^a-z0-9_]/g, "").slice(0, maxLen);
    };

    const handleCancel = () => {
        setForm(buildInitialForm());
        setServerError(null);
        setShake(false);
        onClose();
    };

    const handleSave = () => {
        const payload = Object.fromEntries(
            Object.entries(form).map(([k, v]) => [k, v.trim() === "" ? null : v])
        );
        mutation.mutate(payload);
    };

    if (!open) return null;

    const isSmall = windowWidth < 1024;

    return (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-[999] flex items-end lg:items-center justify-center">
            <div
                className={`
                    relative flex flex-col
                    w-full lg:max-w-2xl
                    ${isSmall ? "h-[100dvh]" : "max-h-[90vh]"}
                    rounded-none lg:rounded-2xl
                    bg-gradient-to-br from-neutral-900/95 via-neutral-800/95 to-neutral-900/95
                    border-0 lg:border border-neutral-700
                    ${shake ? "animate-shake" : ""}
                `}
            >
                {/* Header */}
                <div className="flex flex-row items-center justify-between px-6 pt-5 pb-4 border-b border-white/5 shrink-0">
                    <h3 className="text-xl font-semibold tracking-wide text-white">Edit Profile</h3>
                    <div className="flex gap-2">
                        <button
                            className="px-3 py-2 rounded-lg text-sm text-zinc-300 hover:text-white hover:bg-white/5 transition"
                            onClick={handleCancel}
                            disabled={mutation.isLoading}
                        >
                            Cancel
                        </button>
                        <button
                            className="px-4 py-2 rounded-lg text-sm font-medium text-neutral-900 bg-amber-400 hover:brightness-95 disabled:opacity-50 disabled:cursor-not-allowed transition"
                            disabled={!canSave || mutation.isLoading}
                            onClick={handleSave}
                        >
                            {mutation.isLoading ? "Saving…" : "Save"}
                        </button>
                    </div>
                </div>

                {/* Scrollable body */}
                <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4 forkit-scroll">
                    {serverError && <div className="text-sm text-red-400">{serverError}</div>}

                    <div>
                        <label className="text-sm mb-1 block">Username</label>
                        <input
                            ref={usernameRef}
                            className="input-dark w-full"
                            value={form.username}
                            onChange={(e) => setForm(s => ({ ...s, username: e.target.value }))}
                        />
                        <div className="mt-1 h-4 text-xs">
                            {isUsernameChanged && usernameStatus === "checking" && <span className="text-zinc-400">Checking…</span>}
                            {isUsernameChanged && usernameStatus === "available" && <span className="text-green-400">Available ✓</span>}
                            {isUsernameChanged && usernameStatus === "taken" && <span className="text-red-400">Taken ✕</span>}
                            {isUsernameChanged && usernameStatus === "invalid" && <span className="text-yellow-400">3-30 chars, letters, numbers, underscore</span>}
                        </div>
                    </div>

                    <div>
                        <label className="text-sm mb-1 block">Bio <span className="text-xs text-zinc-400">({form.bio.length}/160)</span></label>
                        <textarea
                            maxLength={160}
                            className="input-dark w-full h-24 resize-none"
                            value={form.bio}
                            onChange={(e) => setForm(s => ({ ...s, bio: e.target.value }))}
                        />
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div>
                            <label className="text-sm mb-1 block">Location</label>
                            <input
                                className="input-dark w-full"
                                value={form.location}
                                onChange={(e) => setForm(s => ({ ...s, location: e.target.value }))}
                            />
                        </div>

                        <div>
                            <label className="text-sm mb-1 block">Website</label>
                            <input
                                className="input-dark w-full"
                                placeholder="https://example.com"
                                value={form.website}
                                onChange={(e) => setForm(s => ({ ...s, website: e.target.value }))}
                            />
                            {form.website && (
                                <a
                                    href={form.website.startsWith("http") ? form.website : `https://${form.website}`}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="text-xs text-blue-400 mt-1 inline-block"
                                >
                                    Preview website ↗
                                </a>
                            )}
                        </div>
                    </div>

                    <div>
                        <label className="text-sm mb-1 block">Twitter / X</label>
                        <input
                            className="input-dark w-full"
                            placeholder="@username or x.com/username"
                            value={form.twitter}
                            onChange={(e) =>
                                setForm(s => ({ ...s, twitter: parseHandle(e.target.value, "x.com", 15) }))
                            }
                        />
                        {form.twitter && (
                            <a
                                href={`https://twitter.com/${form.twitter}`}
                                target="_blank"
                                rel="noreferrer"
                                className="text-xs text-blue-400 mt-1 inline-block"
                            >
                                Preview twitter ↗
                            </a>
                        )}
                    </div>

                    <div className="pb-4">
                        <label className="text-sm mb-1 block">YouTube</label>
                        <input
                            className="input-dark w-full"
                            placeholder="youtube.com/@channel or channel name"
                            value={form.youtube}
                            onChange={(e) =>
                                setForm(s => ({ ...s, youtube: parseHandle(e.target.value, "youtube.com", 50) }))
                            }
                        />
                        {form.youtube && (
                            <a
                                href={`https://youtube.com/@${form.youtube}`}
                                target="_blank"
                                rel="noreferrer"
                                className="text-xs text-blue-400 mt-1 inline-block"
                            >
                                Preview YouTube ↗
                            </a>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
/* ------------------------- Avatar Editor (kept logic, nicer UI) ------------------------- */

function getCroppedImage(imageSrc, crop) {
    return new Promise((resolve) => {
        const image = new Image();
        image.src = imageSrc;
        image.onload = () => {
            const canvas = document.createElement("canvas");
            canvas.width = crop.width;
            canvas.height = crop.height;
            const ctx = canvas.getContext("2d");

            ctx.drawImage(
                image,
                crop.x,
                crop.y,
                crop.width,
                crop.height,
                0,
                0,
                crop.width,
                crop.height
            );

            canvas.toBlob((blob) => resolve(blob), "image/png");
        };
    });
}

function AvatarEditorModal({ open, onClose, username }) {
    const qc = useQueryClient();
    const [imageSrc, setImageSrc] = useState(null);
    const [crop, setCrop] = useState({ x: 0, y: 0 });
    const [zoom, setZoom] = useState(1);
    const [croppedAreaPixels, setCroppedAreaPixels] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
        if (!open) {
            setImageSrc(null);
            setZoom(1);
            setCrop({ x: 0, y: 0 });
            setError(null);
        }
    }, [open]);

    const onCropComplete = useCallback((_, pixels) => {
        setCroppedAreaPixels(pixels);
    }, []);

    const uploadMutation = useMutation(async (blob) => {
        const form = new FormData();
        form.append("file", blob, "avatar.png");

        const res = await fetch(`${backendUrlV1}/profile/me/avatar`, {
            method: "POST",
            credentials: "include",
            body: form,
        });

        if (!res.ok) throw new Error("Upload failed");
        return res.json();
    }, {
        onSuccess: (data) => {
            qc.setQueryData(["profile", "me"], (old) =>
                old ? { ...old, avatar_url: data.avatar_url, avatar_changed_at: data.avatar_changed_at } : old
            );

            if (username) {
                qc.setQueryData(["profile", username], (old) =>
                    old ? { ...old, avatar_url: data.avatar_url, avatar_changed_at: data.avatar_changed_at } : old
                );
            }

            qc.invalidateQueries({ queryKey: ["profile"] });
            onClose();
        },
        onError: () => setError("Upload failed. Please try again.")
    });

    const handleFile = (file) => {
        if (!file) return;
        if (!file.type.startsWith("image/")) {
            setError("Only image files are allowed.");
            return;
        }
        if (file.size > 5 * 1024 * 1024) {
            setError("Image must be under 5MB.");
            return;
        }

        const url = URL.createObjectURL(file);
        setImageSrc(url);
    };

    async function handleSave() {
        try {
            const blob = await getCroppedImage(imageSrc, croppedAreaPixels);
            await uploadMutation.mutateAsync(blob);
        } catch {
            setError("Failed to process image.");
        }
    }

    if (!open) return null;

    return (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm grid place-items-center z-50 px-4">
            <div className="relative w-full max-w-lg rounded-2xl bg-gradient-to-br from-neutral-900/80 via-neutral-800/70 to-neutral-900/80 border border-neutral-700 p-6">
                <h3 className="text-lg font-semibold mb-3">Edit Avatar</h3>

                {error && <div className="text-red-400 text-sm mb-3">{error}</div>}

                {!imageSrc && (
                    <label className="relative flex flex-col items-center justify-center w-full h-48 border-2 border-dashed border-zinc-700 rounded-xl cursor-pointer bg-neutral-800/50 hover:bg-neutral-800/70 transition">
                        <div className="flex flex-col items-center text-center px-4">
                            <Upload className="w-6 h-6 text-zinc-400 mb-2" />
                            <p className="text-sm text-zinc-300">
                                <span className="font-medium">Click to upload</span> or drag & drop
                            </p>
                            <p className="text-xs text-zinc-500 mt-1">Square image works best • Max 5MB</p>
                        </div>

                        <input
                            type="file"
                            accept="image/*"
                            className="absolute inset-0 opacity-0 cursor-pointer"
                            onChange={(e) => handleFile(e.target.files?.[0])}
                        />
                    </label>
                )}

                {imageSrc && (
                    <>
                        <div className="relative w-full h-64 bg-black rounded-lg overflow-hidden">
                            <Cropper
                                image={imageSrc}
                                crop={crop}
                                zoom={zoom}
                                aspect={1}
                                onCropChange={setCrop}
                                onZoomChange={setZoom}
                                onCropComplete={onCropComplete}
                            />

                            {uploadMutation.isLoading && (
                                <div className="absolute inset-0 bg-black/60 grid place-items-center text-white text-sm">
                                    Saving…
                                </div>
                            )}
                        </div>

                        <div className="mt-3">
                            <input
                                type="range"
                                min={1}
                                max={3}
                                step={0.01}
                                value={zoom}
                                onChange={(e) => setZoom(Number(e.target.value))}
                                className="w-full accent-amber-400"
                            />
                        </div>

                        <div className="flex justify-end gap-2 mt-4">
                            <button className="btn-ghost" onClick={onClose} disabled={uploadMutation.isLoading}>
                                Cancel
                            </button>
                            <button
                                className="btn-primary"
                                onClick={handleSave}
                                disabled={uploadMutation.isLoading}
                            >
                                {uploadMutation.isLoading ? "Saving…" : "Save Avatar"}
                            </button>
                        </div>
                    </>
                )}

                {!imageSrc && (
                    <div className="flex justify-end mt-4">
                        <button className="btn-ghost" onClick={onClose}>Cancel</button>
                    </div>
                )}
            </div>
        </div>
    );
}

/* ------------------------- Loading & NotFound (refreshed) ------------------------- */
const ProfileLoading = () => (
    <div className="flex justify-center items-center min-h-[50vh]">
        <div className="w-full max-w-md rounded-2xl border border-neutral-700 bg-gradient-to-br from-neutral-900/70 to-neutral-800/50 p-8 shadow-xl animate-pulse">
            <div className="h-6 w-1/2 bg-white/10 rounded mb-6" />
            <div className="h-4 w-full bg-white/10 rounded mb-3" />
            <div className="h-4 w-5/6 bg-white/10 rounded mb-3" />
            <div className="h-4 w-2/3 bg-white/10 rounded" />
        </div>
    </div>
);

const ProfileNotFound = () => (
    <div className="flex justify-center items-center min-h-[60vh] px-6">
        <div className="max-w-md w-full rounded-2xl border border-neutral-700 bg-gradient-to-br from-neutral-900/60 to-neutral-800/40 p-10 text-center">
            <div className="text-5xl mb-4">😕</div>
            <h2 className="text-xl font-semibold text-white mb-2">Profile Not Found</h2>
            <p className="text-sm text-white/60 mb-6">The user you're looking for doesn't exist or may have been removed.</p>
            <button
                onClick={() => window.history.back()}
                className="px-5 py-2 rounded-xl bg-amber-400 hover:brightness-95 text-neutral-900 font-medium transition"
            >
                Go Back
            </button>
        </div>
    </div>
);

function FollowButton({ username }) {
    const qc = useQueryClient();

    const { data, isLoading } = useQuery({
        queryKey: ["followStatus", username],
        queryFn: async () => {
            const res = await fetch(`${backendUrlV1}/follows/${username}/status`, {
                credentials: "include",
            });
            if (!res.ok) throw new Error("Failed");
            return res.json();
        },
        enabled: Boolean(username),
    });

    const mutation = useMutation({
        mutationFn: async () => {
            const res = await fetch(`${backendUrlV1}/follows/${username}`, {
                method: "POST",
                credentials: "include",
            });
            if (!res.ok) throw new Error("Failed");
            return res.json();
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ["followStatus", username] });
        },
    });

    const isFollowing = data?.is_following ?? false;
    const followers = data?.followers_count ?? 0;

    if (isLoading) return null;

    return (
        <div className="flex items-center gap-3">
            <button
                onClick={() => mutation.mutate()}
                disabled={mutation.isPending}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition flex items-center gap-2
                    ${isFollowing
                        ? "bg-white/10 text-white hover:bg-red-500/20 hover:text-red-400 border border-white/10"
                        : "bg-amber-500 text-black hover:bg-amber-400"
                    }`}
            >
                {mutation.isPending ? "..." : isFollowing ? "Following" : "Follow"}
            </button>
            <span className="text-xs text-zinc-400">
                {followers} follower{followers !== 1 ? "s" : ""}
            </span>
        </div>
    );
}

/* ------------------------- Main Profile Dashboard (refreshed layout) ------------------------- */
export default function ProfileDashboard() {
    const { username } = useParams();
    const navigate = useNavigate();
    const me = useMe();

    const { setIsLoading } = useContextManager();

    const { windowWidth } = useContextManager();
    const isXS = windowWidth < 380;
    const isSM = windowWidth < 778;
    const isMD = windowWidth < 1024;
    const isLG = windowWidth >= 1024;

    const avatarSize = isXS ? 110 : isSM ? 130 : isMD ? 150 : 160;
    const headerPadding = isXS ? "p-4" : isSM ? "p-5" : "p-6";
    const titleClass = isXS
        ? "text-xl"
        : isSM
            ? "text-2xl"
            : "text-3xl";
    const sectionGap = isXS ? "space-y-6" : "space-y-10";
    const statsWrap = isXS || isSM;

    useEffect(() => {
        if (!username && me.data?.username) {
            navigate(`/profile/${encodeURIComponent(me.data.username)}`, { replace: true });
        }
    }, [username, me.data, navigate]);

    useEffect(() => {
        setIsLoading(false);
    }, []);

    const profileQuery = useQuery({
        queryKey: ["profile", username],
        enabled: Boolean(username),
        queryFn: async () => {
            const url = `${backendUrlV1}/profile/${encodeURIComponent(username)}`;
            const res = await fetch(url, { credentials: "include" });
            if (!res.ok) throw new Error("Profile fetch failed");
            return res.json();
        },
        retry: false,
        staleTime: 1000 * 60 * 2,
    });

    const canEdit = Boolean(me.data?.username && username && me.data.username === username);
    const isAdmin = Boolean(me.data?.is_admin);


    const reputationQuery = useQuery({
        queryKey: ["profile", username, "reputation"],
        enabled: canEdit,
        queryFn: async () => {
            const res = await fetch(`${backendUrlV1}/profile/me/reputation`, { credentials: "include" });
            if (!res.ok) throw new Error("Reputation fetch failed");
            return res.json();
        },
        retry: false,
        staleTime: 1000 * 60 * 2,
    });

    const [editOpen, setEditOpen] = useState(false);
    const [avatarOpen, setAvatarOpen] = useState(false);

    useEffect(() => {
        const isModalOpen = editOpen || avatarOpen;
        if (isModalOpen) {
            document.body.style.overflow = "hidden";
        } else {
            document.body.style.overflow = "";
        }
        return () => {
            document.body.style.overflow = "";
        };
    }, [editOpen, avatarOpen]);

    const isOwnProfile = !username;
    const isLoading = isOwnProfile ? me.isLoading : profileQuery.isLoading;

    const isMissing = isOwnProfile ? !me.data : profileQuery.isError || !profileQuery.data;

    if (isLoading) return <ProfileLoading />;
    if (isMissing) return <ProfileNotFound />;

    const raw = profileQuery.data || {};

    let reputationObj = {};
    if (raw.reputation == null) {
        reputationObj = { score: 0, level: "--", progress_pct: 0 };
    } else if (typeof raw.reputation === "object") {
        reputationObj = {
            score: raw.reputation.score ?? 0,
            level: raw.reputation.level ?? "--",
            next_level: raw.reputation.next_level ?? null,
            progress_pct: raw.reputation.progress_pct ?? 0,
        };
    } else {
        reputationObj = { score: Number(raw.reputation) || 0, level: "--", progress_pct: 0 };
    }

    const effectiveReputation = reputationQuery.data ? {
        score: reputationQuery.data.score ?? reputationObj.score,
        level: reputationQuery.data.level ?? reputationObj.level,
        next_level: reputationQuery.data.next_level ?? reputationObj.next_level,
        progress_pct: reputationQuery.data.progress_pct ?? reputationObj.progress_pct,
    } : reputationObj;

    const user = {
        ...raw,
        reputation_score: effectiveReputation.score,
        reputation_level: effectiveReputation.level,
        reputation_obj: effectiveReputation,
    };

    const twitter = user?.twitter?.replace(/^@/, "");
    const youtube = user?.youtube?.replace(/^https?:\/\//, "");

    return (
        <div
            className={`
                min-h-screen max-w-[100vw] text-neutral-200 px-3 py-6
            `}
        >

            <div className={`max-w-6xl mx-auto ${sectionGap}`}>

                {/* Header */}
                <div
                    className={`
                        rounded-3xl ${headerPadding}
                        flex ${windowWidth < 774 ? "flex-col items-start" : "flex-row items-center"}
                        gap-${isXS ? "4" : "6"}
                    `}
                >
                    <div className={`flex items-center gap-6 w-full ${isSM || isXS ? "flex-col" : "flex-row"}`}>
                        <div className="relative">
                            <div className="flex">
                                <div className="rounded-full max-h-fit max-w-fit bg-gradient-to-tr from-amber-400 to-pink-400 p-1">
                                    <div className="rounded-full bg-neutral-700 max-w-fit">
                                        <img
                                            src={
                                                user.avatar_url
                                                    ? `${user.avatar_url}?v=${user.avatar_changed_at ?? ""}`
                                                    : `https://ui-avatars.com/api/?name=${encodeURIComponent(user.username ?? "User")}`
                                            }
                                            alt={user.username}
                                            style={{ minWidth: avatarSize, maxWidth: avatarSize, minHeight: avatarSize, maxHeight: avatarSize, display: "block", userSelect: "none", pointerEvents: "none" }}
                                            className="rounded-full object-cover ring-4 ring-black/60 shadow-xl"
                                        />
                                    </div>
                                </div>

                                {canEdit && (
                                    <button
                                        onClick={() => setAvatarOpen(true)}
                                        className="absolute -right-2 -bottom-2 bg-amber-400 p-2 rounded-full shadow-md text-neutral-900 hover:scale-105 transition"
                                    >
                                        <Upload className="w-4 h-4" />
                                    </button>
                                )}
                            </div>
                        </div>
                        <div className="flex-col">
                            <div className="flex-col">
                                <div className="flex items-baseline gap-3">
                                    <h1 className={`${titleClass} font-semibold tracking-tight`}>
                                        {user.username}</h1>
                                    <span className="inline-block w-2 h-2 rounded-full bg-orange-400" />
                                </div>
                                {user.bio && (
                                    <p
                                        className={`
                                        mt-2 text-sm text-zinc-400 max-w-xl
                                        ${isXS ? "leading-snug" : "leading-relaxed"}
                                    `}
                                    >
                                        {user.bio}
                                    </p>
                                )}
                            </div>

                            <div className="flex flex-col">
                                <div className="mt-4 flex items-center gap-3">
                                    {canEdit ? (
                                        <button
                                            onClick={() => setEditOpen(true)}
                                            className="px-4 py-2 rounded-lg bg-orange-600/90 hover:bg-orange-500 text-black font-bold transition flex items-center gap-2 text-sm"
                                        >
                                            <Edit2 className="w-4 h-4" /> Edit Profile
                                        </button>
                                    ) : (
                                        <FollowButton username={username} />
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>
                    {/* Stats (compact) */}
                    <div
                        className={`
                            ${statsWrap ? "w-full grid grid-cols-3 gap-2 mt-4" : "ml-auto flex gap-3"}
                        `}
                    >

                        {[
                            ["Recipes", user.stats?.recipes ?? 0],
                            ["Forks", user.stats?.forks ?? 0],
                            ["Comments", user.stats?.comments ?? 0],
                        ].map(([label, value]) => (
                            <div key={label} className="bg-white/4 px-4 py-3 rounded-2xl text-center min-w-[96px]">
                                <div className="text-xl text-center w-full font-bold">{value}</div>
                                <span className="text-xs text-zinc-400">{label}</span>
                            </div>
                        ))}
                    </div>
                </div>

                <div className="w-full h-px bg-white/40" />

                {/* Main content */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    {/* Left / main */}
                    <div className="lg:col-span-2">
                        <div className="p-6 rounded-2xl border border-neutral-700 bg-gradient-to-br from-black/20 to-black/10 h-full">
                            <div className="flex items-center gap-2.5 mb-4">
                                {/* Clock icon */}
                                <Info className="w-4 h-4" stroke="rgba(251,146,60,0.65)" />
                                <h3 className="text-[15px] font-medium tracking-tight text-white/90">
                                    About
                                </h3>
                            </div>

                            {/* Bio block */}
                            <div className="pb-5 border-b border-white/[0.06]">
                                {/* "On Forkit since" chip */}
                                <div className="inline-flex items-center gap-1.5 text-[11px] 
                            bg-white/[0.04] border border-white/[0.08] rounded-full
                            px-2.5 py-1 mb-4">
                                    <span className="w-1.5 h-1.5 rounded-full bg-orange-400/70 flex-shrink-0" />
                                    On Forkit since{" "}
                                    <span className="text-white">
                                        {user.created_at
                                            ? new Intl.DateTimeFormat("en-GB", { year: "numeric", month: "short" })
                                                .format(new Date(user.created_at))
                                            : "-"}
                                    </span>
                                </div>

                                {user.bio
                                    ? <p className="text-sm text-white leading-relaxed">{user.bio}</p>
                                    : <p className="text-sm text-white/70 italic">No bio yet.</p>
                                }
                            </div>

                            {/* Links grid - each cell separated by hairline */}
                            {(user.location || user.website || twitter || youtube) ? (
                                <div className="grid grid-cols-2 gap-1">

                                    {user.location && (
                                        <div className="flex items-center gap-3 py-3.5">
                                            <div className="w-7 h-7 rounded-[8px] bg-white/[0.05] flex items-center
                                        justify-center flex-shrink-0">
                                                <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
                                                    stroke="rgba(251,146,60,0.8)" strokeWidth="2" strokeLinecap="round">
                                                    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z" />
                                                    <circle cx="12" cy="10" r="3" />
                                                </svg>
                                            </div>
                                            <div className="min-w-0">
                                                <div className="text-[11px] text-white/50 mb-0.5">Location</div>
                                                <div className="text-[13px] text-white/75 truncate">{user.location}</div>
                                            </div>
                                        </div>
                                    )}

                                    {user.website && (
                                        <a href={user.website.startsWith("http") ? user.website : `https://${user.website}`}
                                            target="_blank" rel="noopener noreferrer"
                                            className="flex items-center gap-3 py-3.5 group transition-colors duration-100">
                                            <div className="w-7 h-7 rounded-[8px] bg-white/[0.05] flex items-center
                                        justify-center flex-shrink-0">
                                                <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
                                                    stroke="rgba(96,165,250,0.8)" strokeWidth="2" strokeLinecap="round">
                                                    <circle cx="12" cy="12" r="10" />
                                                    <path d="M2 12h20M12 2a15.3 15.3 0 010 20M12 2a15.3 15.3 0 000 20" />
                                                </svg>
                                            </div>
                                            <div className="min-w-0">
                                                <div className="text-[11px] text-white/50 mb-0.5">Website</div>
                                                <div className="text-[13px] text-white/75 truncate
                                            group-hover:text-white/95 transition-colors">
                                                    {user.website.replace(/^https?:\/\//, "")}
                                                </div>
                                            </div>
                                        </a>
                                    )}

                                    {twitter && (
                                        <a href={`https://twitter.com/${encodeURIComponent(twitter)}`}
                                            target="_blank" rel="noopener noreferrer"
                                            className="flex items-center gap-3 py-3.5 group transition-colors duration-100">
                                            <div className="w-7 h-7 rounded-[8px] bg-white/[0.05] flex items-center
                                        justify-center flex-shrink-0">
                                                <svg width="13" height="13" viewBox="0 0 24 24"
                                                    fill="rgba(148,163,184,0.8)">
                                                    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.744l7.737-8.835L1.254 2.25H8.08l4.261 5.636 5.903-5.636zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
                                                </svg>
                                            </div>
                                            <div className="min-w-0">
                                                <div className="text-[11px] text-white/50 mb-0.5">Twitter / X</div>
                                                <div className="text-[13px] text-white/75 truncate
                                            group-hover:text-white/95 transition-colors">
                                                    @{twitter}
                                                </div>
                                            </div>
                                        </a>
                                    )}

                                    {youtube && (
                                        <a href={`https://youtube.com/@${encodeURIComponent(youtube)}`}
                                            target="_blank" rel="noopener noreferrer"
                                            className="flex items-center gap-3 py-3.5 group transition-colors duration-100">
                                            <div className="w-7 h-7 rounded-[8px] bg-white/[0.05] flex items-center
                                        justify-center flex-shrink-0">
                                                <svg width="13" height="13" viewBox="0 0 24 24"
                                                    fill="rgba(248,113,113,0.85)">
                                                    <path d="M23.5 6.19a3.02 3.02 0 00-2.12-2.14C19.54 3.5 12 3.5 12 3.5s-7.54 0-9.38.55A3.02 3.02 0 00.5 6.19C0 8.04 0 12 0 12s0 3.96.5 5.81a3.02 3.02 0 002.12 2.14C4.46 20.5 12 20.5 12 20.5s7.54 0 9.38-.55a3.02 3.02 0 002.12-2.14C24 15.96 24 12 24 12s0-3.96-.5-5.81zM9.75 15.52V8.48L15.5 12l-5.75 3.52z" />
                                                </svg>
                                            </div>
                                            <div className="min-w-0">
                                                <div className="text-[11px] text-white/50 mb-0.5">YouTube</div>
                                                <div className="text-[13px] text-white/75 truncate
                                            group-hover:text-white/95 transition-colors">
                                                    @{youtube}
                                                </div>
                                            </div>
                                        </a>
                                    )}
                                </div>
                            ) : (
                                <div className="px-6 py-4 text-[13px] text-white/20">
                                    No links added yet.
                                </div>
                            )}
                        </div>
                    </div>
                    {/* Right sidebar */}
                    <div className="space-y-6">
                        <div className="p-4 rounded-2xl border border-neutral-700 bg-gradient-to-br from-black/20 to-black/10 h-full">
                            <ReputationBar rep={user.reputation_obj} />
                        </div>
                    </div>
                </div>
                <div className="p-4 rounded-2xl border border-neutral-700 bg-gradient-to-br from-black/20 to-black/10">
                    <h3 className="font-semibold mb-3">Badges</h3>
                    <BadgesList badges={user.badges ?? []} />
                </div>

                <div className="p-6 rounded-2xl border border-neutral-700 bg-gradient-to-br from-black/20 to-black/10">

                    {/* Header */}
                    <div className="flex items-center justify-between mb-4 border-b py-2 border-white/[0.2]">
                        <div className="flex items-center gap-2.5">
                            {/* Clock icon */}
                            <svg width="15" height="15" viewBox="0 0 15 15" fill="none" className="flex-shrink-0">
                                <circle cx="7.5" cy="7.5" r="6.5"
                                    stroke="rgba(251,146,60,0.65)" strokeWidth="1" />
                                <path d="M7.5 4v4l2.5 1.5"
                                    stroke="rgba(251,146,60,0.85)" strokeWidth="1.2" strokeLinecap="round" />
                            </svg>
                            <h3 className="text-[15px] font-medium tracking-tight text-white/90">
                                Activity
                            </h3>
                        </div>

                        {/* Live badge */}
                        <div className="flex items-center gap-1.5 text-[11px] text-emerald-400
                        bg-emerald-400/10 border border-emerald-400/25 rounded-full px-2.5 py-1">
                            <span className="relative flex h-1.5 w-1.5">
                                <span className="animate-ping absolute inline-flex h-full w-full
                                    rounded-full bg-emerald-400 opacity-75" />
                                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
                            </span>
                            Live
                        </div>
                    </div>

                    <ActivityFeed username={user.username ?? username ?? ""} />
                </div>

                {/* Owner-only sections */}
                {canEdit && (
                    <div className="space-y-6">
                        <div className="p-6 rounded-2xl border border-neutral-700 bg-gradient-to-br from-black/20 to-black/10">
                            <div className="flex items-center gap-3 mb-3">
                                <ShieldCheck className="w-5 h-5 text-amber-400" />
                                <div>
                                    <div className="font-semibold text-base">Security</div>
                                </div>
                            </div>
                            <LazyErrorBoundary
                                fallback={
                                    <SoftCrashPanel />
                                }
                            >
                                <Suspense fallback={<PanelSkeleton />}>
                                    <SecurityCenterExpanded me={user} />
                                </Suspense>
                            </LazyErrorBoundary>
                        </div>

                        <div className="p-6 rounded-2xl border border-red-500/30 bg-gradient-to-br from-red-900/20 to-black/30">
                            <div className="flex md:flex-row flex-col md:items-center md:justify-between">
                                <div>
                                    <h3 className="font-semibold">Danger Zone</h3>
                                    <p className="mt-2 text-sm text-zinc-400">
                                        Actions here are destructive. You'll be asked to confirm.
                                    </p>
                                </div>
                                <div className="flex items-center gap-2 mt-5 md:mt-0">
                                    <button className="flex items-center gap-2 bg-red-700/90 hover:bg-red-600 px-4 py-2 rounded-xl text-sm transition">
                                        <Trash2 className="w-4 h-4" /> Delete account
                                    </button>
                                </div>
                            </div>
                        </div>
                        {isAdmin && <div className="p-6">
                            <div className="flex md:flex-row flex-col md:items-center md:justify-between">
                                <div>
                                    <h3 className="font-semibold">Go to Admin Panel</h3>
                                    <p className="mt-2 text-sm text-zinc-400">
                                        Access administrative tools and settings for your account.
                                    </p>
                                </div>
                                <div className="flex items-center gap-2 mt-5 md:mt-0">
                                    <button className="flex items-center gap-2 bg-emerald-700 hover:bg-emerald-900 px-4 py-2 rounded-xl text-sm transition"
                                        onClick={() => window.location.href = "/admin"}
                                    >
                                        <Settings className="w-4 h-4" /> Admin
                                    </button>
                                </div>
                            </div>
                        </div>
                        }
                    </div>
                )}

                {canEdit && <EditProfileModal open={editOpen} onClose={() => setEditOpen(false)} user={user} />}
                {canEdit && <AvatarEditorModal open={avatarOpen} onClose={() => setAvatarOpen(false)} username={user.username ?? username} />}
            </div>
        </div>
    );
}
