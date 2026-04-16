/**
 * recipeData.js
 * ─────────────────────────────────────────────────────────────────────────────
 * Single source of truth for recipe data across the app.
 *
 * Exports
 *   normalizeRecipe(raw)          - maps API shape → UI shape (safe defaults)
 *   useRecipeFeed(params)         - hook for /feed/list
 *   useRecipe(id)                 - hook for a single recipe (detail page)
 *   useRecommendations(recipeId)  - hook for /feed/recommendations
 *   useTrendingPreview(limit)     - hook for /feed/trending-preview
 *
 * Every hook returns  { data, loading, error, reload }
 * so every consumer can independently handle its own loading / error state.
 *
 * Data flow
 *   API response  →  normalizeRecipe()  →  hook state  →  component
 *
 * The normalizer is the ONLY place that knows about API shape.
 * Components only ever see the normalized UI shape.
 */

import backendUrlV1 from "../../urls/backendUrl";
import { useMe } from "../../hooks/useMe";
import { useQuery } from "@tanstack/react-query";

// ─────────────────────────────────────────────────────────────────────────────
// Canonical UI shape  (what components consume)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * @typedef {Object} NormalizedIngredient
 * @property {number}  id
 * @property {string}  name
 * @property {boolean} isAnimal    - true if animal-derived
 * @property {boolean} isAllergen  - true if a common allergen
 */

/**
 * @typedef {Object} NormalizedStep
 * @property {number}      stepNumber
 * @property {string}      instruction
 * @property {string|null} technique         - e.g. "sauté", "fold"
 * @property {number|null} estimatedMinutes
 */

/**
 * @typedef {Object} NormalizedModeration   - only present for moderators / reporters
 * @property {number}      reportsCount
 * @property {boolean}     isReported        - any report exists
 * @property {boolean}     viewerReported    - current viewer filed a report
 * @property {string|null} viewerReportReason
 * @property {Array|null}  recentReports     - moderator-only, up to 5
 */

/**
 * @typedef {Object} NormalizedRecipe
 * @property {string|number} id
 * @property {string}        title
 * @property {string|null}   body
 * @property {boolean}       isDraft
 *
 * @property {{ id: string|number|null, username: string|null }} author
 *
 * @property {{
 *   imageUrl: string|null,   - first image URL (or null)
 *   images:   string[],      - all image URLs
 *   videos:   string[],      - all video URLs
 *   hasVideo: boolean
 * }} media
 *
 * @property {{
 *   likes: number, views: number, shares: number,
 *   comments: number, bookmarks: number, forks: number
 * }} stats
 *
 * @property {{
 *   isFork:            boolean,
 *   parentId:          string|number|null,
 *   forksCount:        number,
 *   improvementsCount: number,
 *   rootRecipeId:      string|number|null,  - from lineage snapshot
 *   depth:             number|null           - fork depth from root
 * }} lineage
 *
 * @property {{
 *   isLocked: boolean, isTrending: boolean, isExperimental: boolean,
 *   isVerified: boolean
 * }} status
 *
 * @property {{
 *   createdAt: string|null, updatedAt: string|null, publishedAt: string|null
 * }} timestamps
 *
 * // Detail-only fields (null when coming from list/feed endpoints)
 * @property {NormalizedIngredient[]|null} ingredients
 * @property {NormalizedStep[]|null}       steps
 * @property {Array|null}                  forks
 * @property {{ timeMinutes: number|null, difficulty: string|null }|null} meta
 * @property {Array|null}                  lineageHistory
 * @property {NormalizedModeration|null}   moderation  - null on list, populated on detail
 */

// ─────────────────────────────────────────────────────────────────────────────
// Normalizer
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Maps any API response shape to the canonical UI shape.
 *
 * Three source shapes are handled transparently:
 *
 *   A) /feed/list  (feeds.py)
 *      media:  { image_url, has_video }
 *      stats:  { likes, views, shares, comments, bookmarks, forks }
 *      author: { id, username }
 *      lineage: { is_fork, parent_id, forks_count, improvements_count }
 *
 *   B) GET /{id}  (get.py)
 *      media:        { images: string[], videos: string[] }
 *      flat counts:  likes_count, views_count, forks_count, …
 *      author_name:  string  (no author object, no author_id)
 *      parent_id:    flat
 *      root_recipe_id, depth:  from lineage snapshot (flat)
 *      ingredients:  [{ id, name, is_animal, is_allergen }]
 *      steps:        [{ step_number, instruction, technique, estimated_minutes }]
 *      moderation:   reports_count, is_reported, viewer_reported, viewer_report_reason,
 *                    recent_reports (moderator-only)
 *
 *   C) Mock / normalized already
 *      media: { imageUrl, images, videos, hasVideo }
 *      Everything already camelCase.
 *
 * All fields have safe fallbacks - components never guard individual API fields.
 */
