import { useEffect, useRef, useState } from "react";
import backendUrlV1 from "../urls/backendUrl";

function useDebounced(value, ms = 400) {
    const [v, setV] = useState(value);
    useEffect(() => {
        const t = setTimeout(() => setV(value), ms);
        return () => clearTimeout(t);
    }, [value, ms]);
    return v;
}

const USERNAME_RE = /^[a-zA-Z0-9_]{3,30}$/;

export function useUsernameAvailabilitySimple(username, enabled = true) {
    const debounced = useDebounced(username, 400);
    const [status, setStatus] = useState(null);
    const controller = useRef(null);

    useEffect(() => {
        if (!enabled) return;
        if (!debounced) {
            setStatus(null);
            return;
        }


        if (!USERNAME_RE.test(debounced)) {
            setStatus("invalid");
            return;
        }


        controller.current?.abort();
        const ctrl = new AbortController();
        controller.current = ctrl;

        let mounted = true;
        setStatus("checking");


        fetch(`${backendUrlV1}/profile/${encodeURIComponent(debounced)}`, {
            method: "GET",
            credentials: "include",
            signal: ctrl.signal,
        })
            .then(async (res) => {
                if (!mounted) return;
                if (res.status === 404) {
                    setStatus("available");
                    return;
                }
                if (res.ok) {
                    setStatus("taken");
                    return;
                }

                setStatus(null);
            })
            .catch((err) => {
                if (err.name === "AbortError") return;

                setStatus(null);
            });

        return () => {
            mounted = false;
            ctrl.abort();
        };
    }, [debounced, enabled]);

    return status;
}