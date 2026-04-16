// src/components/SearchOverlay.jsx
import React, { useEffect, useRef, useReducer, useCallback } from "react";
import { Search, X, Clock, TrendingUp, Flame, ChefHat, ArrowRight } from "lucide-react";
import { useDebounced, useSearch } from "../hooks/useSearchHooks";

// ─── Reducer ────────────────────────────────────────────────────────────────

const initialState = {
    query:          "",
    activeIndex:    -1,
    recentSearches: JSON.parse(localStorage.getItem("fk_recent") || "[]"),
};

function reducer(state, action) {
    switch (action.type) {
        case "SET_QUERY":
            return { ...state, query: action.payload, activeIndex: -1 };
        case "MOVE_ACTIVE":
            return { ...state, activeIndex: Math.max(-1, Math.min(action.max - 1, state.activeIndex + action.dir)) };
        case "RESET_ACTIVE":
            return { ...state, activeIndex: -1 };
        case "ADD_RECENT": {
            const next = [action.payload, ...state.recentSearches.filter(r => r !== action.payload)].slice(0, 5);
            localStorage.setItem("fk_recent", JSON.stringify(next));
            return { ...state, recentSearches: next };
        }
        case "CLEAR_RECENT":
            localStorage.removeItem("fk_recent");
            return { ...state, recentSearches: [] };
        case "RESET":
            return { ...initialState, recentSearches: state.recentSearches };
        default:
            return state;
    }
}

// ─── Glass tokens (inline style objects) ─────────────────────────────────────
// Keeping them here keeps JSX clean and makes tweaking trivial.

const glass = {
    // The input bar — lighter, more translucent
    input: {
        background:           "rgba(255,255,255,0.07)",
        backdropFilter:       "blur(24px) saturate(160%)",
        WebkitBackdropFilter: "blur(24px) saturate(160%)",
        border:               "1px solid rgba(255,255,255,0.14)",
        borderTopColor:       "rgba(255,255,255,0.22)",
        boxShadow:            "inset 0 1px 0 rgba(255,255,255,0.07), 0 20px 48px rgba(0,0,0,0.45)",
    },
    inputFocused: {
        background:           "rgba(255,255,255,0.07)",
        backdropFilter:       "blur(24px) saturate(160%)",
        WebkitBackdropFilter: "blur(24px) saturate(160%)",
        border:               "1px solid rgba(249,115,22,0.35)",
        borderTopColor:       "rgba(249,115,22,0.45)",
        boxShadow:            "inset 0 1px 0 rgba(255,255,255,0.07), 0 20px 48px rgba(0,0,0,0.5), 0 0 0 3px rgba(249,115,22,0.07)",
    },
    // The dropdown panel — darker, deeper blur
    panel: {
        background:           "rgba(16,13,10,0.78)",
        backdropFilter:       "blur(36px) saturate(180%)",
        WebkitBackdropFilter: "blur(36px) saturate(180%)",
        border:               "1px solid rgba(255,255,255,0.1)",
        borderTopColor:       "rgba(255,255,255,0.16)",
        boxShadow:            "inset 0 1px 0 rgba(255,255,255,0.06), 0 32px 64px rgba(0,0,0,0.6), 0 0 0 1px rgba(0,0,0,0.35)",
    },
};

// ─── Skeleton loader ──────────────────────────────────────────────────────────

function SkeletonRows() {
    return (
        <div className="p-1.5">
            {[52, 40, 62].map((w, i) => (
                <div key={i} className="flex items-center gap-2.5 px-3 py-2.5 rounded-xl">
                    <div className="w-8 h-8 rounded-[9px] bg-white/[0.05] shrink-0 animate-pulse" />
                    <div className="flex-1 space-y-1.5">
                        <div className="h-2.5 rounded-full bg-white/[0.06] animate-pulse" style={{ width: `${w}%` }} />
                        <div className="h-2 rounded-full bg-white/[0.04] animate-pulse w-4/5" />
                    </div>
                </div>
            ))}
        </div>
    );
}

// ─── Result row ───────────────────────────────────────────────────────────────

