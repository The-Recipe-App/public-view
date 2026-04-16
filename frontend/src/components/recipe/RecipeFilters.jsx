// components/recipe/RecipeFilters.jsx

import React, { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Search,
  X,
  SlidersHorizontal,
  TrendingUp,
  Clock,
  Flame,
  Leaf,
  Drumstick,
  Sparkles,
  ChevronDown,
  ChevronUp,
  Heart,
} from "lucide-react";
import { useContextManager } from "../../features/ContextProvider";

const SORT_OPTIONS = [
  { value: "recent", label: "Recent", icon: Clock },
  { value: "trending", label: "Trending", icon: TrendingUp },
  { value: "popular", label: "Popular", icon: Sparkles },
];

const DIFFICULTY_OPTIONS = [
  { value: "easy", label: "Easy" },
  { value: "medium", label: "Medium" },
  { value: "hard", label: "Hard" },
];

const DIET_OPTIONS = [
  { value: "vegetarian", label: "Vegetarian", icon: Leaf },
  { value: "vegan", label: "Vegan", icon: Leaf },
  { value: "non-vegetarian", label: "Non-veg", icon: Drumstick },
];

// ─────────────────────────────────────────────────────────────────────────────
// Hook
// ─────────────────────────────────────────────────────────────────────────────

