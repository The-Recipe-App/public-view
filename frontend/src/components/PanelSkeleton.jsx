import React from "react";

export default function PanelSkeleton({
    title = true,
    rows = 3,
    padded = true,
}) {
    return (
        <div
            className={`
        rounded-2xl border border-neutral-700
        bg-gradient-to-br from-black/20 to-black/10
        ${padded ? "p-6" : ""}
        animate-pulse
        `}
        >
            {/* Header */}
            {title && (
                <div className="flex items-center gap-3 mb-4">
                    <div className="h-5 w-5 rounded-full bg-white/10" />
                    <div className="h-4 w-32 rounded bg-white/10" />
                </div>
            )}

            {/* Content rows */}
            <div className="space-y-3">
                {Array.from({ length: rows }).map((_, i) => (
                    <div
                        key={i}
                        className="h-3 rounded bg-white/10"
                        style={{
                            width:
                                i === rows - 1
                                    ? "60%"
                                    : `${80 - i * 5}%`,
                        }}
                    />
                ))}
            </div>
        </div>
    );
}