export function normalizeRecipe(raw) {
    if (!raw) return null;

    // ── Detect source shape ──────────────────────────────────────────────────
    const isDetailShape = raw.author_name !== undefined     // get.py sets author_name
        || (raw.media?.images !== undefined);                  // get.py sets media.images[]

    // ── author ───────────────────────────────────────────────────────────────
    // get.py:    raw.author_name (string), no id available in response
    // feeds.py:  raw.author = { id, username }
    // mock:      raw.author = { id, username }
    const author = {
        id: raw.author?.id ?? raw.author_id ?? null,
        username: raw.author?.username ?? raw.author_name ?? null,
        avatar_url: raw.author?.avatar_url ?? raw.avatar_url ?? null,
    };

    // ── media ─────────────────────────────────────────────────────────────────
    // get.py:   raw.media = { images: string[], videos: string[] }
    // feeds.py: raw.media = { image_url: string, has_video: bool }
    // mock:     raw.media = { imageUrl, images, videos, hasVideo } or { hero_image }
    let images = [];
    let videos = [];

    if (Array.isArray(raw.media?.images)) {
        images = raw.media.images;
    }
    if (Array.isArray(raw.media?.videos)) {
        videos = raw.media.videos;
    }

    const imageUrl =
        images[0] ??   // get.py: first of images[]
        raw.media?.image_url ??   // feeds.py
        raw.media?.imageUrl ??   // already normalized
        raw.media?.hero_image ??   // legacy mock
        null;

    const hasVideo =
        videos.length > 0 ||
        raw.media?.has_video ||
        raw.media?.hasVideo ||
        false;

    // ── stats ─────────────────────────────────────────────────────────────────
    // get.py:   flat  raw.likes_count, raw.views_count, …
    // feeds.py: nested raw.stats = { likes, views, … }
    // mock:     nested raw.stats = { likes, views, … }
    const stats = {
        likes: raw.likes_count ?? raw.stats?.likes ?? 0,
        views: raw.views_count ?? raw.stats?.views ?? 0,
        shares: raw.shares_count ?? raw.stats?.shares ?? 0,
        comments: raw.comments_count ?? raw.stats?.comments ?? 0,
        bookmarks: raw.bookmarks_count ?? raw.stats?.bookmarks ?? 0,
        forks: raw.forks_count ?? raw.stats?.forks ?? raw.lineage?.forks_count ?? 0,
    };

    // ── lineage ───────────────────────────────────────────────────────────────
    // get.py:   raw.parent_id (flat), raw.root_recipe_id, raw.depth
    // feeds.py: raw.lineage = { is_fork, parent_id, forks_count, improvements_count }
    // mock:     raw.lineage = { isFork, parentId, forksCount, improvementsCount }
    const parentId =
        raw.parent_id ??
        raw.lineage?.parent_id ??
        raw.lineage?.parentId ??
        null;

    const lineage = {
        isFork: parentId !== null || raw.lineage?.is_fork || raw.lineage?.isFork || false,
        parentId,
        forksCount: stats.forks,
        improvementsCount: raw.lineage?.improvements_count ?? raw.lineage?.improvementsCount ?? 0,
        // Lineage snapshot fields - only present on GET /{id} response
        rootRecipeId: raw.root_recipe_id ?? raw.lineage?.rootRecipeId ?? null,
        depth: raw.depth ?? raw.lineage?.depth ?? null,
    };

    // ── status ────────────────────────────────────────────────────────────────
    const status = {
        isLocked: raw.status?.is_locked ?? raw.status?.isLocked ?? false,
        isTrending: raw.status?.is_trending ?? raw.status?.isTrending ?? false,
        isExperimental: raw.status?.is_experimental ?? raw.status?.isExperimental ?? false,
        isVerified: raw.status?.is_verified ?? raw.status?.isVerified ?? false,
        isFavorited: raw.viewer_favorite ?? raw.status?.viewer_favorite ?? false,
        isDraft: raw.is_draft ?? false,
    };

    // ── timestamps ────────────────────────────────────────────────────────────
    // get.py:   raw.created_at (flat), no updated_at / published_at in response
    // feeds.py: raw.timestamps = { created_at, updated_at, published_at }
    const timestamps = {
        createdAt: raw.created_at ?? raw.timestamps?.created_at ?? null,
        updatedAt: raw.timestamps?.updated_at ?? null,
        publishedAt: raw.timestamps?.published_at ?? null,
    };

    // ── ingredients ───────────────────────────────────────────────────────────
    // get.py:  [{ id, name, is_animal, is_allergen }]  - rich objects
    // mock:    string[]                                 - plain strings
    // feeds:   null (list endpoint doesn't include ingredients)
    let ingredients = null;
    if (Array.isArray(raw.ingredients)) {
        ingredients = raw.ingredients.map((ing) => {
            if (typeof ing === "string") {
                // Legacy mock format - lift to object shape
                return { id: null, name: ing, isAnimal: false, isAllergen: false };
            }
            return {
                id: ing.id ?? null,
                name: ing.name ?? "",
                isAnimal: ing.is_animal ?? false,
                isAllergen: ing.is_allergen ?? false,
            };
        });
    }

    // ── steps ─────────────────────────────────────────────────────────────────
    // get.py:  [{ step_number, instruction, technique, estimated_minutes }]
    // mock:    string[]
    // feeds:   null
    let steps = null;
    if (Array.isArray(raw.steps)) {
        steps = raw.steps.map((s, i) => {
            if (typeof s === "string") {
                return { stepNumber: i + 1, instruction: s, technique: null, estimatedMinutes: null };
            }
            return {
                stepNumber: s.step_number ?? i + 1,
                instruction: s.instruction ?? "",
                technique: s.technique ?? null,
                estimatedMinutes: s.estimated_minutes ?? null,
            };
        });
    }

    // ── moderation ────────────────────────────────────────────────────────────
    // Only present on GET /{id} response; null on all list/feed shapes.
    const hasModeration = raw.reports_count !== undefined || raw.is_reported !== undefined;
    const moderation = hasModeration
        ? {
            reportsCount: raw.reports_count ?? 0,
            isReported: raw.is_reported ?? false,
            viewerReported: raw.viewer_reported ?? false,
            viewerReportReason: raw.viewer_report_reason ?? null,
            recentReports: raw.recent_reports ?? null,  // moderator-only
        }
        : null;

    // ── meta (client-side only, not from API) ─────────────────────────────────
    const meta = raw.meta
        ? {
            timeMinutes: raw.meta.time_minutes ?? raw.meta.timeMinutes ?? null,
            difficulty: raw.meta.difficulty ?? null
        }
        : null;

    return {
        id: raw.id,
        title: raw.title ?? "Untitled",
        body: raw.body ?? null,
        isDraft: raw.is_draft ?? raw.isDraft ?? false,
        author,
        media: { imageUrl, images, videos, hasVideo },
        stats,
        lineage,
        status,
        timestamps,
        // Detail-only (null when coming from list/feed endpoints)
        ingredients,
        steps,
        forks: raw.forks ?? null,
        lineageHistory: raw.lineageHistory ?? null,
        meta,
        moderation,
        tags: raw.tags ?? [],
    };
}