export function useRecipeFilters() {
  const [searchParams, setSearchParams] = useSearchParams();

  const sort = searchParams.get("sort") || "recent";
  const q = searchParams.get("q") || "";
  const difficulty = searchParams.get("difficulty") || "";
  const viewFavorites = searchParams.get("view") === "favorites";
  const viewDrafts = searchParams.get("view") === "drafts";

  const tags = useMemo(() => {
    const raw = searchParams.get("tag");
    return raw ? raw.split(",").filter(Boolean) : [];
  }, [searchParams]);

  const activeCount = (sort !== "recent" ? 1 : 0)
    + (q ? 1 : 0)
    + (difficulty ? 1 : 0)
    + tags.length;

  function update(changes) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete("page");
      Object.entries(changes).forEach(([key, value]) => {
        if (value === null || value === "" || (Array.isArray(value) && value.length === 0)) {
          next.delete(key);
        } else if (Array.isArray(value)) {
          next.set(key, value.join(","));
        } else {
          next.set(key, String(value));
        }
      });
      return next;
    });
  }

  function toggleFavorites() {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete("page");
      if (next.get("view") === "favorites") {
        next.delete("view");
      } else {
        next.set("view", "favorites");
        // Clear feed-only filters - they don't apply to favorites
        next.delete("sort");
        next.delete("q");
        next.delete("difficulty");
        next.delete("tag");
      }
      return next;
    });
  }

  function toggleDrafts() {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete("page");
      if (next.get("view") === "drafts") {
        next.delete("view");
      } else {
        next.set("view", "drafts");
        // Clear feed-only filters - they don't apply to favorites
        next.delete("sort");
        next.delete("q");
        next.delete("difficulty");
        next.delete("tag");
      }
      return next;
    });
  }

  function toggleTag(tag) {
    const next = tags.includes(tag)
      ? tags.filter((t) => t !== tag)
      : [...tags, tag];
    update({ tag: next });
  }

  function clearAll() {
    setSearchParams({});
  }

  return {
    sort, q, difficulty, tags, activeCount, viewFavorites, viewDrafts,
    setSort: (v) => update({ sort: v }),
    setQ: (v) => update({ q: v }),
    setDifficulty: (v) => update({ difficulty: difficulty === v ? "" : v }),
    toggleTag,
    toggleDrafts,
    toggleFavorites,
    clearAll,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────────

export default function RecipeFilters({ className = "" }) {
  const filters = useRecipeFilters();
  const [open, setOpen] = useState(localStorage.getItem("recipe-filters-open", "false") === "true");
  const [tagSearch, setTagSearch] = useState("");

  const { isOverlay } = useContextManager();

  const { sort, q, difficulty, tags, activeCount, viewFavorites, viewDrafts, clearAll } = filters;

  const COMMON_TAGS = [
    "vegan", "vegetarian", "gluten-free", "quick", "spicy",
    "breakfast", "dessert", "italian", "asian", "low-carb",
  ];

  const visibleTags = tagSearch
    ? COMMON_TAGS.filter((t) => t.includes(tagSearch.toLowerCase()))
    : COMMON_TAGS;

  return (
    <div className={`rounded-xl ${open ? "" : "max-h-fit"} ${isOverlay && "border border-neutral-800 bg-neutral-900/60"} ${className}`}>
      {/* ── Header ── */}
      <button
        onClick={() => {setOpen((v) => !v); localStorage.setItem("recipe-filters-open", open ? "false" : "true");}}
        className={`static w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-neutral-300 hover:text-white transition-colors ${!isOverlay && "hover:bg-neutral-800/80 rounded-lg mb-3"}`}
        aria-expanded={open}
      >
        <span className="flex items-center gap-2">
          <SlidersHorizontal size={15} className="text-neutral-500" />
          Filters
          {(activeCount > 0 || viewFavorites) && (
            <span className="ml-1 px-1.5 py-0.5 text-[10px] font-semibold rounded-full bg-amber-500 text-black leading-none">
              {activeCount + (viewFavorites ? 1 : 0)}
            </span>
          )}
        </span>
        <span className="text-white">
          {open ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
        </span>
      </button>

      {/* ── Body ── */}
      {open && (
        <div className={`${isOverlay && "max-h-[340px]"} overflow-auto px-4 pb-4 space-y-5 border-t border-neutral-800 pt-4 forkit-scroll`}>

          {/* Clear all */}
          {(activeCount > 0 || viewFavorites) && (
            <button
              onClick={clearAll}
              className="flex items-center gap-1.5 text-xs text-neutral-500 hover:text-neutral-300 transition-colors"
            >
              <X size={12} />
              Clear all filters
            </button>
          )}

          {/* ── Favorites toggle - its own section, not inside sort ── */}
          <Section label="View">
            <div className="flex gap-x-2">
              <Chip
                active={viewFavorites}
                onClick={filters.toggleFavorites}
                icon={<Heart size={11} />}
              >
                My Favorites
              </Chip>
              <Chip
                active={viewDrafts}
                onClick={filters.toggleDrafts}
                icon={<Heart size={11} />}
              >
                Drafts
              </Chip>

            </div>
          </Section>

          {/* ── Feed-only filters - hidden when viewing favorites ── */}
          {!viewFavorites && (
            <>
              <Section label="Sort by">
                <div className="flex flex-wrap gap-2">
                  {SORT_OPTIONS.map(({ value, label, icon: Icon }) => (
                    <Chip
                      key={value}
                      active={sort === value}
                      onClick={() => filters.setSort(value)}
                      icon={<Icon size={11} />}
                    >
                      {label}
                    </Chip>
                  ))}
                </div>
              </Section>

              <Section label="Difficulty">
                <div className="flex flex-wrap gap-2">
                  {DIFFICULTY_OPTIONS.map(({ value, label }) => (
                    <Chip
                      key={value}
                      active={difficulty === value}
                      onClick={() => filters.setDifficulty(value)}
                    >
                      {label}
                    </Chip>
                  ))}
                </div>
              </Section>

              <Section label="Diet">
                <div className="flex flex-wrap gap-2">
                  {DIET_OPTIONS.map(({ value, label, icon: Icon }) => (
                    <Chip
                      key={value}
                      active={tags.includes(value)}
                      onClick={() => filters.toggleTag(value)}
                      icon={<Icon size={11} />}
                    >
                      {label}
                    </Chip>
                  ))}
                </div>
              </Section>

              <Section label="Tags">
                <div className="relative mb-2">
                  <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-neutral-500 pointer-events-none" />
                  <input
                    value={tagSearch}
                    onChange={(e) => setTagSearch(e.target.value)}
                    placeholder="Find a tag…"
                    aria-label="Search tags"
                    className={`w-full pl-8 pr-2 py-1.5 text-xs rounded-lg ${isOverlay ? "bg-neutral-800 border border-neutral-700" : "bg-neutral-900 border border-neutral-800"} text-white placeholder-neutral-500 focus:outline-none focus:border-neutral-500 transition-colors`}
                  />
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {visibleTags.map((tag) => (
                    <Chip
                      key={tag}
                      active={tags.includes(tag)}
                      onClick={() => filters.toggleTag(tag)}
                      small
                    >
                      {tag}
                    </Chip>
                  ))}
                  {visibleTags.length === 0 && (
                    <p className="text-xs text-neutral-600">No tags match "{tagSearch}"</p>
                  )}
                </div>
                {tags.filter((t) => !COMMON_TAGS.includes(t)).map((tag) => (
                  <Chip
                    key={tag}
                    active
                    onClick={() => filters.toggleTag(tag)}
                    small
                  >
                    {tag}
                  </Chip>
                ))}
              </Section>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Primitives
// ─────────────────────────────────────────────────────────────────────────────

function Section({ label, children }) {
  return (
    <div className="space-y-2">
      <p className="text-[10px] uppercase tracking-widest text-neutral-600 font-medium">
        {label}
      </p>
      {children}
    </div>
  );
}

function Chip({ active, children, onClick, icon, small = false }) {
  return (
    <button
      onClick={onClick}
      className={[
        "flex items-center gap-1 rounded-full border transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400",
        small ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs",
        active
          ? "bg-amber-500/10 border-amber-500/60 text-amber-400"
          : "border-neutral-700 text-neutral-400 hover:border-neutral-500 hover:text-white",
      ].join(" ")}
    >
      {icon}
      {children}
    </button>
  );
}