//getRouteParams.js
import { useParams, useSearchParams } from "react-router-dom";

export function useRouteVersion() {
    const params = useParams();              // path params: { language, version, ... }
    const [search] = useSearchParams();      // query params

    // prefer explicit query param v= (legacy links), then try path params
    const vQuery = search.get("v") || search.get("version");
    const langQuery = search.get("language");

    const language = langQuery || params.language || "python"; // default fallback
    const versionRaw = vQuery || params.version || null;       // might be 'v1.2.3-release' or '1.2.3'

    // normalize display vs full if you want (adapt to your context shape)
    const display = versionRaw ? versionRaw.replace(/^v?/, "").replace(/-release$/, "") : null;
    const full = versionRaw
        ? versionRaw.includes("-release")
            ? versionRaw
            : `v${display}-release` // optional: construct full branch if only display provided
        : null;

    return { language, versionRaw, versionFull: full, versionDisplay: display };
}