// ─────────────────────────────────────────────────────────────────────────────
// Internal fetch helper
// ─────────────────────────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────────────────────────
// Internal fetch helper
// ─────────────────────────────────────────────────────────────────────────────

async function apiFetch(path, { viewDrafts = false } = {}) {
    const draftsPath = viewDrafts
        ? path.includes("?") ? `${path}&is_draft=true` : `${path}?is_draft=true`
        : path;
    const url = `${backendUrlV1}${draftsPath}`;
    const res = await fetch(url, { credentials: "include" });
    if (!res.ok) {
        const err = new Error(`HTTP ${res.status}`);
        err.status = res.status;
        throw err;
    }
    return res.json();
}

// ─────────────────────────────────────────────────────────────────────────────
// Public hooks
// ─────────────────────────────────────────────────────────────────────────────

export function useRecipeFeed(params = {}) {
    const {
        sort = "recent", page = 1, pageSize = 20,
        q, authorId, isDraft, licenseCode, favorites = false,
    } = params;

    const me = useMe();
    const { id: userId } = me.data ?? {};

    return useQuery({
        queryKey: ["recipeFeed", { favorites, userId, sort, page, pageSize, q, authorId, isDraft, licenseCode }],
        queryFn: async () => {
            const qs = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
            let url;
            if (favorites) {
                url = `/recipes/feed/${userId}/favorites?${qs}`;
            } else {
                qs.set("sort", sort);
                if (q) qs.set("q", q);
                if (authorId) qs.set("author_id", String(authorId));
                if (isDraft != null) qs.set("is_draft", String(isDraft));
                if (licenseCode) qs.set("license_code", licenseCode);
                url = `/recipes/feed/list?${qs}`;
            }
            const json = await apiFetch(url);
            return {
                items: (json.items ?? []).map(normalizeRecipe),
                pagination: json.pagination ?? {},
            };
        },
        enabled: !favorites || !!userId,
    });
}

