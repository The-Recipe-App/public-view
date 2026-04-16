import React, { Fragment, useEffect, useRef, useState } from "react";
import { Dialog, DialogPanel, DialogTitle, Transition, TransitionChild } from "@headlessui/react";
import { createPortal } from "react-dom";
import {
    Info,
    AlertTriangle,
    CheckCircle2,
    XCircle,
    X,
    Loader2,
} from "lucide-react";

/* ───────────────── Config ───────────────── */

const TYPE_ICON = {
    info: Info,
    warning: AlertTriangle,
    success: CheckCircle2,
    error: XCircle,
    consent: AlertTriangle,
};

const TYPE_COLOR = {
    info: "text-blue-400",
    warning: "text-yellow-400",
    success: "text-green-500",
    error: "text-red-500",
    consent: "text-purple-400",
};

/* ───────────────── Modal ───────────────── */

export default function Modal({
    isOpen,
    onClose,

    /* content */
    title = "Notification",
    description = "",
    children,

    /* type */
    type = "info",
    icon,

    /* behavior */
    lock = true,
    preventCloseWhileBusy = true,
    showCloseButton = false,
    unlockAfter = null,
    forceProgress = false,

    /* actions */
    primaryAction,
    secondaryAction,
    tertiaryAction,
    quaternaryAction,
    quinaryAction,
    autoCloseOnSuccess = false,

    /* steps */
    steps = null,
    initialStep = 0,

    /* appearance */
    variant = "default",
    zIndex = 1005,

    /* close */
    enableClose = false,

    /* ───────────── Consent Additions ───────────── */
    mode = "default",
    consents = [],
    requireAllConsents = true,
    requireScroll = false,
}) {
    const initialFocusRef = useRef(null);
    const bodyRef = useRef(null);

    const [busy, setBusy] = useState(false);
    const [unlocked, setUnlocked] = useState(!lock);
    const [step, setStep] = useState(initialStep);
    const [checked, setChecked] = useState({});
    const [scrolledToEnd, setScrolledToEnd] = useState(!requireScroll);

    const Icon = icon || TYPE_ICON[type] || Info;

    /* ───────────── Scroll lock ───────────── */
    useEffect(() => {
        if (!isOpen) return;
        const prev = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        return () => (document.body.style.overflow = prev);
    }, [isOpen]);

    /* ───────────── Timed unlock ───────────── */
    useEffect(() => {
        if (!isOpen || !lock || !unlockAfter) return;
        const t = setTimeout(() => setUnlocked(true), unlockAfter * 1000);
        return () => clearTimeout(t);
    }, [isOpen, lock, unlockAfter]);

    /* ───────────── ESC hard-block ───────────── */
    useEffect(() => {
        if (!isOpen || unlocked) return;
        const handler = (e) => {
            if (e.key === "Escape") {
                e.preventDefault();
                e.stopPropagation();
            }
        };
        window.addEventListener("keydown", handler, true);
        return () => window.removeEventListener("keydown", handler, true);
    }, [isOpen, unlocked]);

    const safeClose = () => {
        if (typeof onClose === "function") onClose();
    };

    const runAction = async (action) => {
        if (!action?.onClick) return;
        try {
            setBusy(true);
            await action.onClick({
                step,
                next: () => setStep((s) => s + 1),
                prev: () => setStep((s) => Math.max(0, s - 1)),
                unlock: () => setUnlocked(true),
            });
            if (autoCloseOnSuccess) safeClose();
        } finally {
            setBusy(false);
        }
    };

    const renderActionButton = (action, style = "secondary") => {
        if (!action) return null;

        const base =
            "px-4 py-2 rounded-lg transition disabled:opacity-50 flex items-center gap-2";

        const styles = {
            primary:
                "bg-gradient-to-b from-blue-500 to-blue-600 text-white shadow-lg shadow-blue-600/30 hover:from-blue-400 hover:to-blue-500",
            secondary:
                "bg-white/10 text-white backdrop-blur-md ring-1 ring-white/10 hover:bg-white/20",
            ghost:
                "bg-transparent text-gray-300 hover:text-white",
        };

        return (
            <button
                key={action.label}
                disabled={busy || action.disabled || (mode === "consent" && !consentAllowed)}
                onClick={() => runAction(action)}
                className={`${base} ${styles[style]}`}
            >
                {busy && style === "primary" && (
                    <Loader2 size={16} className="animate-spin" />
                )}
                {action.label}
            </button>
        );
    };

    const stepData = steps?.[step];

    const allConsentsAccepted = consents.every(c =>
        !c.required || checked[c.id]
    );

    const consentAllowed =
        (!requireAllConsents || allConsentsAccepted) && scrolledToEnd;

    const handleScroll = () => {
        if (!requireScroll || !bodyRef.current) return;
        const el = bodyRef.current;
        if (el.scrollTop + el.clientHeight >= el.scrollHeight - 10) {
            setScrolledToEnd(true);
        }
    };

    if (!isOpen) return null;

    return createPortal(
        <Transition appear show as={Fragment}>
            <Dialog
                as="div"
                className="relative"
                style={{ zIndex }}
                onClose={unlocked && !busy ? safeClose : () => { }}
                initialFocus={initialFocusRef}
                static
            >
                <div className="fixed inset-0 bg-gradient-to-b from-black/60 via-black/50 to-black/70 backdrop-blur-xl" />

                <div className="fixed inset-0 flex items-center justify-center p-4">
                    <TransitionChild
                        as={Fragment}
                        enter="ease-out duration-300"
                        enterFrom="opacity-0 scale-95 translate-y-2"
                        enterTo="opacity-100 scale-100 translate-y-0"
                        leave="ease-in duration-200"
                        leaveFrom="opacity-100 scale-100"
                        leaveTo="opacity-0 scale-95 translate-y-1"
                    >
                        <DialogPanel
                            ref={initialFocusRef}
                            tabIndex={-1}
                            className={`
                                relative w-full max-w-2xl
                                rounded-2xl p-6
                                bg-gradient-to-br
                                from-neutral/[0.08]
                                via-neutral/[0.05]
                                to-neutral/[0.02]
                                backdrop-blur-2xl
                                border border-neutral-400/70
                                shadow-[0_20px_60px_-15px_rgba(0,0,0,0.8)]
                                outline-none ring-1 ring-white/5
                                ${variant === "terms" || mode === "consent" ? "max-h-[90vh] overflow-y-auto" : ""}
                            `}
                        >
                            {enableClose && unlocked && !busy && (
                                <button
                                    onClick={safeClose}
                                    className="absolute top-4 right-4 text-gray-400 hover:text-red-400"
                                >
                                    <X size={20} />
                                </button>
                            )}

                            <div className="flex items-center gap-4 mb-5">
                                <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-white/10 ring-1 ring-white/15 backdrop-blur-md">
                                    <Icon size={26} className={TYPE_COLOR[type]} />
                                </div>
                                <DialogTitle className="text-xl font-semibold tracking-tight text-white">
                                    {stepData?.title || title}
                                </DialogTitle>
                            </div>

                            {(stepData?.description || description) && (
                                <p className="text-gray-300 mb-4" dangerouslySetInnerHTML={{ __html: stepData?.description || description }} />
                            )}

                            <div
                                ref={bodyRef}
                                onScroll={handleScroll}
                                className="mb-6 max-h-[50vh] overflow-y-auto pr-2"
                            >
                                {stepData?.content || children}
                            </div>

                            {mode === "consent" && consents.length > 0 && (
                                <div className="mb-6">
                                    <p className="text-sm text-gray-200 mb-2">By checking each box, you agree to:</p>
                                    <div className="grid grid-cols-3 items-baseline justify-center space-x-3 ">
                                        {consents.map(c => (
                                            <label key={c.id} className="flex gap-3 text-sm text-gray-200 items-start">
                                                <input
                                                    type="checkbox"
                                                    checked={!!checked[c.id]}
                                                    onChange={e =>
                                                        setChecked(s => ({ ...s, [c.id]: e.target.checked }))
                                                    }
                                                    className="mt-1"
                                                />
                                                <span>
                                                    {c.label}
                                                    {c.required && <span className="text-red-400 ml-1">*</span>}
                                                </span>
                                            </label>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {!forceProgress && (
                                <div className="flex flex-wrap justify-end gap-3">
                                    <>
                                        {renderActionButton(secondaryAction, "secondary")}
                                        {renderActionButton(tertiaryAction, "ghost")}
                                        {renderActionButton(quaternaryAction, "ghost")}
                                        {renderActionButton(quinaryAction, "ghost")}
                                        {renderActionButton(primaryAction, "primary")}
                                    </>
                                </div>
                            )}
                        </DialogPanel>
                    </TransitionChild>
                </div>
            </Dialog>
        </Transition>,
        document.body
    );
}
