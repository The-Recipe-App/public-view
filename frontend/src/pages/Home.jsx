// Home.jsx
// ─────────────────────────────────────────────────────────────────────────────
// Homepage - hero, live bench strip, principles, CTAs.
//
// Error handling
//   • Live feed fails    → shows MOCK_RECIPES as fallback, no error shown (graceful)
//   • Trending fails     → section simply hidden (non-critical widget)
//   • Per-card render    → RecipeErrorBoundary isolates failures
//   • Images             → LazyImage shows grey fallback slot
//
// Data
//   useTrendingPreview()  - for the live bench section
//   Falls back to MOCK_RECIPES on error.
// ─────────────────────────────────────────────────────────────────────────────

import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  GitFork,
  TrendingUp,
  Search,
  UserPlus,
  Wrench,
  Sparkles,
  Clock,
  Plus,
  Filter,
  RefreshCw,
} from "lucide-react";
import { useContextManager } from "../features/ContextProvider";
import { useTrendingPreview, MOCK_RECIPES } from "../components/recipe/recipeData";
import { LazyImage, RecipeErrorBoundary, LiveStripSkeleton } from "../components/recipe/recipeUI";

// ─────────────────────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────────────────────

export default function Home() {
  const navigate = useNavigate();
  const { isAuthorized, setSearchOpen, setIsLoading } = useContextManager();

  const [query, setQuery] = useState("");
  const [activeTag, setActiveTag] = useState("All");
  const TAGS = ["All", "Quick", "Comfort", "Vegan", "Low salt", "Baking"];

  useEffect(() => {
    setIsLoading(false);
  }, []);

  // Trending preview for the "live on the bench" strip
  const { data: trendingItems, loading: trendingLoading, error: trendingError, reload: reloadTrending } =
    useTrendingPreview(6);

  // Map trending-preview API items → a shape LiveWorkbench understands
  // Falls back to MOCK_RECIPES on error / empty
  const liveItems =
    trendingError || !trendingItems?.length
      ? MOCK_RECIPES.slice(0, 4).map((r) => ({
        id: r.id,
        title: r.title,
        img: r.media.imageUrl,
        tags: r.tags,
      }))
      : trendingItems.map((t) => ({
        id: t.id,
        title: t.title,
        img: t.image_url ?? null,
        tags: [],
      }));

  // Client-side filter on query + tag
  const filteredLive = liveItems.filter((r) => {
    const matchQ = !query || r.title.toLowerCase().includes(query.toLowerCase());
    const matchTag = activeTag === "All" || r.tags.includes(activeTag);
    return matchQ && matchTag;
  });

  return (
    <div className="min-h-screen max-w-[100vw] px-4 md:px-8 lg:px-12 py-8 text-neutral-200 bg-transparent">
      <main className="max-w-[100vw] mx-auto space-y-12">

        {/* ── HERO ── */}
        <section className="max-w-[100vw] grid gap-6 lg:grid-cols-2 items-start">
          <div className="pt-2 max-w-[100vw]">
            <h1 className="text-3xl sm:text-4xl md:text-5xl font-extrabold leading-tight tracking-tight">
              Recipes as craft.
              <br />
              Tweak. Test. Improve.
            </h1>

            <p className="mt-4 text-neutral-400 max-w-xl">
              Forkit is a small workshop for recipes - each fork is a crafted tweak.
              Change one thing, test it, and the kitchen decides what works.
            </p>

            <div className="mt-6 flex flex-wrap gap-3 items-center">
              <PrimaryCTA onClick={() => navigate("/recipes")} label="Explore recipes" icon={<Search size={16} />} />
              <SecondaryCTA onClick={() => navigate("/recipes?sort=trending")} label="Trending forks" icon={<TrendingUp size={16} />} />

              {isAuthorized ? (
                <PrimarySmall onClick={() => navigate("/me/forks")} label="My forks" icon={<GitFork size={14} />} />
              ) : (
                <SecondaryCTA
                  onClick={() => {
                    localStorage.setItem("redirectAfterLogin", "/");
                    navigate("/login");
                  }}
                  label="Sign in to fork"
                  icon={<UserPlus size={16} />}
                />
              )}

              <button
                onClick={() => navigate("/recipes/create")}
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-emerald-500 text-black font-medium hover:brightness-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 ml-2"
                aria-label="Create a new fork"
              >
                <Plus size={14} />
                <span className="text-sm">Create fork</span>
              </button>
            </div>

            <div className="mt-6 grid grid-cols-1 sm:grid-cols-3 gap-3 max-w-md text-xs text-neutral-400">
              <Stat label="Small changes" sub="One tweak at a time" icon={<Wrench size={14} />} />
              <Stat label="Document" sub="Why it changed" icon={<Sparkles size={14} />} />
              <Stat label="Measure" sub="Time, texture, taste" icon={<Clock size={14} />} />
            </div>
          </div>
        </section>

        {/* ── SEARCH + TAGS ── */}
        <section className="space-y-3" aria-label="Search and filter">
          <SearchBar query={query} setQuery={setQuery} setSearchOpen={setSearchOpen} />
          <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by category">
            {TAGS.map((tag) => (
              <button
                key={tag}
                onClick={() => setActiveTag(tag)}
                aria-pressed={activeTag === tag}
                className={`px-3 py-1 rounded-full text-xs font-medium transition focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400 ${activeTag === tag
                  ? "bg-amber-400 text-black"
                  : "bg-neutral-900 border border-neutral-800 text-neutral-400 hover:text-neutral-200"
                  }`}
              >
                {tag}
              </button>
            ))}
          </div>
        </section>

        {/* ── LIVE ON THE BENCH ── */}
        <section aria-label="Live on the bench">
          <div className="flex items-center justify-between mb-4">
            <SectionHeader
              title="Live on the bench"
              subtitle="Recipes being actively tweaked"
            />
            {/* Retry button only shown when the API failed (not on fallback) */}
            {trendingError && (
              <button
                onClick={reloadTrending}
                className="flex items-center gap-1.5 text-xs text-neutral-500 hover:text-neutral-300 transition"
                title="Reload live feed"
              >
                <RefreshCw size={12} />
                Retry
              </button>
            )}
          </div>

          {trendingLoading ? (
            <div className="overflow-x-auto no-scrollbar -mx-4 px-4">
              <LiveStripSkeleton count={4} />
            </div>
          ) : (
            <LiveWorkbench
              live={filteredLive}
              onOpen={(id) => navigate(`/recipes/${id}`)}
            />
          )}
        </section>

        {/* ── HOW IT WORKS ── */}
        <section
          className="max-w-[100vw] grid gap-6 md:grid-cols-3"
          aria-label="How Forkit works"
        >
          <SimpleTile icon={<Wrench size={20} />} title="Fork the recipe" caption="Make a copy, change one thing." />
          <SimpleTile icon={<Sparkles size={20} />} title="Test & record" caption="Note results and metrics." />
          <SimpleTile icon={<TrendingUp size={20} />} title="Share & surface" caption="Good forks get noticed." />
        </section>

        {/* ── PRINCIPLES ── */}
        <section className="max-w-[100vw] bg-[#0b0b0b] border border-white/5 p-6 rounded-xl">
          <h3 className="text-lg font-semibold">Workshop principles</h3>
          <p className="text-neutral-400 mt-2 max-w-3xl">
            Minimal edits. Explain clearly. Keep lineage. Respect other people's work.
          </p>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <Principle title="One change" desc="Avoid big rewrites - small reproducible changes win." />
            <Principle title="Why it matters" desc="Write a short note with the how &amp; why." />
            <Principle title="Respect lineage" desc="Keep attribution and history intact." />
          </div>
        </section>

        {/* ── FINAL CTA ── */}
        <section className="max-w-[100vw] flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold">Ready to experiment?</h2>
            <p className="text-neutral-400 mt-2">Fork one recipe, change one thing, test it - see what works.</p>
          </div>
          <div className="flex gap-3">
            <PrimaryCTA onClick={() => navigate("/recipes")} label="Explore recipes" icon={<Search size={16} />} />
            <SecondaryCTA onClick={() => navigate("/recipes?sort=trending")} label="See trending forks" icon={<TrendingUp size={16} />} />
          </div>
        </section>

      </main>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// LiveWorkbench - horizontal scroll on mobile, grid on md+
// ─────────────────────────────────────────────────────────────────────────────

function LiveWorkbench({ live, onOpen }) {
  if (!live?.length) {
    return (
      <p className="text-sm text-neutral-500 py-6">No active recipes right now.</p>
    );
  }

  return (
    <>
      {/* Mobile: horizontal scroll */}
      <div className="block md:hidden overflow-x-auto no-scrollbar -mx-4 px-4">
        <div className="flex gap-4 py-2">
          {live.map((r) => (
            <RecipeErrorBoundary key={r.id} recipeId={r.id} recipeTitle={r.title}>
              <LiveCard r={r} onOpen={onOpen} mobile />
            </RecipeErrorBoundary>
          ))}
        </div>
      </div>

      {/* Desktop: grid */}
      <div className="hidden md:grid md:grid-cols-3 gap-4">
        {live.map((r) => (
          <RecipeErrorBoundary key={r.id} recipeId={r.id} recipeTitle={r.title}>
            <LiveCard r={r} onOpen={onOpen} />
          </RecipeErrorBoundary>
        ))}
      </div>
    </>
  );
}

function LiveCard({ r, onOpen, mobile = false }) {
  return (
    <motion.article
      whileHover={{ y: -6 }}
      className={`${mobile
        ? "min-w-[72vw] sm:w-[260px] flex-shrink-0"
        : ""
        } bg-[#0b0b0b] border border-white/5 rounded-lg p-3 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400`}
      onClick={() => onOpen(r.id)}
      role="button"
      tabIndex={0}
      aria-label={`Open ${r.title}`}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onOpen(r.id); }}
    >
      <div className={`${mobile ? "h-[36vw] sm:h-40" : "h-48"} overflow-hidden rounded-md`}>
        <LazyImage
          src={r.img}
          alt={r.title}
          aspectClass={mobile ? "h-[36vw] sm:h-40" : "h-48"}
        />
      </div>
      <div className="mt-3">
        <div className="text-sm font-medium text-white line-clamp-1">{r.title}</div>
        <div className="text-xs text-neutral-400 mt-1">• active now</div>
      </div>
    </motion.article>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Small building blocks
// ─────────────────────────────────────────────────────────────────────────────

function PrimaryCTA({ onClick, label, icon }) {
  return (
    <button onClick={onClick} className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-amber-400 text-black font-medium hover:brightness-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400">
      {icon}<span>{label}</span>
    </button>
  );
}

function PrimarySmall({ onClick, label, icon }) {
  return (
    <button onClick={onClick} className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-amber-400 text-black font-medium hover:brightness-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400">
      {icon}<span className="text-sm">{label}</span>
    </button>
  );
}

function SecondaryCTA({ onClick, label, icon }) {
  return (
    <button onClick={onClick} className="inline-flex items-center gap-2 px-4 py-2 rounded-md border border-neutral-700 text-neutral-200 hover:bg-neutral-900/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400">
      {icon}<span>{label}</span>
    </button>
  );
}

function Stat({ label, sub, icon }) {
  return (
    <div className="flex items-start gap-3">
      <div className="bg-neutral-800 rounded-md p-2">{icon}</div>
      <div>
        <div className="text-sm font-medium text-white">{label}</div>
        <div className="text-xs text-neutral-400">{sub}</div>
      </div>
    </div>
  );
}

function SimpleTile({ icon, title, caption }) {
  return (
    <div className="bg-[#0b0b0b] border border-white/5 rounded-xl p-5 flex flex-col items-start gap-3">
      <div className="p-2 rounded-md bg-neutral-900">{icon}</div>
      <h4 className="font-semibold">{title}</h4>
      <p className="text-sm text-neutral-400">{caption}</p>
    </div>
  );
}

function SectionHeader({ title, subtitle }) {
  return (
    <div>
      <h3 className="text-lg font-semibold">{title}</h3>
      {subtitle && <p className="text-sm text-neutral-400">{subtitle}</p>}
    </div>
  );
}

function Principle({ title, desc }) {
  return (
    <div className="bg-neutral-900 border border-white/5 rounded-md p-4">
      <div className="text-sm font-semibold">{title}</div>
      <div className="text-xs text-neutral-400 mt-1" dangerouslySetInnerHTML={{ __html: desc }} />
    </div>
  );
}

function SearchBar({ query, setQuery, setSearchOpen }) {
  return (
    <div className="flex items-center gap-2">
      <div className="relative flex-1 max-w-[400px]">
        <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/65 pointer-events-none" />
        <button
          onClick={() => setSearchOpen(true)}
          placeholder="Search recipes, techniques, cooks…"
          className="w-full h-9 pl-9 pr-12 rounded-xl bg-neutral-600/[0.4]
                                        border border-white/10 text-[13px] text-start text-white
                                        placeholder-white/60 cursor-text outline-none
                                        hover:bg-white/[0.09] hover:border-orange-600 transition"
        >
          Search recipes, techniques, cooks…
          <kbd className="absolute text-center right-3 top-1/2 -translate-y-1/2 text-[10px]
                                        text-white/60 bg-white/[0.2] border border-white/10
                                        rounded px-1.5 py-px pointer-events-none">⌘ K</kbd>
        </button>
      </div>
    </div>
  );
}

/* Inject scrollbar styles once */
if (typeof document !== "undefined" && !document.head.querySelector("[data-forkit-style]")) {
  const s = document.createElement("style");
  s.setAttribute("data-forkit-style", "true");
  s.innerHTML = `
    .no-scrollbar::-webkit-scrollbar { height: 8px; }
    .no-scrollbar::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.04); border-radius: 8px; }
    .no-scrollbar { -ms-overflow-style: none; scrollbar-width: thin; }
    .line-clamp-1 { display:-webkit-box;-webkit-line-clamp:1;-webkit-box-orient:vertical;overflow:hidden; }
    .line-clamp-2 { display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden; }
  `;
  document.head.appendChild(s);
}