export function useRecipe(id) {
    return useQuery({
        queryKey: ["recipe", id],
        queryFn: async () => {
            const json = await apiFetch(`/recipes/${id}`);
            const raw = json?.recipe ?? json;
            return normalizeRecipe(raw);
        },
        enabled: !!id,
    });
}

export function useRecommendations(recipeId = null, limit = 8) {
    return useQuery({
        queryKey: ["recommendations", recipeId, limit],
        queryFn: async () => {
            const qs = new URLSearchParams({ limit: String(limit) });
            if (recipeId) qs.set("recipe_id", String(recipeId));
            const json = await apiFetch(`/recipes/feed/recommendations?${qs}`);
            return (json.recommendations ?? []).map(normalizeRecipe);
        },
    });
}

export function useTrendingPreview(limit = 5) {
    return useQuery({
        queryKey: ["trendingPreview", limit],
        queryFn: async () => {
            const json = await apiFetch(`/recipes/feed/trending-preview?limit=${limit}`);
            return json.items ?? [];
        },
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// Mock data  (single source - same shape as normalizeRecipe output)
// Used by all pages during development / when API is unavailable.
// ─────────────────────────────────────────────────────────────────────────────

export const MOCK_RECIPES = [
    {
        id: "r1",
        title: "Juicy Smash Burgers",
        body: null,
        isDraft: false,
        author: { id: "u1", username: "BurgerDude" },
        media: { imageUrl: "https://images.unsplash.com/photo-1550547660-d9450f859349?q=80&w=1200&auto=format&fit=crop", hasVideo: true },
        stats: { likes: 820, views: 4300, shares: 40, comments: 110, bookmarks: 90, forks: 150 },
        lineage: { isFork: false, parentId: null, forksCount: 150, improvementsCount: 12 },
        status: { isLocked: false, isTrending: true, isExperimental: false, isVerified: true },
        timestamps: { createdAt: null, updatedAt: null, publishedAt: null },
        tags: ["quick", "comfort"],
        meta: { timeMinutes: 25, difficulty: "easy" },
        ingredients: ["1 lb ground beef (80/20)", "Salt", "Pepper", "Burger buns", "American cheese"],
        steps: ["Heat skillet until very hot.", "Divide beef into balls.", "Smash beef balls onto pan.", "Season generously.", "Flip and add cheese.", "Toast buns and assemble."],
        lineageHistory: [{ author: "BurgerDude", change: "Original recipe" }, { author: "GrillMaster", change: "Added caramelized onions" }],
        forks: [{ id: "f1", author: "GrillMaster", summary: "Sweeter onions" }, { id: "f2", author: "SpiceLord", summary: "Added chili oil" }],
    },
    {
        id: "r2",
        title: "Creamy Garlic Pasta",
        body: null,
        isDraft: false,
        author: { id: "u2", username: "PastaQueen" },
        media: { imageUrl: "https://images.unsplash.com/photo-1525755662778-989d0524087e?q=80&w=1200&auto=format&fit=crop", hasVideo: false },
        stats: { likes: 560, views: 2800, shares: 20, comments: 60, bookmarks: 70, forks: 90 },
        lineage: { isFork: false, parentId: null, forksCount: 90, improvementsCount: 6 },
        status: { isLocked: false, isTrending: true, isExperimental: false, isVerified: false },
        timestamps: { createdAt: null, updatedAt: null, publishedAt: null },
        tags: ["vegetarian", "comfort", "quick"],
        meta: { timeMinutes: 20, difficulty: "easy" },
        ingredients: ["200g pasta", "4 cloves garlic", "1 cup cream", "Parmesan cheese", "Olive oil", "Salt"],
        steps: ["Boil pasta until al dente.", "Sauté garlic in olive oil.", "Add cream and simmer.", "Toss pasta with sauce.", "Finish with parmesan."],
        lineageHistory: [{ author: "PastaQueen", change: "Original recipe" }, { author: "CheesyLife", change: "Extra parmesan" }],
        forks: [{ id: "f3", author: "HerbAddict", summary: "Added basil and thyme" }],
    },
    {
        id: "r3",
        title: "Crispy Chicken Tacos",
        body: null,
        isDraft: false,
        author: { id: "u3", username: "TacoMaster" },
        media: { imageUrl: "https://images.unsplash.com/photo-1719948515819-71265e1abb0d?q=80&w=1200&auto=format&fit=crop", hasVideo: true },
        stats: { likes: 1100, views: 5200, shares: 80, comments: 200, bookmarks: 150, forks: 200 },
        lineage: { isFork: false, parentId: null, forksCount: 200, improvementsCount: 18 },
        status: { isLocked: false, isTrending: true, isExperimental: false, isVerified: true },
        timestamps: { createdAt: null, updatedAt: null, publishedAt: null },
        tags: ["mexican", "street-food", "non-vegetarian"],
        meta: { timeMinutes: 30, difficulty: "medium" },
        ingredients: ["Chicken thighs", "Taco seasoning", "Corn tortillas", "Oil for frying", "Lettuce", "Sour cream"],
        steps: ["Season chicken generously.", "Fry until crispy.", "Warm tortillas.", "Assemble tacos with toppings."],
        lineageHistory: [{ author: "TacoMaster", change: "Original recipe" }, { author: "CrunchKing", change: "Double-fried chicken" }],
        forks: [{ id: "f4", author: "CrunchKing", summary: "Extra crispy method" }, { id: "f5", author: "HeatSeeker", summary: "Spicy chipotle sauce" }],
    },
    {
        id: "r4",
        title: "Spicy Ramen Hack",
        body: null,
        isDraft: false,
        author: { id: "u6", username: "NoodleNerd" },
        media: { imageUrl: "https://images.unsplash.com/photo-1569718212165-3a8278d5f624?q=80&w=1200&auto=format&fit=crop", hasVideo: true },
        stats: { likes: 390, views: 1600, shares: 15, comments: 45, bookmarks: 30, forks: 45 },
        lineage: { isFork: true, parentId: "r1", forksCount: 45, improvementsCount: 3 },
        status: { isLocked: false, isTrending: false, isExperimental: true, isVerified: false },
        timestamps: { createdAt: null, updatedAt: null, publishedAt: null },
        tags: ["quick", "spicy", "experimental"],
        meta: { timeMinutes: 10, difficulty: "easy" },
        ingredients: ["Instant ramen", "Chili oil", "Soy sauce", "Soft-boiled egg", "Green onions"],
        steps: ["Cook ramen noodles.", "Mix seasoning with chili oil.", "Add noodles and broth.", "Top with egg and onions."],
        lineageHistory: [{ author: "NoodleNerd", change: "Original hack" }, { author: "Eggcellent", change: "Jammy egg technique" }],
        forks: [{ id: "f6", author: "FireTongue", summary: "Extra chili oil" }],
    },
    {
        id: "r5",
        title: "Vegan Buddha Bowl",
        body: null,
        isDraft: false,
        author: { id: "u8", username: "PlantPowered" },
        media: { imageUrl: "https://images.unsplash.com/photo-1540189549336-e6e99c3679fe?q=80&w=1200&auto=format&fit=crop", hasVideo: false },
        stats: { likes: 480, views: 2100, shares: 25, comments: 55, bookmarks: 60, forks: 70 },
        lineage: { isFork: false, parentId: null, forksCount: 70, improvementsCount: 5 },
        status: { isLocked: false, isTrending: false, isExperimental: false, isVerified: true },
        timestamps: { createdAt: null, updatedAt: null, publishedAt: null },
        tags: ["vegan", "healthy"],
        meta: { timeMinutes: 25, difficulty: "easy" },
        ingredients: ["Quinoa", "Roasted chickpeas", "Sweet potato", "Avocado", "Tahini sauce"],
        steps: ["Cook quinoa.", "Roast chickpeas and sweet potatoes.", "Slice avocado.", "Assemble bowl and drizzle sauce."],
        lineageHistory: [{ author: "PlantPowered", change: "Original recipe" }, { author: "GreenChef", change: "Added kale" }],
        forks: [{ id: "f7", author: "SauceBoss", summary: "Spicy tahini sauce" }],
    },
];

export async function favoriteRecipe(recipeId) {
    const url = `${backendUrlV1}/recipes/${recipeId}/favorite`;
    const res = await fetch(url, { method: "POST", credentials: "include" });
    if (!res.ok) console.error(res);
    if (res.status === 200) return true;
    return false;
}