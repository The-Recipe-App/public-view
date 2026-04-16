import { useNavigate, useLocation } from "react-router-dom";
import { useEffect, useState, useRef, useCallback } from "react";
import {
    Home, Search, PlusCircle, Heart, Bell,
    User, LogOut, Settings, ChevronDown, X,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import Logo from "../features/Logo";
import { useMe } from "../hooks/useMe";
import { useAuthApi } from "../features/auth/authApi";
import Modal from "./popUpModal";
import { Tooltip } from "react-tooltip";
import { createPortal } from "react-dom";
import SearchOverlay from "./SearchOverlay";
import { useContextManager } from "../features/ContextProvider";
import { useQuery } from "@tanstack/react-query";
import backendUrlV1 from "../urls/backendUrl";

/* ── Profile dropdown ────────────────────────────────────────────────────── */

function ProfileDropdown({ me, isAuthorized, windowWidth, setShowLogout, onClose, anchorRef, goTo }) {
    const avatarSrc = me?.avatar_url
        ? `${me.avatar_url}?v=${me.avatar_changed_at ?? ""}`
        : me?.username
            ? `https://ui-avatars.com/api/?name=${encodeURIComponent(me.username)}&background=ea580c&color=fff`
            : null;

    const initials = me?.username?.slice(0, 2).toUpperCase() ?? "?";

    const go = (path) => { onClose(); goTo(path); };

    const [pos, setPos] = useState({ top: 0, right: 0 });

    useEffect(() => {
        if (anchorRef?.current) {
            const rect = anchorRef.current.getBoundingClientRect();
            setPos({
                top: rect.bottom + 8,
                right: window.innerWidth - rect.right + 8,
            });
        }
    }, [anchorRef]);

    return createPortal(
        <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.97 }}
            transition={{ duration: 0.15 }}
            style={{ top: pos.top, right: pos.right }}
            className="fixed w-56 rounded-2xl z-[200]"
        >
            <div className="absolute inset-0 rounded-2xl border border-white/[0.3] bg-black/80 backdrop-blur-sm" />
            <div className="relative rounded-2xl overflow-hidden">
                <div className="flex items-center gap-3 px-4 py-3 border-b border-white/[0.3]">
                    <div className="w-9 h-9 rounded-[9px] overflow-hidden flex-shrink-0
                                ring-2 ring-orange-500/70">
                        {avatarSrc
                            ? <img src={avatarSrc} className="w-full h-full object-cover" alt="" />
                            : <div className="w-full h-full bg-gradient-to-br from-orange-600 to-purple-600
                                            flex items-center justify-center text-[13px] font-medium text-white">
                                {initials}
                            </div>
                        }
                    </div>
                    <div className="min-w-0">
                        <div className="text-[13px] font-medium text-white truncate">{me?.username}</div>
                    </div>
                </div>

                {/* Nav items */}
                {[
                    { icon: User, label: "Profile", path: "/profile" },
                    { icon: Heart, label: "Favorites", path: "/recipes?view=favorites" },
                ].map(({ icon: Icon, label, path }) => (
                    <button key={label}
                        onClick={() => go(path)}
                        className="w-full flex items-center gap-3 px-4 py-2.5 text-[13px]
                                text-white hover:text-orange-300 hover:bg-white/[0.05]
                                transition-colors duration-100 text-left">
                        <Icon size={15} className="opacity-60" />
                        {label}
                    </button>
                ))}

                {/* Mobile-only nav items */}
                {windowWidth < 1024 && (
                    <>
                        <div className="h-px bg-white/[0.3]" />
                        {[
                            { icon: Home, label: "Home", path: "/" },
                            { icon: PlusCircle, label: "Create recipe", path: "/recipes/create" },
                        ].map(({ icon: Icon, label, path }) => (
                            <button key={label}
                                onClick={() => go(path)}
                                className="w-full flex items-center gap-3 px-4 py-2.5 text-[13px]
                                text-white hover:text-orange-300 hover:bg-white/[0.05]
                                transition-colors duration-100 text-left">
                                <Icon size={15} className="opacity-60" />
                                {label}
                            </button>
                        ))}
                    </>
                )}

                <div className="h-px bg-white/[0.3]" />
                <button
                    onClick={() => { onClose(); setShowLogout(true); }}
                    className="w-full flex items-center gap-3 px-4 py-2.5 text-[13px]
                            text-red-400/80 hover:text-red-400 hover:bg-red-500/[0.07]
                            transition-colors duration-100 text-left">
                    <LogOut size={15} className="opacity-70" />
                    Log out
                </button>
            </div>

        </motion.div>,
        document.body
    );
}

