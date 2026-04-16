// LoadingAnimation.jsx
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState } from "react";

const PHASES = [
    "Igniting burners…",
    "Simmering ingredients…",
    "Seasoning flavors…",
    "Almost ready…",
];

const STALL_MESSAGES = [
    "Seems like the water is cold today…",
    "Giving the flavors a little extra time…",
    "Good things take patience…",
    "Letting it cook just right…",
];

const FINAL_MESSAGE = "Serving you a hot dish now!";

/* ───────── COMPONENT ─────────
 Props:
  - isLoading: boolean (required)
  - shouldExit: boolean (optional, the child will call setShouldExit(true) to request unmount)
  - setShouldExit: function(boolean) (optional)
*/
export default function LoadingScreen({
    isLoading = true,
    shouldExit = false,
    setShouldExit = () => { },
}) {
    const [phase, setPhase] = useState(0);
    const [stall, setStall] = useState(0);
    const [width, setWidth] = useState(typeof window !== "undefined" ? window.innerWidth : 1024);
    const reduce = useReducedMotion();

    const phaseTimerRef = useRef(null);
    const stallTimerRef = useRef(null);
    const exitTimerRef = useRef(null);

    useEffect(() => {
        const onResize = () => setWidth(window.innerWidth);
        window.addEventListener("resize", onResize);
        return () => window.removeEventListener("resize", onResize);
    }, []);

    // Phase progression while loading - only while loading
    useEffect(() => {
        // clear any existing phase timer
        if (phaseTimerRef.current) {
            clearTimeout(phaseTimerRef.current);
            phaseTimerRef.current = null;
        }

        const lastPhase = PHASES.length - 1;

        if (isLoading && phase < lastPhase) {
            // advance phase every 2s while loading
            phaseTimerRef.current = setTimeout(() => {
                setPhase((p) => Math.min(lastPhase, p + 1));
            }, 2000);
        }

        // If loading just finished, snap to final phase so FINAL_MESSAGE appears
        if (!isLoading) {
            setPhase(lastPhase);
        }

        return () => {
            if (phaseTimerRef.current) {
                clearTimeout(phaseTimerRef.current);
                phaseTimerRef.current = null;
            }
        };
    }, [isLoading, phase]);

    useEffect(() => {
        // clear existing stall interval
        if (stallTimerRef.current) {
            clearInterval(stallTimerRef.current);
            stallTimerRef.current = null;
        }

        const lastPhase = PHASES.length - 1;
        if (isLoading && phase === lastPhase) {
            stallTimerRef.current = setInterval(() => {
                setStall((s) => (s + 1) % STALL_MESSAGES.length);
            }, 4200);
        }

        return () => {
            if (stallTimerRef.current) {
                clearInterval(stallTimerRef.current);
                stallTimerRef.current = null;
            }
        };
    }, [phase, isLoading]);

    useEffect(() => {
        if (exitTimerRef.current) {
            clearTimeout(exitTimerRef.current);
            exitTimerRef.current = null;
        }

        if (!isLoading) {
            try {
                setShouldExit(false);
            } catch {
                // noop if setter missing or throws
            }
            const FINAL_VISIBLE_MS = 900;

            exitTimerRef.current = setTimeout(() => {
                try {
                    setShouldExit(true);
                } catch {
                    // noop
                }
            }, FINAL_VISIBLE_MS);
        } else {
            try {
                setShouldExit(false);
            } catch {
                // noop
            }
        }

        return () => {
            if (exitTimerRef.current) {
                clearTimeout(exitTimerRef.current);
                exitTimerRef.current = null;
            }
        };
    }, [isLoading, setShouldExit]);

    useEffect(() => {
        return () => {
            if (phaseTimerRef.current) clearTimeout(phaseTimerRef.current);
            if (stallTimerRef.current) clearInterval(stallTimerRef.current);
            if (exitTimerRef.current) clearTimeout(exitTimerRef.current);
        };
    }, []);

    const isMobile = width < 640;
    const isTablet = width >= 640 && width < 1024;
    const orbits = isMobile ? [50, 70, 110] : isTablet ? [70, 110, 160] : [140, 220, 300];

    const containerVariants = {
        initial: { opacity: 0 },
        enter: { opacity: 1, transition: { duration: 0.45 } },
        exit: { opacity: 0, transition: { duration: 0.45 } },
    };

    const flameAnimation = reduce
        ? {}
        : {
            scale: [1, 1.45, 1],
            backgroundColor: ["#F97316", "#F59E0B", "#EF4444", "#B75EFC"],
            boxShadow: ["0 0 0 rgba(0,0,0,0)", "0 0 30px rgba(249,115,22,0.9)", "0 0 0 rgba(0,0,0,0)"],
        };

    return (
        <AnimatePresence>
            {!window.location.pathname.startsWith("/activate-account") && !shouldExit && (
                <motion.div
                    role="status"
                    aria-live="polite"
                    variants={containerVariants}
                    initial="initial"
                    animate="enter"
                    exit="exit"
                    className="fixed inset-0 z-[999] flex items-center justify-center bg-black/70 backdrop-blur-sm"
                >
                    {/* Core flame */}
                    <motion.div
                        className="relative z-20 rounded-full"
                        style={{
                            width: isMobile ? 18 : 28,
                            height: isMobile ? 18 : 28,
                        }}
                        animate={flameAnimation}
                        transition={{ duration: 1.2, repeat: Infinity, ease: "easeInOut" }}
                    />

                    {/* Orbits */}
                    {orbits.map((size, i) => {
                        const dur = 10 + i * 6;
                        const reverse = i % 2 === 1;
                        const dotSize = isMobile ? 4 : 6;
                        return (
                            <motion.div
                                key={size}
                                className="absolute pointer-events-none"
                                style={{
                                    width: size,
                                    height: size,
                                }}
                                animate={reduce ? {} : { rotate: reverse ? -360 : 360 }}
                                transition={reduce ? {} : { duration: dur, repeat: Infinity, ease: "linear" }}
                            >
                                {["#F59E0B", "#22C55E", "#F97316", "#B75EFC"].map((c, ii) => (
                                    <span
                                        key={ii}
                                        className="absolute rounded-full"
                                        style={{
                                            width: dotSize,
                                            height: dotSize,
                                            top: "50%",
                                            left: "50%",
                                            transform: `rotate(${(360 / 4) * ii}deg) translate(${size / 2}px)`,
                                            backgroundColor: c,
                                            boxShadow: `0 0 10px ${c}`,
                                        }}
                                    />
                                ))}
                            </motion.div>
                        );
                    })}

                    {/* Text */}
                    <div className="absolute bottom-16 px-6 text-center max-w-sm">
                        <motion.p
                            key={isLoading ? phase : "final"}
                            initial={{ opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -6 }}
                            transition={{ duration: 0.35 }}
                            className="text-sm tracking-widest text-gray-200 uppercase"
                        >
                            {isLoading ? PHASES[phase] : FINAL_MESSAGE}
                        </motion.p>

                        {isLoading && phase === PHASES.length - 1 && (
                            <motion.p initial={{ opacity: 0 }} animate={{ opacity: 0.7 }} transition={{ duration: 0.3 }} className="mt-2 text-xs text-gray-400">
                                {STALL_MESSAGES[stall]}
                            </motion.p>
                        )}
                    </div>
                </motion.div>
            )}
        </AnimatePresence>
    );
}
