// RecipeDetail.jsx
// ─────────────────────────────────────────────────────────────────────────────
// Single recipe detail page.
//
// Error handling strategy
//   • 404              → NotFoundCard with suggestions
//   • Any other error  → PageError with retry
//   • Missing image    → LazyImage fallback
//   • Recommendations fail → silently hidden (non-critical)
//
// Data
//   useRecipe(id)            - detail data
//   useRecommendations(id)   - sidebar / related (gracefully degraded)
//   Falls back to MOCK_RECIPES when API is unavailable.
// ─────────────────────────────────────────────────────────────────────────────

import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
    GitFork,
    Clock,
    Flame,
    ChevronRight,
    Lock,
    Heart,
    Eye,
    HandPlatter,
    Flag,
    ListOrdered,
    Leaf,
    AlertTriangle,
    Upload,
    ExternalLink,
} from "lucide-react";
import { useContextManager } from "../features/ContextProvider";
import { useRecipe, useRecommendations, MOCK_RECIPES, normalizeRecipe, favoriteRecipe } from "../components/recipe/recipeData";
import { LazyImage, PageError, CardSkeleton } from "../components/recipe/recipeUI";
import backendUrlV1 from "../urls/backendUrl";
import { Tooltip } from "react-tooltip";

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function getWikipediaSlug(ingredient) {
    let text = ingredient.toLowerCase()
        .replace(/\(.*?\)|\[.*?\]|\{.*?\}/g, "")
        .replace(/\d+\/\d+|\d+/g, "")
        .replace(
            /\b(grams?|kg|g|ml|l|tbsp?|tsp?|tablespoons?|teaspoons?|cups?|fl_oz|oz|pounds?|lb|pinch|pieces?|of|and|or|to|for|a|an|fresh|chopped|sliced|diced|minced|finely|coarsely)\b/gi,
            "",
        )
        .replace(/[.,;:]/g, "")
        .replace(/\s+/g, " ")
        .trim();

    const words = text.split(" ");
    const core = words.length > 3 ? words.slice(-2).join(" ") : text;
    return core.replace(/\s+/g, "_");
}

// ─────────────────────────────────────────────────────────────────────────────
// Page root
// ─────────────────────────────────────────────────────────────────────────────

export default function RecipeDetail() {
    const { id } = useParams();
    const navigate = useNavigate();
    const { isAuthorized, setIsLoading } = useContextManager();

    const { data: recipe, isLoading, isError, error, reload: refetch } = useRecipe(id);

    useEffect(() => {
        setIsLoading(false);
    }, []);

    useEffect(() => {
        window.scrollTo({ top: 0, behavior: "smooth" });
    }, [id]);

    // ── Loading ──
    if (isLoading) return <DetailSkeleton />;

    // ── 404 ──
    if (error?.status === 404 || (!isLoading && !recipe)) {
        const fallback = MOCK_RECIPES.find((r) => r.id === id);
        if (fallback) return <RecipeDetailContent recipe={fallback} isAuthorized={isAuthorized} navigate={navigate} />;
        return (
            <div className="max-w-[1000px] mx-auto px-6 py-12">
                <NotFoundCard id={id} navigate={navigate} isAuthorized={isAuthorized} />
            </div>
        );
    }

    // ── Other error ──
    if (isError) {
        return (
            <div className="max-w-[1200px] mx-auto px-6 py-6">
                <PageError error={error} onRetry={refetch} className="min-h-[60vh]" />
            </div>
        );
    }

    return <RecipeDetailContent recipe={recipe} isAuthorized={isAuthorized} navigate={navigate} />;
}

// ─────────────────────────────────────────────────────────────────────────────
// Skeleton
// ─────────────────────────────────────────────────────────────────────────────

