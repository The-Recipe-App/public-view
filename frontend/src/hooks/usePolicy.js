import { useEffect, useState } from "react";

const API = "/api/legal"; // adjust if needed

export function usePolicy(policyKey, locale = "en") {
    const [data, setData] = useState(null);
    const [meta, setMeta] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        if (!policyKey) return;

        let cancelled = false;

        async function load() {
            try {
                setLoading(true);

                // 1️⃣ get active policies
                const res = await fetch(`${API}/active?locale=${locale}`);
                const json = await res.json();

                if (!json.ok) throw new Error("Failed to fetch policies");

                const policy = json.policies.find(p => p.key === policyKey);

                if (!policy) {
                    throw new Error(`Policy '${policyKey}' not found`);
                }

                setMeta(policy);

                // 2️⃣ fetch static file
                const fileRes = await fetch(policy.file_url);
                const text = await fileRes.text();

                if (cancelled) return;

                // auto detect format
                if (policy.file_format === "html") {
                    setData({ html: text });
                } else {
                    setData({ markdown: text });
                }
            } catch (err) {
                if (!cancelled) setError(err.message);
            } finally {
                if (!cancelled) setLoading(false);
            }
        }

        load();

        return () => {
            cancelled = true;
        };
    }, [policyKey, locale]);

    return { data, meta, loading, error };
}