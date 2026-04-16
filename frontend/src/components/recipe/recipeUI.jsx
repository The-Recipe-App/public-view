/**
 * recipeUI.jsx
 * ─────────────────────────────────────────────────────────────────────────────
 * Shared, reusable UI primitives consumed by Home, Recipes, and RecipeDetail.
 *
 * Exports
 *   LazyImage           - intersection-observer lazy image with skeleton + fade
 *   RecipeErrorBoundary - class component that catches render errors per-card
 *   CardErrorSlot       - shown when a single card fails (doesn't affect others)
 *   PageError           - full-page error state with retry
 *   PageSkeleton        - full-page skeleton while loading
 *   CardSkeleton        - single card skeleton
 */

import React, { Component, useEffect, useRef, useState } from "react";
import { AlertCircle, RefreshCw, WifiOff } from "lucide-react";

// ─────────────────────────────────────────────────────────────────────────────
// LazyImage
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Uses IntersectionObserver (rootMargin: 400px) to defer image loading until
 * near the viewport. Native loading="lazy" is added as a second-line defense
 * for browsers without IO support (extremely rare today).
 *
 * Props
 *   src         {string}   image URL
 *   alt         {string}   accessible alt text
 *   className   {string}   extra classes on the <img>
 *   aspectClass {string}   classes on the wrapping div (controls height)
 *   onError     {function} optional callback if image fails to load
 */