function DetailSkeleton() {
    return (
        <div className="animate-pulse">
            {/* Hero */}
            <div className="w-full h-[420px] bg-neutral-900" />
            <div className="max-w-[1200px] mx-auto px-6 py-8">
                <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-10">
                    <div className="space-y-4">
                        <div className="h-12 w-full bg-neutral-800 rounded-2xl" />
                        <div className="h-12 w-full bg-neutral-800 rounded-2xl" />
                        <div className="h-28 w-full bg-neutral-900 rounded-2xl" />
                    </div>
                    <div className="space-y-6">
                        <div className="h-5 w-3/4 bg-neutral-800 rounded" />
                        <div className="h-4 w-1/2 bg-neutral-800 rounded" />
                        <div className="space-y-2">
                            {Array.from({ length: 5 }).map((_, i) => (
                                <div key={i} className="h-12 bg-neutral-900 rounded-2xl" />
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main content
// ─────────────────────────────────────────────────────────────────────────────

function RecipeDetailContent({ recipe, isAuthorized, navigate }) {
    return (
        <div className="min-h-screen">
            {/* ── Hero ── */}
            <Hero recipe={recipe} isAuthorized={isAuthorized} navigate={navigate} />

            {/* ── Body ── */}
            <div className="max-w-[1200px] mx-auto px-4 sm:px-6 py-8">
                <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-10 mb-10 border-b border-neutral-500">
                    <Sidebar recipe={recipe} isAuthorized={isAuthorized} navigate={navigate} />
                    <TableBody recipe={recipe} isAuthorized={isAuthorized} navigate={navigate} />
                </div>
                {/* Steps */}
                {recipe.steps?.length > 0 && <Steps steps={recipe.steps} />}
            </div>
        </div>
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// Hero - full-bleed cover with gradient fade + title overlay
// ─────────────────────────────────────────────────────────────────────────────

function Hero({ recipe, isAuthorized, navigate }) {
    const [favorited, setFavorited] = useState(recipe.status?.isFavorited ?? false);

    useEffect(() => {
        setFavorited(recipe.status?.isFavorited ?? false);
    }, [recipe]);

    const toggleFavorite = async () => {
        if (!isAuthorized) return;
        setFavorited(f => !f); // optimistic - instant UI update
        try {
            await favoriteRecipe(recipe.id);
        } catch {
            setFavorited(f => !f); // revert on failure
        }
    };

    return (
        <div className="relative w-full overflow-hidden" style={{ height: "min(480px, 55vw)", minHeight: 280 }}>
            {/* Background image */}
            {recipe.media?.imageUrl ? (
                <img
                    src={recipe.media.imageUrl}
                    alt={recipe.title}
                    className="absolute inset-0 w-full h-full object-cover"
                    loading="eager"
                    style={{ maskImage: "linear-gradient(to bottom, black 40%, transparent 100%)", WebkitMaskImage: "linear-gradient(to bottom, black 40%, transparent 100%)" }}
                />
            ) : (
                <div className="absolute inset-0 bg-[#0a0a0a] flex items-center justify-center text-[#1a1a1a] text-8xl">⬡</div>
            )}

            {/* Content anchored to the bottom */}
            <div className="absolute inset-x-0 bottom-0 px-4 sm:px-6 pb-7 max-w-[1200px] mx-auto">

                {/* Title */}
                <h1
                    className="text-3xl sm:text-4xl font-semibold text-white leading-tight mb-3"
                    style={{ fontFamily: "'Georgia', serif", textShadow: "0 2px 20px rgba(0,0,0,0.5)" }}
                >
                    {recipe.title}
                </h1>

                {/* Author row */}
                <div className="flex items-center gap-2.5 mb-4">
                    <div data-tooltip-id="author-username" className="flex flex-row gap-2.5 items-center text-white hover:text-orange-300 hover:underline transition-colors cursor-pointer"
                        onClick={() => window.open(`/profile/${recipe.author?.username}`, "_blank")}>
                        <img
                            src={recipe.author?.avatar_url || `https://api.dicebear.com/7.x/thumbs/svg?seed=${recipe.author?.username}`}
                            className="w-6 h-6 rounded-full bg-neutral-800 ring-1 ring-white"
                            alt={`${recipe.author?.username} avatar`}
                            loading="lazy"
                        />
                        <span className="text-sm ">
                            {recipe.author?.username}
                        </span>
                    </div>
                    <Tooltip style={{ backgroundColor: "rgba(25, 25, 25, 0.9)" }} id="author-username" content="Go to profile" />

                    {/* Inline stats */}
                    <div className="flex items-center gap-3 ml-2">
                        <span className="flex items-center gap-1 text-white text-xs">
                            <GitFork size={11} /> {recipe.lineage?.forksCount ?? 0}
                        </span>
                        <span className="flex items-center gap-1 text-white text-xs">
                            <Eye size={11} /> {recipe.stats?.views?.toLocaleString() ?? 0}
                        </span>
                        {recipe.meta?.timeMinutes != null && (
                            <span className="flex items-center gap-1 text-white text-xs">
                                <Clock size={11} /> {recipe.meta.timeMinutes}m
                            </span>
                        )}
                        {recipe.meta?.difficulty && (
                            <span className="flex items-center gap-1 text-white text-xs capitalize">
                                <Flame size={11} /> {recipe.meta.difficulty}
                            </span>
                        )}
                    </div>
                </div>

                {/* Action row */}
                <div className="flex items-center gap-2 flex-wrap">
                    <button
                        disabled={!isAuthorized}
                        onClick={() => navigate(`/recipes/${recipe.id}/fork`)}
                        className="flex items-center gap-2 px-4 py-2 rounded-xl bg-amber-500 text-black text-sm font-semibold
                            hover:bg-amber-400 active:scale-[0.98] transition-all duration-200
                            disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                        <GitFork size={13} />
                        Fork this recipe
                    </button>

                    {!isAuthorized && (
                        <button
                            onClick={() => { localStorage.setItem("redirectAfterLogin", window.location.pathname); navigate("/login"); }}
                            className="text-xs text-amber-400/80 flex items-center gap-1.5 px-3 py-2 rounded-xl border border-amber-500/20 hover:border-amber-500/40 transition-colors"
                        >
                            <Lock size={12} />
                            Sign in to fork
                        </button>
                    )}

                    {/* Favorite */}
                    <button
                        aria-label={favorited ? "Remove from favorites" : "Add to favorites"}
                        onClick={toggleFavorite}
                        data-tooltip-id="favorite"
                        className={`p-2 rounded-xl border transition-all duration-200
                            ${favorited
                                ? "bg-red-500/30 border-red-500 text-red-400 hover:bg-red-500/40 hover:border-red-500/40"
                                : "bg-white/5 border-white/70 text-white/70 hover:border-white hover:text-red-400"
                            }`}
                    >
                        <Heart size={15} className={favorited ? "fill-red-500" : ""} />
                    </button>
                    <Tooltip style={{ backgroundColor: "rgba(25, 25, 25, 0.9)" }} id="favorite" content={favorited ? "Remove from favorites" : "Add to favorites"} />
                </div>
            </div>
        </div>
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// Sidebar - sticky on desktop
// ─────────────────────────────────────────────────────────────────────────────

function Sidebar({ recipe, isAuthorized, navigate }) {
    return (
        <aside className="flex flex-col gap-4 lg:sticky lg:top-6 lg:h-fit">

            {/* Draft publish */}
            {recipe.status?.isDraft && (
                <div className="rounded-2xl border border-amber-500/15 bg-amber-500/5 p-4">
                    <p className="text-xs text-amber-400/70 mb-3 flex items-center gap-2">
                        <span className="w-1.5 h-1.5 rounded-full bg-amber-500/60 animate-pulse" />
                        Draft - not publicly visible
                    </p>
                    <button
                        disabled={!isAuthorized}
                        onClick={() => fetch(`${backendUrlV1}/recipes/${recipe.id}/publish`, { method: "POST", credentials: "include" })}
                        className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-amber-500 text-black text-xs font-semibold
                            hover:bg-amber-400 transition-colors disabled:opacity-40 disabled:cursor-not-allowed w-full justify-center"
                    >
                        <Upload size={12} />
                        Publish this draft
                    </button>
                </div>
            )}

            {/* Moderation */}
            {recipe.moderation && (recipe.moderation.viewerReported || recipe.moderation.recentReports) && (
                <ModerationBanner moderation={recipe.moderation} />
            )}

            {/* Description */}
            {recipe.body && (
                <p className="text-white text-sm leading-relaxed lg:hidden">{recipe.body}</p>
            )}

            {/* Description on desktop */}
            {recipe.body && (
                <p className="hidden lg:block text-white text-xs leading-relaxed border-t border-[#505050] pt-4 mb-5">
                    {recipe.body}
                </p>
            )}
        </aside>
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// Body - ingredients + steps
// ─────────────────────────────────────────────────────────────────────────────

function TableBody({ recipe }) {
    return (
        <div className="flex flex-col gap-10">
            {/* Ingredients */}
            {recipe.ingredients?.length > 0 ? (
                <Ingredients ingredients={recipe.ingredients} />
            ) : (
                <p className="text-sm text-neutral-500 italic">Ingredients not available.</p>
            )}
        </div>
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// Ingredients
// ─────────────────────────────────────────────────────────────────────────────

function Ingredients({ ingredients }) {
    const hasFlags = ingredients.some(i => i?.isAnimal || i?.isAllergen);

    return (
        <section>
            <div className="flex flex-col gap-3 mb-5">
                <div className="flex flex-row items-center gap-x-3">
                    <span className="text-amber-500 text-base leading-none">◈</span>
                    <h2 className="text-white/80 text-base font-semibold leading-tight">Ingredients</h2>
                    <p className="text-neutral-200 bg-[#0d0d0d] items-center border border-[#303030] rounded-3xl px-4 py-1 text-xs">{ingredients.length} items</p>
                </div>
                {hasFlags && (
                    <div className="flex flex-col md:flex-row items-start gap-3 text-[12px] text-neutral-200">
                        This recipe has ingredients marked as:
                        <span className="flex items-center gap-1">
                            <Leaf size={10} className="text-amber-500/80" /> Animal-Derived Ingredient
                        </span>
                        <span className="flex items-center gap-1">
                            <AlertTriangle size={10} className="text-orange-500/80" /> Common Allergen
                        </span>
                    </div>
                )}
            </div>

            <ul className="grid md:grid-cols-2 gap-1.5 mb-5">
                {ingredients.map((item, i) => {
                    const name = typeof item === "string" ? item : item.name;
                    const isAnimal = item?.isAnimal ?? false;
                    const isAllergen = item?.isAllergen ?? false;
                    const quantity = item?.quantity;
                    const unit = item?.unit;
                    const slug = getWikipediaSlug(name);
                    const wikiUrl = `https://en.wikipedia.org/wiki/${slug}`;

                    return (
                        <li key={item?.id ?? i}
                            className={`flex items-center gap-3 px-4 py-1 rounded-2xl
                                hover:bg-[#242424] transition-colors duration-200 group`}>
                            {/* Bullet */}
                            <span className="text-amber-500/85 text-[8px] flex-shrink-0">●</span>

                            {/* Name + badges */}
                            <span className="text-neutral-300 text-sm flex-1 min-w-0 truncate">
                                {name.split(" ").map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ")}
                            </span>

                            {/* Dietary badges */}
                            <div className="flex items-center gap-1.5 flex-shrink-0">
                                {isAnimal && (
                                    <span data-tooltip-id={`dietary-badges-animal-${i}`}
                                        className="flex items-center gap-1 text-[10px] text-white bg-amber-500/8 border border-amber-500/15 px-1.5 py-0.5 rounded-full cursor-default">
                                        <Leaf size={12} className="text-amber-500" />
                                    </span>
                                )}
                                {isAllergen && (
                                    <span data-tooltip-id={`dietary-badges-allergen-${i}`}
                                        className="flex items-center gap-1 text-[10px] text-white bg-orange-500/8 border border-orange-500/15 px-1.5 py-0.5 rounded-full cursor-default">
                                        <AlertTriangle size={12} className="text-amber-500" />
                                    </span>
                                )}
                                <Tooltip style={{ backgroundColor: "rgba(25, 25, 25, 0.9)" }} id={`dietary-badges-allergen-${i}`} content="Common Allergen" />
                                <Tooltip style={{ backgroundColor: "rgba(25, 25, 25, 0.9)" }} id={`dietary-badges-animal-${i}`} content="Animal-Derived Ingredient" />
                            </div>

                            {/* Quantity */}
                            {(quantity || unit) && (
                                <span className="text-neutral-300 text-xs flex-shrink-0 min-w-[48px] text-right">
                                    {quantity}{unit ? ` ${unit}` : ""}
                                </span>
                            )}

                            {/* Wikipedia link - subtle, only visible on hover */}
                            <a
                                href={wikiUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                data-tooltip-content={`About ${name.split(" ").map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ")} on Wikipedia`}
                                data-tooltip-id={`wikipedia-${name}`}
                                onClick={e => e.stopPropagation()}
                                className="flex-shrink-0 text-neutral-200 hover:text-amber-500 group-hover:opacity-100
                                    transition-all duration-200"
                                aria-label={`Wikipedia: ${name}`}
                            >
                                <ExternalLink size={12} />
                            </a>
                            <Tooltip style={{ backgroundColor: "rgba(25, 25, 25, 0.9)" }} id={`wikipedia-${name}`} />
                        </li>
                    );
                })}
            </ul>
        </section>
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// Steps - timeline style matching RecipeCreate's aesthetic
// ─────────────────────────────────────────────────────────────────────────────

function Steps({ steps }) {
    return (
        <section>
            <div className="flex items-center gap-3 mb-5">
                <div className="flex flex-row items-center gap-x-3">
                    <span className="text-amber-500 text-base leading-none">◎</span>
                    <h2 className="text-white/80 text-base font-semibold leading-tight">Steps</h2>
                    <p className="text-neutral-200 bg-[#0d0d0d] items-center border border-[#303030] rounded-3xl px-4 py-1 text-xs">{steps.length} step{steps.length !== 1 ? "s" : ""}</p>
                </div>
            </div>

            <ol className="flex flex-col gap-0">
                {steps.map((step, i) => (
                    <StepRow key={step.stepNumber ?? i} step={step} idx={i} total={steps.length} />
                ))}
            </ol>
        </section>
    );
}

function StepRow({ step, idx, total }) {
    const [expanded, setExpanded] = useState(false);
    const num = step.stepNumber ?? idx + 1;

    return (
        <div className="flex gap-3 items-start">
            {/* Number + connector column */}
            <div className="flex flex-col items-center flex-shrink-0 w-8">
                <button
                    onClick={() => setExpanded(e => !e)}
                    className={`w-8 h-8 rounded-full text-xs font-bold flex items-center justify-center transition-all duration-300 flex-shrink-0 focus:outline-none
                        ${expanded
                            ? "bg-amber-500 text-black shadow-[0_0_16px_rgba(232,160,32,0.25)]"
                            : "bg-[#111] border border-amber-500/60 text-amber-500/60 hover:border-amber-500/90 hover:text-amber-500/90"
                        }`}
                >
                    {num}
                </button>
                {idx < total - 1 && (
                    <div className="w-px flex-1 my-1 bg-gradient-to-b from-amber-500/80 to-transparent"
                        style={{ minHeight: 20 }} />
                )}
            </div>

            {/* Card */}
            <div className={`flex-1 min-w-0 mb-3 rounded-2xl border transition-all duration-300
                ${expanded ? "border-[#3a3a3a] bg-[#0d0d0d]" : "border-[#3a3a3a] bg-[#080808]"}`}>

                {/* Collapsed / header row */}
                <div
                    className="flex items-start gap-2 px-4 py-3.5 cursor-pointer select-none"
                    onClick={() => setExpanded(e => !e)}
                >
                    <div className="flex-1 min-w-0">
                        <p className={`text-sm leading-snug transition-colors ${expanded ? "text-white" : "text-white/80"}`}
                            style={{
                                display: "-webkit-box",
                                WebkitLineClamp: expanded ? "unset" : 2,
                                WebkitBoxOrient: "vertical",
                                overflow: expanded ? "visible" : "hidden",
                            }}>
                            {step.instruction}
                        </p>
                    </div>
                    <span className={`text-white text-[20px] flex-shrink-0 ml-2 mt-0.5 transition-transform duration-300 ${expanded ? "rotate-180" : ""}`}>
                        ▾
                    </span>
                </div>

                {/* Expanded metadata */}
                {expanded && (step.technique || step.estimatedMinutes != null || step.imageFile) && (
                    <div className="px-4 pb-4 flex items-center gap-2 flex-wrap border-t border-[#111] pt-3">
                        {step.technique && (
                            <span className="text-[10px] text-amber-500 bg-amber-500/8 border border-amber-500 rounded-full px-2.5 py-1">
                                {step.technique}
                            </span>
                        )}
                        {step.estimatedMinutes != null && (
                            <span className="flex items-center gap-1 text-[10px] text-neutral-200">
                                <Clock size={10} />
                                {step.estimatedMinutes} min
                            </span>
                        )}
                        {step.imageFile?.url && (
                            <div className="ml-auto w-16 h-12 rounded-xl overflow-hidden border border-[#222]">
                                <img src={step.imageFile.url} className="w-full h-full object-cover" alt={`Step ${num}`} />
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// Moderation Banner
// ─────────────────────────────────────────────────────────────────────────────

function ModerationBanner({ moderation }) {
    const isMod = moderation.recentReports !== null;

    return (
        <div
            role="status"
            className={`flex items-start gap-3 px-4 py-3.5 rounded-2xl border text-xs
                ${isMod
                    ? "bg-red-500/5 border-red-500/15 text-red-400/80"
                    : "bg-amber-500/5 border-amber-500/15 text-amber-400/80"
                }`}
        >
            <Flag size={13} className="flex-none mt-0.5 opacity-60" />
            <div className="flex-1 min-w-0">
                {moderation.viewerReported && (
                    <p>
                        You reported this recipe
                        {moderation.viewerReportReason && (
                            <span className="opacity-60 ml-1.5">· {moderation.viewerReportReason}</span>
                        )}
                    </p>
                )}
                {isMod && (
                    <>
                        <p className="font-semibold">
                            {moderation.reportsCount} report{moderation.reportsCount !== 1 ? "s" : ""} filed
                        </p>
                        {moderation.recentReports?.length > 0 && (
                            <ul className="mt-2 space-y-1 opacity-70">
                                {moderation.recentReports.map((r) => (
                                    <li key={r.id} className="flex items-start gap-2">
                                        <span className="opacity-40">#{r.id}</span>
                                        <span className="font-medium capitalize">{r.reason}</span>
                                        {r.details && <span className="opacity-60 truncate">{r.details}</span>}
                                    </li>
                                ))}
                            </ul>
                        )}
                    </>
                )}
            </div>
        </div>
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// Not Found
// ─────────────────────────────────────────────────────────────────────────────

function NotFoundCard({ id, navigate, isAuthorized }) {
    const suggestions = MOCK_RECIPES.filter((r) => r.id !== id).slice(0, 3);

    return (
        <div>
            <div className="flex flex-col md:flex-row gap-6 items-start">
                <div className="flex-none w-20 h-20 rounded-2xl bg-amber-500/5 border border-amber-500/10
                    flex items-center justify-center text-amber-500/30">
                    <HandPlatter size={40} />
                </div>
                <div className="flex-1 min-w-0">
                    <h2 className="text-2xl font-semibold text-white" style={{ fontFamily: "'Georgia', serif" }}>
                        Recipe not found
                    </h2>
                    <p className="text-neutral-500 text-sm mt-1.5 leading-relaxed">
                        We couldn't find that recipe - it may have been removed or the link is incorrect.
                    </p>
                    <div className="mt-5 flex flex-wrap gap-2">
                        <button
                            onClick={() => navigate("/recipes")}
                            className="px-4 py-2.5 rounded-xl bg-amber-500 text-black text-sm font-semibold hover:bg-amber-400 transition-colors"
                        >
                            Browse Recipes
                        </button>
                        <button
                            onClick={() => navigate("/")}
                            className="px-4 py-2.5 rounded-xl border border-[#222] text-neutral-300 text-sm hover:border-[#333] transition-colors"
                        >
                            Home
                        </button>
                        {isAuthorized && (
                            <button
                                onClick={() => navigate("/recipes/create")}
                                className="px-4 py-2.5 rounded-xl border border-amber-500/30 text-amber-400/80 text-sm hover:border-amber-500/50 transition-colors"
                            >
                                Create a Recipe
                            </button>
                        )}
                    </div>
                </div>
            </div>

            {suggestions.length > 0 && (
                <div className="mt-10">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-neutral-500 mb-4">You might like</p>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        {suggestions.map((r) => (
                            <SuggestedCard key={r.id} recipe={r} onOpen={() => navigate(`/recipes/${r.id}`)} />
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

function SuggestedCard({ recipe, onOpen }) {
    return (
        <article
            onClick={onOpen}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === "Enter" && onOpen()}
            aria-label={`Open ${recipe.title}`}
            className="rounded-2xl overflow-hidden border border-[#161616] bg-[#0a0a0a] cursor-pointer
                hover:border-[#252525] transition-all duration-200 group"
        >
            <div className="h-32 overflow-hidden">
                <LazyImage src={recipe.media?.imageUrl} alt={recipe.title}
                    aspectClass="h-32 group-hover:scale-[1.03] transition-transform duration-500" />
            </div>
            <div className="p-3.5">
                <h5 className="text-sm font-medium text-white/85 line-clamp-2 leading-snug"
                    style={{ fontFamily: "'Georgia', serif" }}>
                    {recipe.title}
                </h5>
                <p className="text-[11px] text-neutral-600 mt-1.5">
                    {recipe.author?.username} · {recipe.meta?.timeMinutes ?? "?"} min
                </p>
            </div>
        </article>
    );
}