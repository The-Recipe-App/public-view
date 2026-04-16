import React, { useEffect, useState, useRef } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import Logo from "../features/Logo";
import backendUrlV1 from "../urls/backendUrl";

const CheckIcon = ({ className = "w-10 h-10" }) => (
    <svg viewBox="0 0 24 24" className={className} fill="none">
        <path
            d="M5 12.5l4 4L19 7"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
        />
    </svg>
);

const XIcon = ({ className = "w-8 h-8" }) => (
    <svg viewBox="0 0 24 24" className={className} fill="none">
        <path
            d="M18 6L6 18M6 6l12 12"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
        />
    </svg>
);

const steps = ["Validating link", "Verifying security", "Activating account", "Finalizing"];

export default function ActivateAccount() {
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const token = searchParams.get("token");
    const ran = useRef(false);

    const [status, setStatus] = useState("activating");
    const [message, setMessage] = useState("");
    const [progress, setProgress] = useState(6);

    useEffect(() => {
        if (!token || ran.current) return;
        ran.current = true;

        const controller = new AbortController();
        const timer = setInterval(() => {
            setProgress(p => Math.min(96, p + Math.random() * 5));
        }, 500);

        async function activate() {
            try {
                const res = await fetch(
                    `${backendUrlV1}/auth/registration/activate-account?token=${encodeURIComponent(token)}`,
                    { method: "GET", credentials: "include", signal: controller.signal }
                );

                if (!res.ok) throw new Error("Activation link is invalid or expired.");

                clearInterval(timer);
                setProgress(100);
                setStatus("success");
            } catch (e) {
                clearInterval(timer);
                setStatus("error");
                setMessage(e.message || "Activation failed.");
            }
        }

        activate();
        return () => controller.abort();
    }, [token]);

    return (
        <div className="min-h-screen flex items-center justify-center bg-transparent">
            <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, ease: "easeOut" }}
                className="w-full max-w-md px-8 py-9 rounded-2xl
                   bg-white/5 backdrop-blur-xl
                   border border-white/10
                   shadow-lg text-center"
            >
                <div className="mb-6 flex justify-center">
                    <Logo width={120} />
                </div>

                {/* Loader / Success icon */}
                <div className="flex justify-center mb-4">
                    {status === "success" ? (
                        <motion.div
                            initial={{ scale: 0.9, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            transition={{ duration: 0.3 }}
                            className="text-emerald-400"
                        >
                            <CheckIcon />
                        </motion.div>
                    ) : status === "error" ? (
                        <div className="text-red-400">
                            <XIcon />
                        </div>
                    ) : (
                        <motion.div
                            className="w-8 h-8 border-2 border-amber-400/30 border-t-amber-400 rounded-full"
                            animate={{ rotate: 360 }}
                            transition={{ repeat: Infinity, duration: 1.2, ease: "linear" }}
                        />
                    )}
                </div>

                {/* Title */}
                <AnimatePresence mode="wait">
                    {status === "activating" && (
                        <motion.h1
                            key="activating"
                            initial={{ opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0 }}
                            className="text-lg font-medium text-white"
                        >
                            Activating your account
                        </motion.h1>
                    )}

                    {status === "success" && (
                        <motion.h1
                            key="success"
                            initial={{ opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="text-lg font-medium text-white"
                        >
                            Welcome Aboard!
                        </motion.h1>
                    )}

                    {status === "error" && (
                        <motion.h1
                            key="error"
                            initial={{ opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="text-lg font-medium text-red-400"
                        >
                            Activation failed
                        </motion.h1>
                    )}
                </AnimatePresence>

                {/* Step text */}
                {status === "activating" && (
                    <p className="mt-2 text-sm text-gray-400">
                        {steps[Math.min(steps.length - 1, Math.floor(progress / 30))]}
                    </p>
                )}

                {/* Progress bar */}
                <div className="mt-6 h-1.5 w-full bg-white/10 rounded-full overflow-hidden">
                    <motion.div
                        className="h-full bg-amber-400/80"
                        animate={{ width: `${progress}%` }}
                        transition={{ ease: "easeOut", duration: 0.4 }}
                    />
                </div>

                {/* Success / Error actions */}
                <AnimatePresence>
                    {status === "success" && (
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            className="mt-6"
                        >
                            <p className="text-sm text-gray-400">
                                Your account is ready to use.
                            </p>
                            <button
                                onClick={() => window.location.href = "/"}
                                className="mt-4 px-6 py-2 rounded-lg
                           bg-orange-400/90 text-black
                           text-sm font-medium hover:bg-orange-400 transition"
                            >
                                Continue to Forkit
                            </button>
                        </motion.div>
                    )}

                    {status === "error" && (
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            className="mt-6"
                        >
                            <p className="text-sm text-gray-400">{message}</p>
                            <button
                                onClick={() => window.location.reload()}
                                className="mt-4 px-5 py-2 rounded-lg
                           bg-amber-400/90 text-black
                           text-sm font-medium hover:bg-amber-400 transition"
                            >
                                Retry
                            </button>
                        </motion.div>
                    )}
                </AnimatePresence>
            </motion.div>
        </div>
    );
}
