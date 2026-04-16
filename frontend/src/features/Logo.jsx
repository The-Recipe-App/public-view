import { useEffect, useState } from "react";

export default function Logo({
    src = "/site_logo_text.svg",
    width = 280,
}) {
    const [viewBox, setViewBox] = useState(null);

    useEffect(() => {
        const img = new Image();
        img.onload = () => {
            const w = img.naturalWidth || 100;
            const h = img.naturalHeight || 100;
            setViewBox(`0 0 ${w} ${h}`);
        };
        img.src = src;
    }, [src]);

    if (!viewBox) return null;

    return (
        <svg
            width={width}
            viewBox={viewBox}
            preserveAspectRatio="xMidYMid meet"
            style={{
                display: "block",
                userSelect: "none",
                pointerEvents: "none",
            }}
            aria-hidden
        >
            <image
                href={src}
                width="100%"
                height="100%"
                preserveAspectRatio="xMidYMid meet"
            />
        </svg>
    );
}
