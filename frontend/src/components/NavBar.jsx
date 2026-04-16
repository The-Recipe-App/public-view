// NavBar.jsx — Forkit · Premium Sidebar Redesign
// Dark luxury · Ember accents · Surgical micro-interactions

import React, { useMemo, useState, useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
    Home,
    BookOpen,
    Sparkles,
    ChevronRight,
    ChevronDown,
    Flame,
    Utensils,
    TrendingUp,
    Clock,
    Star,
    LogIn,
    PlusCircle,
    Heart,
    GitFork,
    User,
    Settings,
    Search,
    Compass,
    Award,
    Coffee,
    ShoppingCart,
    Bell,
    HelpCircle,
    FileText,
    Shield,
    Info,
    Scale,
    Cookie,
    NotebookPen,
} from "lucide-react";
import { motion, useReducedMotion, AnimatePresence } from "framer-motion";
import { useContextManager } from "../features/ContextProvider";
import RecipeFilters from "../components/recipe/RecipeFilters";

/* ─── Design tokens ─── */
const TOKEN = {
    sidebar: "w-[240px]",
    accent: "#f97316",    // orange-500
    accentDim: "#7c2d12",    // orange-950
    surface: "rgba(0, 0, 0, 0.85)",
    border: "rgba(255,255,255,0.06)",
};

/* ─── Tiny helpers ─── */
const Divider = () => (
    <div className="mx-3 h-px" style={{ background: TOKEN.border }} />
);

const SectionLabel = ({ children }) => (
    <p className="px-3 pt-1 pb-0.5 text-[10px] font-semibold tracking-[0.15em] uppercase"
        style={{ color: "rgba(255,255,255,0.25)" }}>
        {children}
    </p>
);

/* ─── SubNavItem (nested) ─── */
const SubNavItem = ({ icon: Icon, label, to, onClick, isOpen }) => {
    const location = useLocation();
    const isActive = location.pathname === to;

    return (
        <button
            onClick={onClick}
            tabIndex={isOpen ? 0 : -1}
            aria-current={isActive ? "page" : undefined}
            className="group relative w-full flex items-center gap-2.5 pl-8 pr-3 py-2 rounded-lg text-[12.5px] font-medium transition-all duration-150"
            style={{
                color: isActive ? TOKEN.accent : "rgba(255,255,255,0.4)",
                background: isActive ? "rgba(249,115,22,0.08)" : "transparent",
            }}
            onMouseEnter={e => {
                if (!isActive) e.currentTarget.style.background = "rgba(255,255,255,0.03)";
                e.currentTarget.style.color = isActive ? TOKEN.accent : "rgba(255,255,255,0.75)";
            }}
            onMouseLeave={e => {
                if (!isActive) e.currentTarget.style.background = "transparent";
                e.currentTarget.style.color = isActive ? TOKEN.accent : "rgba(255,255,255,0.4)";
            }}
        >
            {/* Indent guide line */}
            <span
                className="absolute left-[18px] top-0 bottom-0 w-px"
                style={{ background: isActive ? "rgba(249,115,22,0.3)" : "rgba(255,255,255,0.06)" }}
            />
            <Icon
                size={13}
                className="shrink-0"
                style={{ color: isActive ? TOKEN.accent : "inherit", opacity: 0.8 }}
            />
            <span className="flex-1 text-left">{label}</span>
        </button>
    );
};