function ResultRow({ result, isActive, onSelect, onHover, delay }) {
    const title   = result.title   ?? "Untitled";
    const cuisine = result.cuisine;
    const time    = result.cook_time_minutes;
    const snippet = (result.description || result.body || "").slice(0, 105);

    return (
        <button
            onMouseEnter={onHover}
            onClick={onSelect}
            className="group w-full text-left flex items-center gap-2.5 px-3 py-2.5 rounded-[11px] outline-none transition-colors duration-100"
            style={{
                background:      isActive ? "rgba(249,115,22,0.07)" : "transparent",
                animation:       `fk-row-in 0.16s cubic-bezier(0.16,1,0.3,1) ${delay}ms both`,
            }}
            onMouseOver={e => { if (!isActive) e.currentTarget.style.background = "rgba(255,255,255,0.04)"; }}
            onMouseOut={e  => { if (!isActive) e.currentTarget.style.background = "transparent"; }}
        >
            {/* Icon */}
            <span
                className="shrink-0 w-8 h-8 rounded-[9px] flex items-center justify-center transition-colors duration-100"
                style={{ background: isActive ? "rgba(249,115,22,0.15)" : "rgba(255,255,255,0.05)" }}
            >
                <ChefHat
                    size={14}
                    style={{ color: isActive ? "rgba(249,115,22,0.9)" : "rgba(255,255,255,0.22)",
                             transition: "color 0.1s" }}
                />
            </span>

            {/* Text */}
            <div className="flex-1 min-w-0">
                <p className="text-[13.5px] font-normal text-white/85 truncate leading-snug">{title}</p>
                {snippet && (
                    <p className="text-[11.5px] text-white/32 truncate mt-0.5 leading-snug">{snippet}</p>
                )}
            </div>

            {/* Tags */}
            <div className="flex items-center gap-1.5 shrink-0">
                {time && <span className="text-[10.5px] text-white/25">{time}m</span>}
                {cuisine && (
                    <span
                        className="text-[10px] px-1.5 py-0.5 rounded-md text-white/28"
                        style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)" }}
                    >
                        {cuisine}
                    </span>
                )}
            </div>

            {/* Arrow */}
            <ArrowRight
                size={12}
                className="shrink-0 transition-all duration-150"
                style={{
                    color:     isActive ? "rgba(249,115,22,0.55)" : "transparent",
                    transform: isActive ? "translateX(0)" : "translateX(-3px)",
                    opacity:   isActive ? 1 : 0,
                }}
            />
        </button>
    );
}

// ─── Overlay ─────────────────────────────────────────────────────────────────