export function LazyImage({
    src,
    alt,
    className = "",
    aspectClass = "w-full h-full",
    onError,
}) {
    const ref = useRef(null);
    const [visible, setVisible] = useState(false);
    const [loaded, setLoaded] = useState(false);
    const [imgError, setImgError] = useState(false);

    useEffect(() => {
        if (!ref.current) return;
        if (!src) return;

        const obs = new IntersectionObserver(
            ([entry]) => {
                if (entry.isIntersecting) {
                    setVisible(true);
                    obs.disconnect();
                }
            },
            { rootMargin: "400px", threshold: 0.02 },
        );
        obs.observe(ref.current);
        return () => obs.disconnect();
    }, [src]);

    const handleError = () => {
        setImgError(true);
        setLoaded(true); // stop spinner
        onError?.();
    };

    return (
        <div
            ref={ref}
            className={`relative overflow-hidden bg-neutral-800 ${aspectClass} ${className}`}
            aria-busy={!loaded}
        >
            {/* Skeleton pulse - shown until image has loaded or errored */}
            {!loaded && (
                <div
                    aria-hidden="true"
                    className="absolute inset-0 animate-pulse bg-gradient-to-br from-neutral-800 to-neutral-900"
                />
            )}

            {/* Image - only mounted once IO fires */}
            {visible && !imgError && src && (
                <img
                    src={src}
                    alt={alt}
                    loading="lazy"
                    decoding="async"
                    onLoad={() => setLoaded(true)}
                    onError={handleError}
                    className={`object-cover w-full h-full transition-opacity duration-500 ${loaded ? "opacity-100" : "opacity-0"
                        } ${className}`}
                    draggable={false}
                />
            )}

            {/* Fallback for broken / missing images */}
            {(imgError || !src) && (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 text-neutral-600 text-xs">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
                        <rect x="3" y="3" width="18" height="18" rx="2" />
                        <circle cx="8.5" cy="8.5" r="1.5" />
                        <polyline points="21 15 16 10 5 21" />
                    </svg>
                    <span>No image</span>
                </div>
            )}
        </div>
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// RecipeErrorBoundary
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Class component (required for componentDidCatch).
 * Wraps a single recipe card so a render error is isolated.
 * Other cards continue to render normally.
 *
 * Usage
 *   <RecipeErrorBoundary recipeId={r.id} recipeTitle={r.title}>
 *     <RecipeCard ... />
 *   </RecipeErrorBoundary>
 */
export class RecipeErrorBoundary extends Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error) {
        return { hasError: true, error };
    }

    componentDidCatch(error, info) {
        console.error(
            `[RecipeErrorBoundary] Recipe ${this.props.recipeId} failed to render`,
            error,
            info,
        );
    }

    render() {
        if (this.state.hasError) {
            return (
                <CardErrorSlot
                    recipeId={this.props.recipeId}
                    recipeTitle={this.props.recipeTitle}
                    onRetry={() => this.setState({ hasError: false, error: null })}
                />
            );
        }
        return this.props.children;
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// CardErrorSlot - in-place error UI for a single failed card
// ─────────────────────────────────────────────────────────────────────────────

export function CardErrorSlot({ recipeId, recipeTitle, onRetry }) {
    return (
        <article
            className="bg-black/40 rounded-xl overflow-hidden border border-red-900/30 flex flex-col items-center justify-center gap-3 p-6 min-h-[220px] text-center"
            aria-label={`Failed to load recipe${recipeTitle ? `: ${recipeTitle}` : ""}`}
        >
            <AlertCircle size={24} className="text-red-500/70" />
            <div>
                <p className="text-sm text-neutral-300 font-medium">
                    {recipeTitle ?? `Recipe #${recipeId}`}
                </p>
                <p className="text-xs text-neutral-500 mt-1">Couldn't render this card</p>
            </div>
            {onRetry && (
                <button
                    onClick={onRetry}
                    className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md bg-neutral-800 hover:bg-neutral-700 text-neutral-300 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400"
                >
                    <RefreshCw size={12} />
                    Retry
                </button>
            )}
        </article>
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// PageError - full-page error state
// ─────────────────────────────────────────────────────────────────────────────

const ERROR_MESSAGES = {
    0: { title: "No connection", body: "Check your network and try again.", icon: WifiOff },
    404: { title: "Not found", body: "This resource doesn't exist.", icon: AlertCircle },
    500: { title: "Server error", body: "Something went wrong on our end.", icon: AlertCircle },
};

function getErrorMeta(error) {
    const status = error?.status;
    if (status && ERROR_MESSAGES[status]) return ERROR_MESSAGES[status];
    if (!navigator.onLine) return ERROR_MESSAGES[0];
    return { title: "Something went wrong", body: error?.message ?? "Please try again.", icon: AlertCircle };
}

export function PageError({ error, onRetry, className = "" }) {
    const { title, body, icon: Icon } = getErrorMeta(error);
    return (
        <div
            role="alert"
            className={`flex flex-col items-center justify-center gap-4 py-20 text-center ${className}`}
        >
            <div className="p-4 rounded-full bg-neutral-900 border border-white/5">
                <Icon size={28} className="text-neutral-500" />
            </div>
            <div>
                <h2 className="text-lg font-semibold text-white">{title}</h2>
                <p className="text-sm text-neutral-400 mt-1 max-w-xs">{body}</p>
            </div>
            {onRetry && (
                <button
                    onClick={onRetry}
                    className="flex items-center gap-2 px-4 py-2 rounded-md bg-neutral-800 hover:bg-neutral-700 text-neutral-200 text-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400"
                >
                    <RefreshCw size={14} />
                    Try again
                </button>
            )}
        </div>
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// Skeletons
// ─────────────────────────────────────────────────────────────────────────────

/** Single card skeleton - matches RecipeCard proportions exactly */
export function CardSkeleton() {
    return (
        <article
            aria-busy="true"
            aria-label="Loading recipe"
            className="bg-black/40 rounded-xl overflow-hidden"
        >
            {/* image area */}
            <div className="aspect-[4/3] animate-pulse bg-gradient-to-br from-neutral-800 to-neutral-900" />
            {/* body */}
            <div className="p-4 space-y-3">
                <div className="h-5 w-3/4 rounded bg-neutral-800 animate-pulse" />
                <div className="h-3 w-1/3 rounded bg-neutral-800 animate-pulse" />
                <div className="flex gap-4">
                    <div className="h-3 w-12 rounded bg-neutral-800 animate-pulse" />
                    <div className="h-3 w-12 rounded bg-neutral-800 animate-pulse" />
                    <div className="h-3 w-12 rounded bg-neutral-800 animate-pulse" />
                </div>
                <div className="flex gap-2">
                    <div className="h-5 w-14 rounded bg-neutral-800 animate-pulse" />
                    <div className="h-5 w-14 rounded bg-neutral-800 animate-pulse" />
                </div>
            </div>
        </article>
    );
}

/**
 * Grid of card skeletons - drop into any page grid while loading.
 * count = number of skeleton cards to render.
 */
export function CardSkeletonGrid({ count = 8, className = "" }) {
    return (
        <div
            aria-busy="true"
            aria-label="Loading recipes"
            className={`grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 ${className}`}
        >
            {Array.from({ length: count }).map((_, i) => (
                <CardSkeleton key={i} />
            ))}
        </div>
    );
}

/** Full-page skeleton for the Recipes surface */
export function PageSkeleton({ count = 8 }) {
    return (
        <div className="px-6 py-6 max-w-[1500px] mx-auto">
            {/* header skeleton */}
            <div className="mb-6 space-y-2">
                <div className="h-8 w-40 rounded bg-neutral-800 animate-pulse" />
                <div className="h-4 w-72 rounded bg-neutral-800 animate-pulse" />
            </div>
            <CardSkeletonGrid count={count} />
        </div>
    );
}

/** Horizontal strip skeleton for Home's "live" section */
export function LiveStripSkeleton({ count = 3 }) {
    return (
        <div className="flex gap-4">
            {Array.from({ length: count }).map((_, i) => (
                <div
                    key={i}
                    className="min-w-[72vw] sm:w-[260px] md:w-[220px] flex-shrink-0 bg-[#0b0b0b] border border-white/5 rounded-lg overflow-hidden"
                >
                    <div className="h-40 animate-pulse bg-neutral-800" />
                    <div className="p-3 space-y-2">
                        <div className="h-4 w-3/4 rounded bg-neutral-800 animate-pulse" />
                        <div className="h-3 w-1/4 rounded bg-neutral-800 animate-pulse" />
                    </div>
                </div>
            ))}
        </div>
    );
}
