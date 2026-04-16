// src/hooks/useSearchHooks.js
import { useEffect, useState } from "react";
import backendUrlV1 from "../urls/backendUrl";

/**
 * Debounce hook: returns the debounced value after `ms` milliseconds.
 */
export function useDebounced(value, ms = 400) {
    const [v, setV] = useState(value);
    useEffect(() => {
        const t = setTimeout(() => setV(value), ms);
        return () => clearTimeout(t);
    }, [value, ms]);
    return v;
}

/**
 * useSearch hook: performs the fetch for a given query and returns
 * { results, loading, error }.
 *
 * - Cancels previous request when query changes or component unmounts
 * - Returns an error object on HTTP or fetch failure.
 * - If server returns 503, error.message will explain "temporarily unavailable".
 */
export function useSearch(query, limit = 10) {
    const [results, setResults] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    useEffect(() => {
        // Normalize query
        const q = typeof query === "string" ? query.trim() : "";

        if (q.length < 3) {
            setResults([]);
            setLoading(false);
            setError(null);
            return;
        }

        // No query -> reset
        if (!q) {
            setResults([]);
            setLoading(false);
            setError(null);
            return;
        }

        const controller = new AbortController();
        let mounted = true;

        const fetchResults = async () => {
            setLoading(true);
            setError(null);

            try {
                const url = `${backendUrlV1}/search?q=${encodeURIComponent(q)}&limit=${limit}`;
                const res = await fetch(url, {
                    method: "GET",
                    headers: { "Content-Type": "application/json" },
                    signal: controller.signal,
                });

                if (!res.ok) {
                    // handle 503 specially
                    if (res.status === 503) {
                        throw { status: 503, message: "Search temporarily unavailable. Model is still loading." };
                    }
                    // try to extract JSON message if available
                    let text;
                    try { text = await res.text(); } catch (_) { text = res.statusText; }
                    throw { status: res.status || 500, message: text || "Search failed" };
                }

                const json = await res.json();
                if (!mounted) return;
                setResults(Array.isArray(json.results) ? json.results : []);
            } catch (err) {
                if (err && err.name === "AbortError") {
                    // fetch aborted; ignore
                    return;
                }
                if (!mounted) return;
                // normalize error object
                if (err && err.status === 503) {
                    setError({ status: 503, message: err.message });
                } else {
                    setError({ status: err.status || 500, message: err.message || String(err) });
                }
                setResults([]);
            } finally {
                if (mounted) setLoading(false);
            }
        };

        fetchResults();

        return () => {
            mounted = false;
            controller.abort();
        };
    }, [query, limit]);

    return { results, loading, error };
}