function NotificationBell({ data, notifRef }) {
    const navigate = useNavigate();

    const notifications = data?.notifications ?? [];
    const unread = data?.unread_count ?? 0;

    const [pos, setPos] = useState({ top: 0, right: 0 });

    useEffect(() => {
        if (notifRef?.current) {
            const rect = notifRef.current.getBoundingClientRect();
            setPos({
                top: rect.bottom + 8,
                right: window.innerWidth - rect.right - 100,
            });
        }
    }, [notifRef]);

    return createPortal(
        <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.97 }}
            transition={{ duration: 0.15 }}
            style={{ top: pos.top, right: pos.right }}
            className="fixed max-w-[300px] w-[80%] rounded-2xl z-[200]"
        >
            <div className="absolute inset-0 rounded-2xl border border-white/[0.3] bg-black/80 backdrop-blur-sm" />
            <div className="relative rounded-2xl overflow-hidden">
                <div className="px-4 py-3 border-b border-white/[0.3] flex items-center justify-between">
                    <span className="text-xs font-semibold text-white uppercase tracking-widest">
                        Notifications
                    </span>
                    {unread > 0 && (
                        <span className="text-[10px] bg-amber-500/20 text-amber-400 px-2 py-0.5 rounded-full">
                            {unread} new
                        </span>
                    )}
                </div>

                <div className="max-h-80 overflow-y-auto">
                    {notifications.length === 0 ? (
                        <div className="px-4 py-8 text-center text-neutral-600 text-sm">
                            No notifications yet
                        </div>
                    ) : (
                        notifications.map((n, i) => (
                            <button
                                key={n.id}
                                onClick={() => {
                                    navigate(`/recipes/${n.recipe_id}`);
                                    setOpen(false);
                                }}
                                className={`w-full text-left px-4 py-3 hover:bg-white/3 ${i !== notifications.length - 1 && "border-b border-white/4"} transition-colors`}
                            >
                                <p className="text-sm text-white">
                                    <span className="text-amber-400 font-medium">{n.actor}</span>
                                    {" "}{n.label}
                                </p>
                                <p className="text-[11px] text-end text-neutral-400 mt-0.5">
                                    {formatDistanceToNow(new Date(n.created_at), { addSuffix: true }).charAt(0).toUpperCase() + formatDistanceToNow(new Date(n.created_at), { addSuffix: true }).slice(1)}
                                </p>
                            </button>
                        ))
                    )}
                </div>
            </div>
        </motion.div>,
        document.body
    );
}

/* ── Hamburger icon ─────────────────────────────────────────────────────── */

function HamburgerBtn({ open, onClick, ...props }) {
    return (
        <button onClick={onClick} {...props}
            className="w-9 h-9 rounded-[9px] border border-white/10 hover:bg-white/[0.07]
                        flex flex-col items-center justify-center gap-[5px] transition flex-shrink-0">
            <motion.span animate={{ rotate: open ? 45 : 0, y: open ? 6.5 : 0 }}
                className="block w-4 h-[1.5px] bg-white/70 rounded-full origin-center" />
            <motion.span animate={{ opacity: open ? 0 : 1 }}
                className="block w-4 h-[1.5px] bg-white/70 rounded-full" />
            <motion.span animate={{ rotate: open ? -45 : 0, y: open ? -6.5 : 0 }}
                className="block w-4 h-[1.5px] bg-white/70 rounded-full origin-center" />
        </button>
    );
}

/* ── NavButton (desktop) ─────────────────────────────────────────────────── */

function NavBtn({ icon: Icon, label, active, onClick, disabled, className=null }) {
    return (
        <button onClick={onClick} disabled={disabled || active}
            className={className ?? `relative flex flex-col items-center gap-0.5 px-3 py-1.5 rounded-[9px]
                        text-[10px] transition-colors duration-100
                        ${active
                    ? "text-white cursor-default"
                    : "text-white/80 hover:text-orange-300 hover:bg-white/[0.06]"
                }`}>
            <Icon size={18} />
            {label}
            {active && (
                <motion.span layoutId="nav-indicator"
                    className="absolute -bottom-px left-1/2 -translate-x-1/2
                                w-4 h-0.5 bg-orange-500 rounded-t-full" />
            )}
        </button>
    );
}