export default function SearchOverlay({ open, onClose }) {
    const inputRef = useRef(null);
    const listRef  = useRef(null);
    const [state, dispatch] = useReducer(reducer, initialState);

    const debouncedQuery          = useDebounced(state.query, 380);
    const { results, loading, error } = useSearch(debouncedQuery, 20);

    // ── Back-button / swipe-back close ───────────────────────────────────────
    useEffect(() => {
        if (!open) return;
        window.history.pushState({ searchOverlay: true }, "");
        const onPop = () => onClose();
        window.addEventListener("popstate", onPop);
        return () => {
            window.removeEventListener("popstate", onPop);
            if (window.history.state?.searchOverlay) window.history.back();
        };
    }, [open]);

    // ── Focus ────────────────────────────────────────────────────────────────
    useEffect(() => {
        if (!open) return;
        const t = setTimeout(() => inputRef.current?.focus(), 55);
        return () => clearTimeout(t);
    }, [open]);

    // ── Scroll lock ──────────────────────────────────────────────────────────
    useEffect(() => {
        if (!open) return;
        const prev = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        return () => { document.body.style.overflow = prev; };
    }, [open]);

    // ── Reset on close ───────────────────────────────────────────────────────
    useEffect(() => {
        if (!open) dispatch({ type: "RESET" });
    }, [open]);

    // ── Keyboard ─────────────────────────────────────────────────────────────
    useEffect(() => {
        const fn = (e) => {
            if (!open) return;
            if (e.key === "Escape")    { onClose(); return; }
            if (e.key === "ArrowDown") { e.preventDefault(); dispatch({ type: "MOVE_ACTIVE", dir:  1, max: results.length }); }
            if (e.key === "ArrowUp")   { e.preventDefault(); dispatch({ type: "MOVE_ACTIVE", dir: -1, max: results.length }); }
            if (e.key === "Enter" && state.activeIndex >= 0 && results[state.activeIndex]) {
                handleSelect(results[state.activeIndex]);
            }
        };
        document.addEventListener("keydown", fn);
        return () => document.removeEventListener("keydown", fn);
    }, [open, results, state.activeIndex, onClose]);

    // ── Scroll active into view ───────────────────────────────────────────────
    useEffect(() => {
        if (state.activeIndex < 0 || !listRef.current) return;
        listRef.current.children[state.activeIndex]?.scrollIntoView({ block: "nearest" });
    }, [state.activeIndex]);

    const handleSelect = useCallback((result) => {
        dispatch({ type: "ADD_RECENT", payload: result.title });
        window.location.href = `/recipes/${result.id}`;
    }, []);

    const handleTrending = useCallback((term) => {
        dispatch({ type: "SET_QUERY", payload: term });
        inputRef.current?.focus();
    }, []);

    const isIdle      = !debouncedQuery || state.query.length < 3;
    const isLoading   = !isIdle && loading;
    const showResults = !isIdle && !loading && !error && results.length > 0;
    const showEmpty   = !isIdle && !loading && !error && results.length === 0 && state.query.length >= 3;

    if (!open) return null;

    return (
        <>
            <style>{`
                @keyframes fk-backdrop { from{opacity:0} to{opacity:1} }
                @keyframes fk-panel    { from{opacity:0;transform:translateY(-11px) scale(0.983)} to{opacity:1;transform:none} }
                @keyframes fk-row-in   { from{opacity:0;transform:translateX(-5px)} to{opacity:1;transform:none} }
                @keyframes fk-fade-up  { from{opacity:0;transform:translateY(5px)} to{opacity:1;transform:none} }
                input[type="search"]::-webkit-search-cancel-button { display:none }
                .fk-no-scroll::-webkit-scrollbar { display:none }
            `}</style>

            {/* ── Backdrop ── */}
            <div
                className="fixed inset-0 z-[200] flex flex-col items-center px-4"
                style={{
                    background:           "rgba(0,0,0,0.72)",
                    backdropFilter:       "blur(14px)",
                    WebkitBackdropFilter: "blur(14px)",
                    animation:            "fk-backdrop 0.16s ease",
                }}
                onClick={onClose}
                role="dialog"
                aria-modal="true"
                aria-label="Search"
            >
                {/* ── Panel ── */}
                <div
                    className="w-full max-w-[600px] mt-[68px]"
                    style={{ animation: "fk-panel 0.22s cubic-bezier(0.16,1,0.3,1)" }}
                    onClick={e => e.stopPropagation()}
                >
                    {/* ── Input ── */}
                    <div
                        onClick={() => inputRef.current?.focus()}
                        className="flex items-center gap-3 h-[54px] px-4 rounded-2xl cursor-text transition-all duration-200"
                        style={state.query ? glass.inputFocused : glass.input}
                    >
                        {isLoading ? (
                            <span className="shrink-0 w-4 h-4 rounded-full border-2 border-white/15 border-t-orange-400 animate-spin" />
                        ) : (
                            <Search
                                size={16}
                                className="shrink-0 transition-colors duration-200"
                                style={{ color: state.query ? "rgba(249,115,22,0.6)" : "rgba(255,255,255,0.28)" }}
                            />
                        )}

                        <input
                            ref={inputRef}
                            value={state.query}
                            onChange={e => dispatch({ type: "SET_QUERY", payload: e.target.value })}
                            type="search"
                            placeholder="Search recipes, techniques, cooks…"
                            className="flex-1 bg-transparent text-[15px] font-light text-white/90 placeholder-white/22 outline-none"
                            aria-label="Search"
                            autoComplete="off"
                            spellCheck={false}
                        />

                        {state.query ? (
                            <button
                                onClick={e => { e.stopPropagation(); dispatch({ type: "SET_QUERY", payload: "" }); inputRef.current?.focus(); }}
                                className="shrink-0 w-5 h-5 flex items-center justify-center rounded-full transition-colors duration-150"
                                style={{ background: "rgba(255,255,255,0.07)", border: "1px solid rgba(255,255,255,0.1)" }}
                                aria-label="Clear"
                            >
                                <X size={10} className="text-white/45" />
                            </button>
                        ) : (
                            <kbd
                                className="shrink-0 text-[10px] font-mono rounded px-1.5 py-0.5"
                                style={{ color: "rgba(255,255,255,0.2)", background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.09)" }}
                            >
                                ESC
                            </kbd>
                        )}
                    </div>

                    {/* ── Dropdown ── */}
                    <div className="mt-1.5 rounded-[18px] overflow-hidden" style={glass.panel}>

                        {/* Amber top-line accent */}
                        <div
                            className="h-px w-full"
                            style={{ background: "linear-gradient(90deg, transparent 5%, rgba(249,115,22,0.28) 30%, rgba(249,115,22,0.28) 70%, transparent 95%)" }}
                        />

                        {/* ── Idle ── */}
                        {isIdle && (
                            <>
                                {state.recentSearches.length > 0 && (
                                    <>
                                        <div className="flex items-center justify-between px-4 pt-3 pb-1">
                                            <span className="flex items-center gap-1.5 text-[9.5px] font-medium tracking-[0.11em] uppercase text-white/22">
                                                <Clock size={10} />
                                                Recent
                                            </span>
                                            <button
                                                onClick={() => dispatch({ type: "CLEAR_RECENT" })}
                                                className="text-[10px] text-white/22 transition-colors duration-150 hover:text-orange-400/75"
                                            >
                                                Clear
                                            </button>
                                        </div>
                                        <div className="px-1.5 pb-1">
                                            {state.recentSearches.map((r, i) => (
                                                <button
                                                    key={r}
                                                    onClick={() => handleTrending(r)}
                                                    className="group flex items-center gap-2.5 w-full px-3 py-2 rounded-xl transition-colors duration-100 text-left"
                                                    style={{ animation: `fk-row-in 0.14s ease ${i * 35}ms both` }}
                                                    onMouseOver={e  => e.currentTarget.style.background = "rgba(255,255,255,0.04)"}
                                                    onMouseOut={e   => e.currentTarget.style.background = "transparent"}
                                                >
                                                    <Clock size={12} className="text-white/20 shrink-0" />
                                                    <span className="text-[13px] font-light text-white/42 group-hover:text-white/68 transition-colors duration-100">{r}</span>
                                                    <ArrowRight size={11} className="ml-auto text-white/0 group-hover:text-white/22 transition-all duration-150 -translate-x-1 group-hover:translate-x-0" />
                                                </button>
                                            ))}
                                        </div>
                                    </>
                                )}
                            </>
                        )}

                        {/* ── Loading skeleton ── */}
                        {isLoading && <SkeletonRows />}

                        {/* ── Error ── */}
                        {error && (
                            <div
                                className="mx-3 my-3 px-3 py-2.5 rounded-xl text-[12.5px] text-red-300/60"
                                style={{ background: "rgba(239,68,68,0.06)", border: "1px solid rgba(239,68,68,0.12)" }}
                            >
                                {error.status === 503
                                    ? "Search is warming up — try again in a moment."
                                    : `Something went wrong: ${error.message}`}
                            </div>
                        )}

                        {/* ── Empty ── */}
                        {showEmpty && (
                            <div className="flex flex-col items-center gap-1.5 py-10 text-center" style={{ animation: "fk-fade-up 0.18s ease both" }}>
                                <p className="text-[13px] text-white/25">
                                    Nothing for <span className="text-white/42">"{debouncedQuery}"</span>
                                </p>
                                <p className="text-[11px] text-white/16">Try a different keyword</p>
                            </div>
                        )}

                        {/* ── Results ── */}
                        {showResults && (
                            <>
                                <div className="flex items-center gap-1.5 px-4 py-2.5" style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                                    <span className="text-[11px] text-white/25">
                                        <span className="text-white/50 font-medium">{results.length}</span>
                                        {" "}results for{" "}
                                        <span style={{ color: "rgba(249,115,22,0.6)", fontWeight: 500 }}>"{debouncedQuery}"</span>
                                    </span>
                                </div>
                                <div
                                    ref={listRef}
                                    className="fk-no-scroll p-1.5 max-h-[52vh] overflow-y-auto overscroll-contain"
                                    style={{ scrollbarWidth: "none" }}
                                    role="listbox"
                                >
                                    {results.map((r, i) => (
                                        <ResultRow
                                            key={r.id}
                                            result={r}
                                            isActive={i === state.activeIndex}
                                            delay={i * 36}
                                            onSelect={() => handleSelect(r)}
                                            onHover={() => dispatch({ type: "RESET_ACTIVE" })}
                                        />
                                    ))}
                                </div>
                            </>
                        )}

                        {/* ── Footer ── */}
                        <div
                            className="flex items-center justify-between px-4 py-2"
                            style={{ borderTop: "1px solid rgba(255,255,255,0.05)" }}
                        >
                            <div className="flex items-center gap-3">
                                {[["↑↓", "navigate"], ["↵", "open"]].map(([k, l]) => (
                                    <span key={k} className="flex items-center gap-1 text-[10px] text-white/16">
                                        <kbd
                                            className="px-1 py-0.5 rounded text-[9.5px] font-mono"
                                            style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)" }}
                                        >{k}</kbd>
                                        {l}
                                    </span>
                                ))}
                            </div>
                            <span className="flex items-center gap-1 text-[10px] text-white/16">
                                <kbd
                                    className="px-1 py-0.5 rounded text-[9.5px] font-mono"
                                    style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)" }}
                                >esc</kbd>
                                close
                            </span>
                        </div>
                    </div>
                </div>
            </div>
        </>
    );
}