/* ─── NavItem (with optional submenu) ─── */
const NavItem = ({ icon: Icon, label, to, onClick, badge, isOpen, children }) => {
    const location = useLocation();
    const hasChildren = Boolean(children);

    const isActive = to === "/"
        ? location.pathname === "/"
        : location.pathname.startsWith(to);

    // Auto-expand if a child route is active
    const [expanded, setExpanded] = useState(() => {
        if (!hasChildren || !to) return false;
        return location.pathname.startsWith(to);
    });

    // Keep expanded in sync if location changes externally
    useEffect(() => {
        if (hasChildren && to && location.pathname.startsWith(to)) {
            setExpanded(true);
        }
    }, [location.pathname]);

    const handleClick = () => {
        if (hasChildren) {
            setExpanded(prev => !prev);
        }
        onClick?.();
    };

    return (
        <div>
            <button
                onClick={handleClick}
                tabIndex={isOpen ? 0 : -1}
                aria-current={isActive ? "page" : undefined}
                aria-expanded={hasChildren ? expanded : undefined}
                className="group relative w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13.5px] font-medium transition-all duration-150 overflow-hidden"
                style={{
                    color: isActive ? "#fff" : "rgba(255,255,255,0.55)",
                    background: isActive ? "rgba(249,115,22,0.12)" : "transparent",
                }}
                onMouseEnter={e => {
                    if (!isActive) e.currentTarget.style.background = "rgba(255,255,255,0.04)";
                    e.currentTarget.style.color = "#fff";
                }}
                onMouseLeave={e => {
                    if (!isActive) e.currentTarget.style.background = "transparent";
                    e.currentTarget.style.color = isActive ? "#fff" : "rgba(255,255,255,0.55)";
                }}
            >
                {/* Active bar */}
                {isActive && (
                    <motion.span
                        layoutId="nav-pill"
                        className="absolute inset-y-1 left-0 w-[3px] rounded-full"
                        style={{ background: TOKEN.accent }}
                        transition={{ type: "spring", stiffness: 380, damping: 30 }}
                    />
                )}

                <Icon
                    size={16}
                    className="shrink-0 transition-transform duration-150 group-hover:scale-110"
                    style={{ color: isActive ? TOKEN.accent : "inherit", opacity: isActive ? 1 : 0.7 }}
                />
                <span className="flex-1 text-left">{label}</span>

                {badge != null && (
                    <span
                        className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full"
                        style={{ background: TOKEN.accentDim, color: TOKEN.accent }}
                    >
                        {badge}
                    </span>
                )}

                {hasChildren ? (
                    <motion.span
                        animate={{ rotate: expanded ? 90 : 0 }}
                        transition={{ duration: 0.18, ease: "easeInOut" }}
                    >
                        <ChevronRight size={12} style={{ color: isActive ? TOKEN.accent : "rgba(255,255,255,0.3)", opacity: 0.8 }} />
                    </motion.span>
                ) : isActive ? (
                    <ChevronRight size={12} style={{ color: TOKEN.accent, opacity: 0.6 }} />
                ) : null}
            </button>

            {/* Submenu */}
            {hasChildren && (
                <AnimatePresence initial={false}>
                    {expanded && (
                        <motion.div
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: "auto", opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            transition={{ duration: 0.2, ease: "easeInOut" }}
                            style={{ overflow: "hidden" }}
                        >
                            <div className="mt-0.5 space-y-0.5 pb-1">
                                {children}
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>
            )}
        </div>
    );
};

/* ─── Trending pill ─── */
const TrendChip = ({ label, onClick }) => (
    <button
        onClick={onClick}
        className="group flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium transition-all duration-150"
        style={{
            background: "rgba(249,115,22,0.08)",
            color: "rgba(249,115,22,0.7)",
            border: "1px solid rgba(249,115,22,0.15)",
        }}
        onMouseEnter={e => {
            e.currentTarget.style.background = "rgba(249,115,22,0.16)";
            e.currentTarget.style.color = TOKEN.accent;
            e.currentTarget.style.borderColor = "rgba(249,115,22,0.35)";
        }}
        onMouseLeave={e => {
            e.currentTarget.style.background = "rgba(249,115,22,0.08)";
            e.currentTarget.style.color = "rgba(249,115,22,0.7)";
            e.currentTarget.style.borderColor = "rgba(249,115,22,0.15)";
        }}
    >
        <TrendingUp size={10} />
        {label}
    </button>
);

/* ─── Ambient "spark" widget ─── */
const AmbientWidget = ({ onExplore }) => {
    const [hovered, setHovered] = useState(false);

    return (
        <div
            className="relative rounded-xl p-3.5 min-h-fit overflow-hidden transition-all duration-300 cursor-default"
            style={{
                background: "linear-gradient(135deg, rgba(124,45,18,0.18) 0%, rgba(10,10,10,0) 60%)",
                border: "1px solid rgba(249,115,22,0.12)",
            }}
            onMouseEnter={() => setHovered(true)}
            onMouseLeave={() => setHovered(false)}
        >
            {/* Glow blob */}
            <div
                className="absolute -top-6 -right-6 w-20 h-20 rounded-full blur-2xl transition-opacity duration-500 pointer-events-none"
                style={{
                    background: "radial-gradient(circle, rgba(249,115,22,0.3), transparent 70%)",
                    opacity: hovered ? 1 : 0.4,
                }}
            />

            <div className="relative flex items-center gap-2 mb-2">
                <span
                    className="flex items-center justify-center w-6 h-6 rounded-lg"
                    style={{ background: "rgba(249,115,22,0.15)" }}
                >
                    <Flame size={12} style={{ color: TOKEN.accent }} />
                </span>
                <span className="text-[12px] font-semibold" style={{ color: "rgba(255,255,255,0.85)" }}>
                    Forkit
                </span>
            </div>

            <p className="text-[11px] leading-relaxed mb-3" style={{ color: "rgba(255,255,255,0.4)" }}>
                Recipes evolve here. Fork, tweak, and make them yours.
            </p>

            <div className="flex flex-wrap gap-1.5 mb-3">
                <TrendChip label="Trending" onClick={onExplore} />
                <TrendChip label="New forks" onClick={onExplore} />
            </div>

            <button
                onClick={onExplore}
                className="group flex items-center gap-1 text-[11.5px] font-semibold transition-all duration-150"
                style={{ color: TOKEN.accent }}
                onMouseEnter={e => { e.currentTarget.style.gap = "6px"; }}
                onMouseLeave={e => { e.currentTarget.style.gap = "4px"; }}
            >
                Explore recipes
                <ChevronRight size={12} className="transition-transform duration-150 group-hover:translate-x-0.5" />
            </button>
        </div>
    );
};

/* ─── Login prompt ─── */
const JoinPrompt = ({ nav }) => (
    <div
        className="rounded-xl p-3.5"
        style={{
            background: "rgba(255,255,255,0.02)",
            border: "1px solid rgba(255,255,255,0.06)",
        }}
    >
        <div className="flex items-center gap-2 mb-2">
            <Star size={12} style={{ color: TOKEN.accent }} />
            <span className="text-[11px] font-semibold" style={{ color: "rgba(255,255,255,0.7)" }}>
                Join the community
            </span>
        </div>
        <p className="text-[11px] leading-relaxed mb-3" style={{ color: "rgba(255,255,255,0.35)" }}>
            Fork recipes, save favourites, and build your cookbook.
        </p>
        <div className="space-y-2">
        <button
            onClick={() => nav("/login")}
            className="w-full flex items-center justify-center gap-2 py-2 rounded-lg text-[12px] font-semibold transition-all duration-150"
            style={{
                background: "rgba(249,115,22,0.14)",
                color: TOKEN.accent,
                border: "1px solid rgba(249,115,22,0.25)",
            }}
            onMouseEnter={e => {
                e.currentTarget.style.background = "rgba(249,115,22,0.22)";
                e.currentTarget.style.borderColor = "rgba(249,115,22,0.45)";
            }}
            onMouseLeave={e => {
                e.currentTarget.style.background = "rgba(249,115,22,0.14)";
                e.currentTarget.style.borderColor = "rgba(249,115,22,0.25)";
            }}
        >
            <LogIn size={13} />
            Sign in
        </button>
        <button
            onClick={() => nav("/register")}
            className="w-full flex items-center justify-center gap-2 py-2 rounded-lg text-[12px] font-semibold transition-all duration-150"
            style={{
                background: "rgba(249,115,22,0.14)",
                color: TOKEN.accent,
                border: "1px solid rgba(249,115,22,0.25)",
            }}
            onMouseEnter={e => {
                e.currentTarget.style.background = "rgba(249,115,22,0.22)";
                e.currentTarget.style.borderColor = "rgba(249,115,22,0.45)";
            }}
            onMouseLeave={e => {
                e.currentTarget.style.background = "rgba(249,115,22,0.14)";
                e.currentTarget.style.borderColor = "rgba(249,115,22,0.25)";
            }}
        >
            <NotebookPen size={13} />
            Sign Up for free
        </button>
        </div>
    </div>
);

/* ─── Legal link row ─── */
const LegalLink = ({ icon: Icon, label, to, onClick }) => (
    <button
        onClick={onClick}
        className="group flex items-center gap-1.5 text-[10.5px] transition-colors duration-150"
        style={{ color: "rgba(255,255,255,0.22)" }}
        onMouseEnter={e => e.currentTarget.style.color = "rgba(255,255,255,0.55)"}
        onMouseLeave={e => e.currentTarget.style.color = "rgba(255,255,255,0.22)"}
    >
        {Icon && <Icon size={10} />}
        {label}
    </button>
);

/* ══════════════════════════════════════════════
   MAIN NAVBAR
══════════════════════════════════════════════ */
export default function NavBar({ setNavOpen, isOpen, isOverlay, navRef }) {
    const location = useLocation();
    const navigate = useNavigate();
    const { isAuthorized } = useContextManager();
    const reduce = useReducedMotion();
    const asideRef = useRef(null);

    // Merge refs
    const setRefs = (el) => {
        asideRef.current = el;
        if (typeof navRef === "function") navRef(el);
        else if (navRef) navRef.current = el;
    };

    // Apply inert via DOM directly — React 18 doesn't reliably forward unknown props
    useEffect(() => {
        const el = asideRef.current;
        if (!el) return;
        const shouldInert = isOverlay && !isOpen;
        if (shouldInert) {
            el.setAttribute("inert", "");
            el.setAttribute("aria-hidden", "true");
        } else {
            el.removeAttribute("inert");
            el.removeAttribute("aria-hidden");
        }
    }, [isOpen, isOverlay]);

    const isRecipesPage = location.pathname === "/recipes";
    const showFiltersOnNavbar = useMemo(
        () => isRecipesPage && !isOverlay,
        [isRecipesPage, isOverlay]
    );

    function nav(to) {
        navigate(to);
        if (isOverlay) setNavOpen(false);
    }

    const sidebarVariants = {
        open: { x: 0, transition: { type: "spring", stiffness: 320, damping: 28 } },
        closed: { x: "-100%", transition: { duration: 0.2, ease: "easeInOut" } },
    };

    return (
        <motion.aside
            ref={setRefs}
            role="navigation"
            aria-label="Main sidebar"
            className={`z-[50] ${TOKEN.sidebar} flex flex-col fixed bottom-0 top-[60.39px]`}
            style={{
                background: TOKEN.surface,
                borderRight: `1px solid ${TOKEN.border}`,
                backdropFilter: isOverlay ? "blur(8px) saturate(180%)" : "blur(8px)",
                WebkitBackdropFilter: isOverlay ? "blur(8px) saturate(180%)" : "blur(8px)",
            }}
            initial={false}
            animate={isOpen ? "open" : "closed"}
            variants={reduce ? { open: { x: 0 }, closed: { x: 0 } } : sidebarVariants}
        >
            <nav
                className="flex-1 flex flex-col px-2.5 py-5 gap-4 overflow-y-auto"
                style={{ scrollbarWidth: "none" }}
            >
                {/* ── Discover ── */}
                <div className="space-y-0.5">
                    <SectionLabel>Discover</SectionLabel>
                    <NavItem icon={Home} isOpen={isOpen} label="Home" to="/" onClick={() => nav("/")} />
                    <NavItem icon={TrendingUp} isOpen={isOpen} label="Trending" to="/trending" onClick={() => nav("/recipes?sort=trending")} />
                </div>

                <Divider />

                {/* ── Recipes ── */}
                <div className="space-y-0.5">
                    <SectionLabel>Recipes</SectionLabel>
                    <NavItem icon={BookOpen} isOpen={isOpen} label="All Recipes" to="/recipes" onClick={() => nav("/recipes")}>
                        <SubNavItem icon={PlusCircle} label="Create Recipe" to="/recipes/create" onClick={() => nav("/recipes/create")} isOpen={isOpen} />
                        <SubNavItem icon={Heart} label="Favourites" to="/recipes/favourites" onClick={() => nav("/recipes?view=favorites")} isOpen={isOpen} />
                    </NavItem>
                </div>

                {/* ── Filters (recipes page only, desktop) ── */}
                {showFiltersOnNavbar && window.location.pathname.startsWith("/recipes") && (
                    <div className="space-y-1.5">
                        <SectionLabel>Filter</SectionLabel>
                        <RecipeFilters collapsed={false} />
                    </div>
                )}

                <Divider />

                {/* ── Account (auth-gated) ── */}
                {isAuthorized && (
                    <>
                        <div className="space-y-0.5">
                            <SectionLabel>Account</SectionLabel>
                            <NavItem icon={User} isOpen={isOpen} label="Profile" to="/profile" onClick={() => nav("/profile")} />
                        </div>
                        <Divider />
                    </>
                )}

                <div className="flex-1" />

                {/* ── Login prompt ── */}
                <AnimatePresence>
                    {!isAuthorized && (
                        <motion.div
                            initial={{ opacity: 0, y: 8 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: 8 }}
                            transition={{ duration: 0.2 }}
                        >
                            <JoinPrompt nav={nav} />
                        </motion.div>
                    )}
                </AnimatePresence>

                {/* ── Help & Legal ── */}
                <div className="space-y-2 pt-1">
                    <Divider />
                    <div className="space-y-0.5">
                        <SectionLabel>Help</SectionLabel>
                        <NavItem icon={HelpCircle} isOpen={isOpen} label="Help Center" to="/help" onClick={() => nav("/help")} />
                        <NavItem icon={Info} isOpen={isOpen} label="About Forkit" to="/about" onClick={() => nav("/about")} />
                    </div>
                    <Divider />

                    {/* Inline legal links — ultra-compact */}
                    <div className="px-3 py-2 flex flex-wrap gap-x-3 gap-y-1.5">
                        <LegalLink icon={FileText} label="Terms" onClick={() => nav("/legal/tos")} />
                        <LegalLink icon={Shield} label="Privacy" onClick={() => nav("/legal/privacy")} />
                        <LegalLink icon={Cookie} label="Cookies" onClick={() => nav("/legal/cookie_policy")} />
                        <LegalLink icon={Scale} label="Forkit Open Source Licenses" onClick={() => nav("/legal/license")} />
                    </div>
                    <p className="px-3 pb-1 text-[9.5px]" style={{ color: "rgba(255,255,255,0.15)" }}>
                        © {new Date().getFullYear()} Forkit. All rights reserved.
                    </p>
                </div>
            </nav>
        </motion.aside>
    );
}