// Recipes.jsx
// ─────────────────────────────────────────────────────────────────────────────
// Recipe surface - grid + pagination + server-driven filters.
//
// Filter params (sort, q, tag, difficulty) live in the URL and are read here
// to pass to useRecipeFeed().  RecipeFilters writes those same params, so
// changing a filter automatically triggers a fresh fetch with page reset.
// ─────────────────────────────────────────────────────────────────────────────

import React, { useMemo, useRef, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  Clock,
  Flame,
  GitFork,
  PlayCircle,
  BadgeCheck,
  TrendingUp,
  FlaskConical,
  ChevronLeft,
  ChevronRight,
  Eye,
} from "lucide-react";
import { useContextManager } from "../features/ContextProvider";
import {
  useRecipeFeed,
  MOCK_RECIPES,
} from "../components/recipe/recipeData";
import {
  LazyImage,
  RecipeErrorBoundary,
  PageError,
  PageSkeleton,
} from "../components/recipe/recipeUI";
import RecipeFilters from "../components/recipe/RecipeFilters";
import RequireAuthGate from "../components/auth/RequireAuthGate";

export default function Recipes() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const { isAuthorized, user } = useContextManager();
  const { windowWidth, setIsLoading } = useContextManager();

  const sort = params.get("sort") || "recent";
  const q = params.get("q") || undefined;
  const tag = params.get("tag") || undefined;
  const difficulty = params.get("difficulty") || undefined;
  const page = Math.max(1, parseInt(params.get("page") || "1", 10));

  useEffect(() => {
    setIsLoading(false);
  }, []);

  const viewFavorites = params.get("view") === "favorites";

  const feedResult = useRecipeFeed({
    sort, q, tag, difficulty, page, pageSize: 20,
  });

  const favResult = useRecipeFeed({
    page, pageSize: 20,
    favorites: viewFavorites,
  });

  const { data, isLoading, isError, error, reload: refetch } = viewFavorites ? favResult : feedResult;

  const recipes = data?.items ?? (isError ? MOCK_RECIPES : []);
  const pagination = data?.pagination ?? null;

  function goToPage(n) {
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("page", String(n));
      return next;
    });
  }

  if (isLoading) return <PageSkeleton count={8} />;


  if (viewFavorites && !isAuthorized) {
    return <RequireAuthGate message="You need to sign-in to view your favorites" />
  }

  if (error && !data) {
    return (
      <div className="px-6 py-6 max-w-[1500px] mx-auto">
        <SurfaceHeader />
        <PageError error={error} onRetry={refetch} className="min-h-[50vh]" />
      </div>
    );
  }

  return (
    <div className="px-6 py-6 max-w-[1500px] mx-auto">
      <SurfaceHeader pagination={pagination} />

      {error && data && (
        <div
          role="status"
          className="mb-4 flex items-center gap-2 px-4 py-2 rounded-lg bg-amber-900/20 border border-amber-700/30 text-amber-300 text-sm"
        >
          <span>⚠️</span>
          <span>Showing cached results - live feed unavailable.</span>
          <button onClick={refetch} className="ml-auto text-xs underline hover:text-amber-200">
            Refresh
          </button>
        </div>
      )}
      {windowWidth < 1024 &&
        <div className="mb-10">
          <RecipeFilters />
        </div>
      }

      <div>
        {recipes.length === 0 ? (
          <EmptyState q={q} tag={tag} />
        ) : (
          <section
            aria-label="Recipe grid"
            className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6"
          >

            {recipes.map((recipe) => (
              <RecipeErrorBoundary key={recipe.id} recipeId={recipe.id} recipeTitle={recipe.title}>
                <RecipeCard
                  recipe={recipe}
                  isAuthorized={isAuthorized}
                  onOpen={() => navigate(`/recipes/${recipe.id}`)}
                />
              </RecipeErrorBoundary>
            ))}
          </section>
        )}
      </div>

      {pagination && (
        <Pagination pagination={pagination} currentPage={page} onPageChange={goToPage} />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Pagination
// ─────────────────────────────────────────────────────────────────────────────

function Pagination({ pagination, currentPage, onPageChange }) {
  const { total_pages, has_prev, has_next, total, page_size } = pagination;

  function getPages() {
    if (total_pages <= 7) return Array.from({ length: total_pages }, (_, i) => i + 1);
    const pages = new Set([1, total_pages, currentPage]);
    for (let d = 1; d <= 2; d++) {
      if (currentPage - d >= 1) pages.add(currentPage - d);
      if (currentPage + d <= total_pages) pages.add(currentPage + d);
    }
    const sorted = [...pages].sort((a, b) => a - b);
    const result = [];
    for (let i = 0; i < sorted.length; i++) {
      if (i > 0 && sorted[i] - sorted[i - 1] > 1) result.push(null);
      result.push(sorted[i]);
    }
    return result;
  }

  const from = (currentPage - 1) * page_size + 1;
  const to = Math.min(currentPage * page_size, total);

  return (
    <nav aria-label="Pagination" className="mt-10 flex flex-col items-center gap-4">
      <p className="text-xs text-neutral-500 tracking-wide">
        Showing{" "}
        <span className="text-neutral-300 font-medium">{from.toLocaleString()}–{to.toLocaleString()}</span>
        {" "}of{" "}
        <span className="text-neutral-300 font-medium">{total.toLocaleString()}</span>
        {" "}recipes
      </p>

      <div className="flex items-center gap-1">
        <PageButton onClick={() => onPageChange(currentPage - 1)} disabled={!has_prev} aria-label="Previous page">
          <ChevronLeft size={16} />
        </PageButton>

        {getPages().map((p, i) =>
          p === null ? (
            <span key={`ellipsis-${i}`} className="w-9 text-center text-neutral-600 select-none">…</span>
          ) : (
            <PageButton
              key={p}
              onClick={() => onPageChange(p)}
              active={p === currentPage}
              aria-label={`Page ${p}`}
              aria-current={p === currentPage ? "page" : undefined}
            >
              {p}
            </PageButton>
          )
        )}

        <PageButton onClick={() => onPageChange(currentPage + 1)} disabled={!has_next} aria-label="Next page">
          <ChevronRight size={16} />
        </PageButton>
      </div>
    </nav>
  );
}

function PageButton({ children, onClick, disabled, active, ...rest }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={[
        "min-w-[36px] h-9 px-2 rounded-lg text-sm font-medium transition-colors",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400",
        active ? "bg-amber-500 text-black" :
          disabled ? "text-neutral-700 cursor-not-allowed" :
            "text-neutral-400 hover:bg-neutral-800 hover:text-white",
      ].join(" ")}
      {...rest}
    >
      {children}
    </button>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Header / empty state
// ─────────────────────────────────────────────────────────────────────────────

function SurfaceHeader({ pagination }) {
  return (
    <header className="mb-6 flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h1 className="text-3xl font-semibold text-white">Recipes</h1>
        <p className="text-neutral-400 mt-1 max-w-2xl">
          Recipes evolve here. Fork ideas, improve techniques, and discover what the community is cooking next.
        </p>
      </div>
      {pagination?.total != null && (
        <span className="text-sm text-neutral-500 self-end pb-1">
          {pagination.total.toLocaleString()} recipes
        </span>
      )}
    </header>
  );
}

function EmptyState({ q, tag }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-20 text-center text-neutral-500">
      <span className="text-4xl">🍽️</span>
      <p className="text-base">
        {q ? `No recipes match "${q}"` :
          tag ? `No recipes tagged "${tag}"` :
            "No recipes found"}
      </p>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Recipe Card (unchanged)
// ─────────────────────────────────────────────────────────────────────────────

function RecipeCard({ recipe, isAuthorized, onOpen }) {
  return (
    <article
      onClick={onOpen}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onOpen(); }}
      aria-label={`Open ${recipe.title}`}
      className="bg-black/40 rounded-xl overflow-hidden cursor-pointer hover:bg-neutral-700/20 transition group relative focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400"
    >
      <div className="relative aspect-[4/3] overflow-hidden">
        <LazyImage
          src={recipe.media?.imageUrl}
          alt={recipe.title}
          className="group-hover:scale-[1.02] transition-transform duration-300"
          aspectClass="aspect-[4/3]"
        />
        {recipe.media?.hasVideo && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <PlayCircle size={42} className="text-white/80 drop-shadow" />
          </div>
        )}
        <RecipeBadges recipe={recipe} />
      </div>

      <div className="p-4 space-y-3">
        <TitleBlock recipe={recipe} />
        <StatsRow recipe={recipe} />
        <TagRow tags={recipe.tags} />
        {!isAuthorized && (
          <p className="text-xs text-neutral-500">🔒 Fork to customize &amp; evolve</p>
        )}
      </div>
    </article>
  );
}

function RecipeBadges({ recipe }) {
  return (
    <div className="absolute top-2 left-2 flex gap-2">
      {recipe.status?.isTrending && <Badge icon={TrendingUp} label="Trending" />}
      {recipe.status?.isVerified && <Badge icon={BadgeCheck} label="Verified" />}
      {recipe.status?.isExperimental && <Badge icon={FlaskConical} label="Experimental" />}
    </div>
  );
}

function Badge({ icon: Icon, label }) {
  return (
    <span className="flex items-center gap-1 px-2 py-0.5 text-xs rounded bg-black/60 text-white backdrop-blur-sm">
      <Icon size={12} />{label}
    </span>
  );
}

function TitleBlock({ recipe }) {
  return (
    <div>
      <h3 className="text-base font-medium text-white line-clamp-1">{recipe.title}</h3>
      <p className="text-sm text-neutral-400 mt-0.5">
        by {recipe.author?.username ?? "Unknown"}
        {recipe.lineage?.isFork && <span className="ml-2 text-xs text-neutral-500">· Forked</span>}
      </p>
    </div>
  );
}

function StatsRow({ recipe }) {
  const forks = recipe.stats.forks ?? {};
  const { timeMinutes, difficulty } = recipe.meta ?? {};
  const views = recipe.stats.views ?? {};

  return (
    <div className="flex items-center gap-4 text-sm text-neutral-400">
      {forks != null && (
        <span className="flex items-center gap-1" title={`${forks} forks`}>
          <GitFork size={14} />{forks}
        </span>
      )}
      {views != null && (
        <span className="flex items-center gap-1" title={`${views} views`}>
          <Eye size={14} />{views}
        </span>
      )}
      {timeMinutes != null && (
        <span className="flex items-center gap-1" title={`${timeMinutes} minutes`}>
          <Clock size={14} />{timeMinutes} min
        </span>
      )}
      {difficulty != null && (
        <span className="flex items-center gap-1 capitalize" title={`Difficulty: ${difficulty}`}>
          <Flame size={14} />{difficulty}
        </span>
      )}
    </div>
  );
}

function TagRow({ tags }) {
  if (!tags?.length) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {tags.map((tag) => (
        <span key={tag} className="px-2 py-0.5 text-xs rounded bg-neutral-800 text-neutral-300">
          {tag}
        </span>
      ))}
    </div>
  );
}