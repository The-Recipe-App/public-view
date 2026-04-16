import { useState, useEffect, useRef } from "react";
import Logo from "../features/Logo";
import { useContextManager } from "../features/ContextProvider";

// ─── Intersection Observer Hook ──────────────────────────────────────────────
function useInView(threshold = 0.15) {
    const ref = useRef(null);
    const [inView, setInView] = useState(false);
    useEffect(() => {
        const el = ref.current;
        if (!el) return;
        const obs = new IntersectionObserver(
            ([entry]) => { if (entry.isIntersecting) { setInView(true); obs.disconnect(); } },
            { threshold }
        );
        obs.observe(el);
        return () => obs.disconnect();
    }, []);
    return [ref, inView];
}

// ─── Animated Counter ─────────────────────────────────────────────────────────
function Counter({ to, suffix = "", duration = 1800 }) {
    const [val, setVal] = useState(0);
    const [ref, inView] = useInView(0.5);
    useEffect(() => {
        if (!inView) return;
        let start = null;
        const step = (ts) => {
            if (!start) start = ts;
            const progress = Math.min((ts - start) / duration, 1);
            const ease = 1 - Math.pow(1 - progress, 3);
            setVal(Math.round(ease * to));
            if (progress < 1) requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
    }, [inView, to, duration]);
    return (
        <span ref={ref} className="tabular-nums">
            {val.toLocaleString()}{suffix}
        </span>
    );
}

// ─── Fade-in wrapper ──────────────────────────────────────────────────────────
function Reveal({ children, delay = 0, className = "" }) {
    const [ref, inView] = useInView();
    return (
        <div
            ref={ref}
            className={`transition-all duration-700 ${inView ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"} ${className}`}
            style={{ transitionDelay: `${delay}ms` }}
        >
            {children}
        </div>
    );
}

// ─── Timeline node ────────────────────────────────────────────────────────────
function Chapter({ index, label, icon, title, body, isLast }) {
    const [ref, inView] = useInView(0.1);
    return (
        <div ref={ref} className="flex gap-6 md:gap-10">
            {/* spine */}
            <div className="flex flex-col items-center flex-shrink-0">
                <div
                    className={`w-12 h-12 rounded-full flex items-center justify-center text-xl font-black border-2 transition-all duration-700 ${inView
                        ? "bg-amber-400 border-amber-400 text-stone-950 scale-100 shadow-lg shadow-amber-400/30"
                        : "bg-transparent border-amber-400/30 text-amber-400/30 scale-75"
                        }`}
                    style={{ transitionDelay: "100ms" }}
                >
                    {icon}
                </div>
                {!isLast && (
                    <div
                        className={`w-px flex-1 mt-2 transition-all duration-1000 ${inView ? "bg-amber-400/30" : "bg-transparent"}`}
                        style={{ minHeight: "3rem", transitionDelay: "400ms" }}
                    />
                )}
            </div>

            {/* card */}
            <div
                className={`pb-16 flex-1 transition-all duration-700 ${inView ? "opacity-100 translate-x-0" : "opacity-0 translate-x-6"}`}
                style={{ transitionDelay: "200ms" }}
            >
                <p className="text-amber-400/60 text-xs tracking-[0.2em] uppercase font-semibold mb-1">{label}</p>
                <h3 className="text-white font-bold text-xl md:text-2xl mb-3 leading-snug">{title}</h3>
                <p className="text-stone-400 leading-relaxed text-base md:text-lg">{body}</p>
            </div>
        </div>
    );
}

// ─── Stat pill ────────────────────────────────────────────────────────────────
function Stat({ value, to, suffix, label }) {
    return (
        <div className="flex flex-col items-center gap-1">
            <span className="text-3xl md:text-4xl font-black text-amber-400 tracking-tight">
                {to != null ? <Counter to={to} suffix={suffix} /> : value}
            </span>
            <span className="text-stone-500 text-xs tracking-widest uppercase">{label}</span>
        </div>
    );
}

// ─── Main ─────────────────────────────────────────────────────────────────────
export default function AboutPage() {
    const { setIsLoading } = useContextManager();
    const [scrollY, setScrollY] = useState(0);
    useEffect(() => {
        const fn = () => setScrollY(window.scrollY);
        window.addEventListener("scroll", fn, { passive: true });
        return () => window.removeEventListener("scroll", fn);
    }, []);

    const chapters = [
        {
            label: "The Problem",
            icon: "🌐",
            title: "Recipes online were broken.",
            body: "The internet is full of recipes - buried under ads, scattered across blogs, locked behind paywalls, and impossible to improve. You'd find a great dish, tweak it over months, and have nowhere to share that evolution. The knowledge just... disappeared."
        },
        {
            label: "The Gap",
            icon: "🔍",
            title: "Communities existed. Collaboration didn't.",
            body: "Reddit could spark a conversation. GitHub could version-control anything. But nothing in between existed for food. No way to fork a recipe, build on someone else's work, or watch a dish evolve through a community's hands."
        },
        {
            label: "The Insight",
            icon: "🍴",
            title: "Food knowledge should be open source.",
            body: "The best recipes aren't invented - they're iterated. Every grandmother's secret dish was once someone else's starting point. Forkit was built on that idea: treat recipes the way great software treats code. Share it, improve it, attribute it."
        },
        {
            label: "The Platform",
            icon: "🔨",
            title: "Built for the way people actually cook.",
            body: "Semantic search so you can describe a craving, not keyword-match it. A feed that surfaces quality, not recency. Passkey authentication so getting in never gets in the way. Every decision was made around one question: does this make sharing easier?"
        },
        {
            label: "Where It Goes",
            icon: "🚀",
            title: "A living archive of how the world cooks.",
            body: "Forkit grows with the people who use it. Every recipe shared, every fork published, every variation documented adds to something bigger - a collective record of culinary knowledge that belongs to everyone."
        }
    ];

    return (
        <div className="min-h-screen bg-transparent text-white font-sans selection:bg-amber-400 selection:text-stone-950 overflow-x-hidden">

            {/* ── Hero ── */}
            <section className="relative min-h-screen flex flex-col justify-center items-center px-6 py-32 text-center overflow-hidden">

                {/* ambient glow rings - Tailwind only */}
                <div
                    className="absolute inset-0 flex items-center justify-center pointer-events-none"
                    style={{ transform: `translateY(${scrollY * 0.15}px)` }}
                >
                    <div className="w-96 h-96 rounded-full border border-amber-400/10 absolute animate-ping" style={{ animationDuration: "4s" }} />
                    <div className="w-72 h-72 rounded-full border border-amber-400/15 absolute animate-ping" style={{ animationDuration: "3s", animationDelay: "1s" }} />
                    <div className="w-48 h-48 rounded-full bg-amber-400/5 absolute blur-3xl animate-pulse" style={{ animationDuration: "5s" }} />
                </div>

                {/* wordmark */}
                <div
                    className="relative z-10 transition-all duration-1000 opacity-100 translate-y-0"
                    style={{ animationFillMode: "both" }}
                >
                    <div className="inline-flex items-center gap-3 mb-8">
                        <div className="w-px h-8 bg-amber-400/40" />
                        <span className="text-amber-400/70 text-xs tracking-[0.35em] uppercase font-semibold">The Story of</span>
                        <div className="w-px h-8 bg-amber-400/40" />
                    </div>

                    <div className="w-full flex justify-center">
                        <Logo />
                    </div>

                    <p className="text-stone-400 text-lg md:text-xl max-w-xl mx-auto leading-relaxed mt-6">
                        The platform where recipes are shared, improved, and credited -
                        because culinary knowledge belongs to everyone who cooks.
                    </p>

                    {/* scroll cue */}
                    <div className="mt-16 flex flex-col items-center gap-2 animate-bounce">
                        <span className="text-stone-600 text-xs tracking-widest uppercase">Scroll</span>
                        <svg className="w-4 h-4 text-amber-400/50" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                        </svg>
                    </div>
                </div>
            </section>

            {/* ── Origin quote ── */}
            <section className="px-6 py-24 max-w-4xl mx-auto">
                <Reveal>
                    <blockquote className="relative pl-8 border-l-2 border-amber-400">
                        <div className="absolute -left-3 -top-2 text-6xl text-amber-400/20 font-serif leading-none select-none">"</div>
                        <p className="text-2xl md:text-3xl text-stone-200 font-light leading-relaxed italic">
                            The best recipes aren't invented - they're iterated.
                            Every dish you love was built on someone else's foundation.
                            Forkit exists to make that inheritance visible.
                        </p>
                    </blockquote>
                </Reveal>
            </section>

            {/* ── Stats bar ── */}
            <section className="px-6 py-16 max-w-5xl mx-auto">
                <Reveal>
                    <div className="rounded-2xl border border-amber-400/10 bg-amber-400/5 backdrop-blur-sm px-8 py-10 grid grid-cols-2 md:grid-cols-4 gap-8">
                        <Stat value="∞" label="Recipes to discover" />
                        <Stat value="∀" label="Cuisines welcome" />
                        <Stat value="∞" label="Variations possible" />
                        <Stat to={100} suffix="%" label="Free to fork" />
                    </div>
                </Reveal>
            </section>

            {/* ── Chapter timeline ── */}
            <section className="px-6 py-24 max-w-3xl mx-auto">
                <Reveal className="mb-16">
                    <div className="flex items-center gap-4 mb-3">
                        <div className="h-px flex-1 bg-amber-400/20" />
                        <span className="text-amber-400/60 text-xs tracking-[0.3em] uppercase font-semibold">Origin</span>
                        <div className="h-px flex-1 bg-amber-400/20" />
                    </div>
                    <h2 className="text-4xl md:text-5xl font-black text-white text-center">Why Forkit exists.</h2>
                </Reveal>

                <div>
                    {chapters.map((c, i) => (
                        <Chapter key={i} index={i} {...c} isLast={i === chapters.length - 1} />
                    ))}
                </div>
            </section>

            {/* ── What Forkit is ── */}
            <section className="px-6 py-24 max-w-5xl mx-auto">
                <Reveal className="mb-16 text-center">
                    <span className="text-amber-400/60 text-xs tracking-[0.3em] uppercase font-semibold">Philosophy</span>
                    <h2 className="text-4xl md:text-5xl font-black text-white mt-2">Built different, on purpose.</h2>
                </Reveal>

                <div className="grid md:grid-cols-3 gap-4">
                    {[
                        {
                            icon: "🍴",
                            title: "Fork Anything",
                            body: "A recipe is never finished. Take any recipe, adapt it, make it yours, and publish your version alongside the original. Cooking is collaborative - your platform should be too."
                        },
                        {
                            icon: "🔍",
                            title: "Find by Feeling",
                            body: "Semantic search means you can describe what you're craving - not just keyword-match it. \"Something warm and spicy for a rainy evening\" is a valid search query here."
                        },
                        {
                            icon: "🛡️",
                            title: "Your Identity, Your Way",
                            body: "Passkeys and OAuth from day one. No passwords stored. No dark patterns. Security that gets out of the way of the thing that actually matters: the food."
                        }
                    ].map((card, i) => (
                        <Reveal key={i} delay={i * 120}>
                            <div className="rounded-2xl border border-amber-400/10 bg-amber-400/5 p-8 h-full hover:border-amber-400/30 hover:bg-amber-400/10 transition-all duration-300 group">
                                <div className="text-3xl mb-4 group-hover:scale-110 transition-transform duration-300 inline-block">{card.icon}</div>
                                <h3 className="text-white font-bold text-lg mb-3">{card.title}</h3>
                                <p className="text-stone-400 text-sm leading-relaxed">{card.body}</p>
                            </div>
                        </Reveal>
                    ))}
                </div>
            </section>

            {/* ── Manifesto strip ── */}
            <section className="px-6 py-20 overflow-hidden">
                <Reveal>
                    <div className="max-w-4xl mx-auto rounded-3xl border border-amber-400/20 bg-gradient-to-br from-amber-400/10 via-amber-400/5 to-transparent p-12 md:p-16 relative overflow-hidden">
                        {/* decorative large fork character */}
                        <div className="absolute right-8 top-1/2 -translate-y-1/2 text-9xl opacity-5 select-none pointer-events-none font-black">
                            🍴
                        </div>

                        <span className="text-amber-400/60 text-xs tracking-[0.3em] uppercase font-semibold mb-4 block">Our Belief</span>
                        <p className="text-2xl md:text-3xl font-light text-stone-200 leading-relaxed max-w-2xl">
                            A recipe shared is a meal given to everyone who will ever read it.
                            Forkit is the <span className="text-amber-400 font-semibold">infrastructure</span> that
                            makes sure it doesn't get lost.
                        </p>
                    </div>
                </Reveal>
            </section>

            {/* ── Community values ── */}
            <section className="px-6 py-24 max-w-3xl mx-auto text-center">
                <Reveal>
                    <span className="text-amber-400/60 text-xs tracking-[0.3em] uppercase font-semibold">Our Values</span>
                    <h2 className="text-4xl md:text-5xl font-black text-white mt-2 mb-4">Food is meant to be shared.</h2>
                    <p className="text-stone-400 text-lg leading-relaxed max-w-xl mx-auto">
                        Forkit is built around a simple belief: culinary knowledge improves when it circulates freely.
                        No walled gardens. No algorithmic black boxes. No recipe buried under a life story you have to scroll past.
                        Just food, community, and credit given where it's due.
                    </p>
                </Reveal>

                <Reveal delay={150} className="mt-12">
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-left">
                        {[
                            { icon: "🤝", title: "Attribute generously", body: "Every fork traces back to its origin. Credit is built into the structure, not bolted on." },
                            { icon: "🌍", title: "Every cuisine belongs", body: "No cuisine is niche here. Street food and fine dining live side by side, as they should." },
                            { icon: "🔓", title: "Open by default", body: "Recipes are meant to travel. Share publicly, iterate openly, keep the knowledge moving." },
                        ].map((v, i) => (
                            <div key={i} className="rounded-xl border border-amber-400/10 bg-amber-400/5 p-6 hover:border-amber-400/25 transition-all duration-300">
                                <div className="text-2xl mb-3">{v.icon}</div>
                                <p className="text-white font-semibold text-sm mb-1">{v.title}</p>
                                <p className="text-stone-500 text-sm leading-relaxed">{v.body}</p>
                            </div>
                        ))}
                    </div>
                </Reveal>
            </section>

            {/* ── CTA ── */}
            <section className="px-6 py-32 text-center">
                <Reveal>
                    <h2 className="text-5xl md:text-7xl font-black text-white mb-4 tracking-tight">
                        Ready to{" "}
                        <span className="text-amber-400 relative inline-block">
                            Fork
                            <span className="absolute -bottom-1 left-0 w-full h-0.5 bg-amber-400/50 rounded-full" />
                        </span>
                        ?
                    </h2>
                    <p className="text-stone-400 max-w-md mx-auto text-lg leading-relaxed mb-12">
                        Join the community. Share a recipe. Improve someone else's. Start cooking.
                    </p>

                    <div className="flex flex-wrap gap-4 justify-center">
                        <button className="px-8 py-4 bg-amber-400 text-stone-950 font-bold rounded-full text-base hover:bg-amber-300 active:scale-95 transition-all duration-200 shadow-lg shadow-amber-400/20 hover:shadow-amber-400/40 hover:-translate-y-0.5"
                        onClick={() => {setIsLoading(true); window.location.replace("/recipes")}}
                        >
                            Explore Recipes
                        </button>
                        <button className="px-8 py-4 border border-amber-400/30 text-amber-400 font-semibold rounded-full text-base hover:border-amber-400/60 hover:bg-amber-400/5 active:scale-95 transition-all duration-200"
                        onClick={() => {setIsLoading(true); window.location.replace("/register")}}
                        >
                            Create Account
                        </button>
                    </div>
                </Reveal>
            </section>

            {/* ── Footer note ── */}
            <div className="px-6 pb-12 text-center">
                <Reveal>
                    <div className="flex items-center justify-center gap-4 mb-4">
                        <div className="h-px w-16 bg-amber-400/20" />
                        <span className="text-amber-400 text-sm font-black tracking-tighter">Forkit</span>
                        <div className="h-px w-16 bg-amber-400/20" />
                    </div>
                    <p className="text-stone-600 text-xs tracking-widest uppercase">
                        Built for cooks, by cooks · © 2026
                    </p>
                </Reveal>
            </div>

        </div>
    );
}