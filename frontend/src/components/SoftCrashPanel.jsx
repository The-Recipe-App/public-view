import React from "react";
import { RotateCcw, AlertTriangle, Frown } from "lucide-react";

export default function SoftCrashPanel({
    title = "That didn't go as planned",
    message = "This section couldn't load right now.",
    hint = "A quick refresh usually fixes it.",
    onRetry,
}) {
    return (
        <div
            className="
                p-8 rounded-2xl
                border border-red-500/30
                bg-gradient-to-br from-red-900/20 via-black/30 to-black/40
                text-center
            "
        >
            {/* Icon */}
            <div className="flex justify-center mb-4">
                <div className="h-14 w-14 rounded-full bg-red-500/10 flex items-center justify-center">
                    <AlertTriangle className="w-7 h-7 text-red-400" />
                </div>
            </div>

            {/* Text */}
            <div className="flex flex-col md:flex-row items-center justify-center md:gap-x-2 w-full text-lg font-semibold text-red-200">
                <Frown className="w-8 inline-block" /> <p>Uh oh - {title}</p>
            </div>

            <p className="mt-2 text-sm text-red-300/90">
                {message}
            </p>

            {hint && (
                <p className="mt-1 text-xs text-red-300/60">
                    {hint}
                </p>
            )}

            {/* Actions */}
            <div className="mt-6 flex justify-center gap-3">
                <button
                    onClick={onRetry ?? (() => window.location.reload())}
                    className="
                        inline-flex items-center gap-2
                        px-4 py-2 rounded-lg
                        bg-red-600/90 hover:bg-red-500
                        text-black text-sm font-semibold
                        transition
                    "
                >
                    <RotateCcw className="w-4 h-4" />
                    Try again
                </button>
            </div>
        </div>
    );
}