async function fetchNotifications() {
    const res = await fetch(`${backendUrlV1}/notifications`, {
        credentials: "include",
    });
    if (!res.ok) throw new Error("Failed");
    return res.json();
}

/* ── TopBar ──────────────────────────────────────────────────────────────── */

const TopBar = ({ isAuthorized, windowWidth, setNavOpen, navOpen, searchOpen, setSearchOpen }) => {
    const { data: me, isLoading } = useMe(isAuthorized);
    const navigate = useNavigate();
    const location = useLocation();
    const reduce = useReducedMotion();
    const profileRef = useRef(null);
    const notifRef = useRef(null);
    const { logout } = useAuthApi();

    const { setIsLoading } = useContextManager();

    const [profileOpen, setProfileOpen] = useState(false);
    const [showLogout, setShowLogout] = useState(false);
    const [showAuthGate, setShowAuthGate] = useState(false);
    const [showNotifications, setShowNotifications] = useState(false);
    const [showCreateHint, setShowCreateHint] = useState(false);
    const [notifOpen, setNotifOpen] = useState(false);

    const IS_XS = windowWidth < 470;
    const IS_SM = windowWidth < 600;
    const IS_MD = windowWidth < 1024;

    const { data } = useQuery({
        queryKey: ["notifications"],
        queryFn: fetchNotifications,
        enabled: isAuthorized,
        refetchInterval: 30000, // poll every 30s
        refetchIntervalInBackground: false,
    });

    useEffect(() => {
        setIsLoading(isLoading);
    })

    useEffect(() => {
        const fn = (e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "k") {
                e.preventDefault();
                setSearchOpen(true);
            }
        };
        document.addEventListener("keydown", fn);
        return () => document.removeEventListener("keydown", fn);
    }, []);

    useEffect(() => {
        const fn = (e) => {
            if (profileRef.current && !profileRef.current.contains(e.target))
                setProfileOpen(false);
        };
        document.addEventListener("mousedown", fn);
        return () => document.removeEventListener("mousedown", fn);
    }, []);

    useEffect(() => {
        const fn = (e) => {
            if (notifRef.current && !notifRef.current.contains(e.target))
                setNotifOpen(false);
        };
        document.addEventListener("mousedown", fn);
        return () => document.removeEventListener("mousedown", fn);
    }, []);

    const requireAuth = useCallback((action) => {
        if (!isAuthorized) { setShowAuthGate(true); return; }
        action();
    }, [isAuthorized]);

    const activeNav = location.pathname === "/" ? "home"
        : new URLSearchParams(location.search).get("view") === "favorites" ? "favorites"
            : "";

    const avatarSrc = me?.avatar_url
        ? `${me.avatar_url}?v=${me.avatar_changed_at ?? ""}`
        : me?.username
            ? `https://ui-avatars.com/api/?name=${encodeURIComponent(me.username)}&background=ea580c&color=fff`
            : null;

    const initials = me?.username?.slice(0, 2).toUpperCase() ?? "?";

    const navigatingRef = useRef(false);

    const goTo = useCallback((path) => {
        const targetBase = path.split("?")[0];
        const targetSearch = path.includes("?") ? "?" + path.split("?")[1] : "";

        const samePage =
            (location.pathname === targetBase && location.search === targetSearch) ||
            (targetBase === "/profile" && location.pathname.startsWith("/profile")) ||
            (targetBase === "/recipe" && location.pathname === "/recipe") ||
            (targetBase === "/recipe/create" && location.pathname === "/recipe/create");

        if (samePage) return;
        if (navigatingRef.current) return;
        navigatingRef.current = true;
        setIsLoading(true);
        navigate(path);
        setTimeout(() => { navigatingRef.current = false; }, 800);
    }, [location.pathname, location.search, navigate, setIsLoading]);

    return (
        <>
            {/* ── Modals ─────────────────────────────────────────────── */}
            <Modal isOpen={showLogout} lock type="warning"
                title="Log out?" description="You'll need to sign in again to access your account."
                primaryAction={{
                    label: "Log out", onClick: async () => {
                        setIsLoading(true);
                        localStorage.setItem("redirectAfterLogin", window.location.pathname);
                        await logout(); setShowLogout(false);
                    }
                }}
                secondaryAction={{ label: "Cancel", onClick: () => setShowLogout(false) }}
            />
            <Modal isOpen={showAuthGate} onClose={() => setShowAuthGate(false)}
                enableClose lock={false} type="info"
                title="Sign in required" description="You need an account to use this feature."
                primaryAction={{ label: "Sign in", onClick: () => { setIsLoading(true); navigate("/login") } }}
                secondaryAction={{ label: "Create account", onClick: () => { setIsLoading(true); navigate("/register") } }}
            />
            <Modal isOpen={showNotifications} type="info"
                title="Notifications" description="You're all caught up 🎉"
                primaryAction={{ label: "Close", onClick: () => setShowNotifications(false) }}
            />
            <Modal isOpen={showCreateHint} type="success"
                title="Create a recipe" description="Start from scratch or build on someone else's idea."
                primaryAction={{ label: "Start cooking", onClick: () => { setIsLoading(true); navigate("/recipes/create") } }}
                secondaryAction={{ label: "Cancel", onClick: () => setShowCreateHint(false) }}
            />

            {/* ── Search overlay ──────────────────────────────────────── */}
            <SearchOverlay open={searchOpen} onClose={() => setSearchOpen(false)} />

            {/* ── Bar ────────────────────────────────────────────────── */}
            <header className="fixed z-[60] w-full h-[60px] border-b border-gray-700
                                bg-black/85 backdrop-blur-md px-3 text-white shadow-lg
                                flex items-center gap-2">

                {/* Hamburger */}
                <div className="flex items-center gap-2 justify-start">
                    <HamburgerBtn
                        open={navOpen}
                        onClick={() => {
                            setNavOpen(o => !o);
                        }}
                        className="user-select-none flex-shrink-0"
                        data-tooltip-id="hamburger-tooltip"
                    />
                    <Tooltip id="hamburger-tooltip" content={navOpen ? "Close navigation" : "Open navigation"} style={{ backgroundColor: "rgba(40, 40, 40, 1)" }} />

                    {/* Logo */}
                    <button onClick={() => goTo("/")}
                        className="flex items-center gap-2 flex-shrink-0 group">
                        <Logo width={120} />
                    </button>

                </div>
                <div className="flex items-center flex-1 justify-end gap-2">
                    {/* Search - full input on MD+, pill on SM, icon-only on XS */}
                    {!IS_SM ? (
                        <div className="relative flex-1 max-w-[420px] mx-2">
                            <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/65 pointer-events-none" />
                            <input
                                type="search" readOnly
                                onClick={() => setSearchOpen(true)}
                                placeholder="Search recipes, techniques, cooks…"
                                className="w-full h-9 pl-9 pr-12 rounded-xl bg-neutral-600/[0.4]
                                        border border-white/10 text-[13px] text-white
                                        placeholder-white/60 cursor-text outline-none
                                        hover:bg-white/[0.09] hover:border-orange-600 transition"
                            />
                            <kbd className="absolute text-center right-3 top-1/2 -translate-y-1/2 text-[10px]
                                        text-white/60 bg-white/[0.2] border border-white/10
                                        rounded px-1.5 py-px pointer-events-none">⌘ K</kbd>
                        </div>
                    ) : IS_SM && !IS_XS ? (
                        <button onClick={() => setSearchOpen(true)}
                            className="flex-1 h-9 flex items-center gap-2 px-3 rounded-xl
                                    bg-neutral-600/[0.4] border border-white/10 text-[13px]
                                    text-white/60 hover:bg-white/[0.09] transition cursor-text">
                            <Search size={14} />
                            Search…
                        </button>
                    ) : (
                        <button onClick={() => setSearchOpen(true)}
                            className="w-9 h-9 rounded-[9px] border border-white/10
                                    flex items-center justify-center text-white/50
                                    hover:bg-white/[0.07] hover:text-white transition flex-shrink-0">
                            <Search size={16} />
                        </button>
                    )}


                    {/* Desktop nav */}
                    {/* Desktop nav */}
                    {!IS_MD && (
                        <nav className="flex items-center gap-1 mr-1">
                            <NavBtn icon={Home} label="Home" active={activeNav === "home"}
                                onClick={() => goTo("/")} />
                            <NavBtn icon={Heart} label="Favorites" active={activeNav === "favorites"}
                                onClick={() => requireAuth(() => goTo("/recipes?view=favorites"))} />
                        </nav>
                    )}

                    {/* Create CTA - text on MD+ */}
                    {!IS_MD ? (
                        <button
                            onClick={() => requireAuth(() => goTo("/recipes/create"))}
                            className="flex items-center gap-1.5 h-9 px-4 rounded-xl
                            bg-white/20 hover:bg-white/30 text-[13px] font-medium
                            text-white transition flex-shrink-0">
                            <PlusCircle size={15} />
                            Create recipe
                        </button>
                    ) : !IS_XS && (
                        <button
                            onClick={() => requireAuth(() => goTo("/recipes/create"))}
                            className="w-9 h-9 rounded-[9px] bg-white/20 hover:bg-white/30
                flex items-center justify-center transition flex-shrink-0">
                            <PlusCircle size={17} />
                        </button>
                    )}

                    {/* Notifications */}
                    {isAuthorized && (
                        <div ref={notifRef} className="relative flex-shrink-0">
                            <button
                                onClick={() => setNotifOpen(o => !o)}
                                className="relative px-4 py-3 rounded-xl text-white hover:text-orange-300 hover:bg-white/[0.06] transition-all"
                                aria-label="Notifications"
                                data-tooltip-id="notif-tooltip"
                            >
                                <NavBtn icon={Bell} className={"flex align-middle"}/>
                                {data?.unread_count > 0 && (
                                    <span className="absolute top-2 right-2 w-2 h-2 rounded-full bg-amber-500" />
                                )}
                            </button>
                            <Tooltip id="notif-tooltip" content={notifOpen ? "Close notifications" : "Open notifications"} style={{ backgroundColor: "rgba(40, 40, 40, 1)" }} />

                            <AnimatePresence>
                                {notifOpen && (
                                    <NotificationBell data={data} notifOpen={notifOpen} setNotifOpen={setNotifOpen} notifRef={notifRef} />
                                )}
                            </AnimatePresence>
                        </div>
                    )}

                    {/* Profile */}
                    {isAuthorized ? (
                        <div ref={profileRef} className="relative flex-shrink-0">
                            <button onClick={() => setProfileOpen(o => !o)}
                                className="flex items-center gap-2 rounded-[9px] px-3 py-2
                                        hover:bg-white/[0.2] transition group">
                                <div className="w-7 h-7 rounded-[7px] overflow-hidden flex-shrink-0
                                            ring-2 ring-orange-500/0 group-hover:ring-orange-500/70
                                            transition-all">
                                    {avatarSrc
                                        ? <img src={avatarSrc} className="w-full h-full object-cover" alt="" />
                                        : <div className="w-full h-full bg-gradient-to-br from-orange-600
                                                        to-purple-600 flex items-center justify-center
                                                        text-[11px] font-medium text-white">
                                            {initials}
                                        </div>
                                    }
                                </div>
                                {!IS_MD && (
                                    <div className="text-left">
                                        <div className="text-[11px] text-white/60 leading-none">Signed in as</div>
                                        <div className="text-[13px] font-medium leading-tight truncate max-w-[90px]">
                                            {me?.username}
                                        </div>
                                    </div>
                                )}
                                <motion.div animate={{ rotate: profileOpen ? 180 : 0 }} transition={{ duration: 0.15 }}>
                                    <ChevronDown size={14} className="text-white/60" />
                                </motion.div>
                            </button>

                            <AnimatePresence>
                                {profileOpen && (
                                    // In TopBar's JSX where ProfileDropdown is rendered:
                                    <ProfileDropdown
                                        me={me}
                                        isAuthorized={isAuthorized}
                                        windowWidth={windowWidth}
                                        setShowLogout={setShowLogout}
                                        onClose={() => setProfileOpen(false)}
                                        anchorRef={profileRef}
                                        goTo={goTo}                   // ← pass down
                                    />
                                )}
                            </AnimatePresence>
                        </div>
                    ) : (
                        <button
                            onClick={() => {
                                localStorage.setItem("redirectAfterLogin", window.location.pathname);
                                goTo("/login");
                            }}
                            className="flex items-center gap-1.5 h-9 px-3.5 rounded-xl
                                border border-white/15 text-[13px] text-white
                                hover:text-white hover:border-white/25 transition flex-shrink-0">
                            <User size={15} />
                            Sign in
                        </button>
                    )}
                </div>
            </header>
        </>
    );
};

export default TopBar;