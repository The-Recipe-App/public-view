import { useQueryClient } from "@tanstack/react-query";
import backendUrlV1 from "../../urls/backendUrl";
import { useContextManager } from "../ContextProvider";

/* -------------------------
   Helpers
------------------------- */

function jsonHeaders() {
    return { "Content-Type": "application/json" };
}

async function parseJsonSafe(res) {
    try {
        return await res.json();
    } catch {
        return null;
    }
}

function extractErrorMessage(data, fallback) {
    if (!data) return fallback;
    if (typeof data.message === "string") return data.message;
    if (Array.isArray(data.message)) return data.message.map(d => d.msg).join(", ");
    return fallback;
}

/* -------------------------
   Central Auth Hook
------------------------- */

export function useAuthApi() {
    const { setIsLoading } = useContextManager();
    const queryClient = useQueryClient();

    async function withLoading(fn) {
        try {
            setIsLoading(true);
            return await fn();
        } finally {
            setIsLoading(false);
        }
    }

    // ─────────────────────────────
    // Login (password, device-aware, OTP-capable)
    // ─────────────────────────────
    function loginWithPassword(identifier, password) {
        return withLoading(async () => {
            const res = await fetch(`${backendUrlV1}/auth/security/login`, {
                method: "POST",
                credentials: "include",
                headers: jsonHeaders(),
                body: JSON.stringify({ identifier, password }),
            });

            const data = await parseJsonSafe(res);
            if (!res.ok) throw new Error(extractErrorMessage(data, "Invalid credentials"));

            // If OTP challenge required, return it to UI
            if (data?.challenge === "otp_required") {
                return data;
            }
            if (!res.ok) throw new Error(extractErrorMessage(data, "Invalid credentials"));
            window.location.replace(localStorage.getItem("redirectAfterLogin") || "/");
            return data; // { ok: true }
        });
    }

    // ─────────────────────────────
    // Verify login OTP (step-up auth)
    // ─────────────────────────────
    function verifyLoginOtp({ identifier, challenge_id, code }) {
        return withLoading(async () => {
            const res = await fetch(`${backendUrlV1}/auth/security/verify-otp`, {
                method: "POST",
                credentials: "include",
                headers: jsonHeaders(),
                body: JSON.stringify({
                    email: identifier,     // backend still uses email for OTP
                    challenge_id,
                    code,
                }),
            });

            const data = await parseJsonSafe(res);
            if (!res.ok) throw new Error(extractErrorMessage(data, "Invalid verification code"));
            window.location.replace(localStorage.getItem("redirectAfterLogin") || "/");
            return data; // { ok: true }
        });
    }

    // ─────────────────────────────
    // Register
    // ─────────────────────────────
    function registerWithPassword(email, password, username = null) {
        return withLoading(async () => {
            const res = await fetch(`${backendUrlV1}/auth/registration/register`, {
                method: "POST",
                credentials: "include",
                headers: jsonHeaders(),
                body: JSON.stringify({ email, password, username }),
            });

            const data = await parseJsonSafe(res);
            if (!res.ok) throw new Error(extractErrorMessage(data, "Registration failed"));
            return data;
        });
    }

    // ─────────────────────────────
    // Current User
    // ─────────────────────────────
    function getCurrentUser() {
        return withLoading(async () => {
            const res = await fetch(`${backendUrlV1}/auth/security/me`, {
                credentials: "include",
            });

            if (!res.ok) return null;
            return res.json();
        });
    }

    // ─────────────────────────────
    // Logout
    // ─────────────────────────────
    function logout() {
        return withLoading(async () => {
            //await supabase.auth.signOut();
            const res = await fetch(`${backendUrlV1}/auth/security/logout`, {
                method: "POST",
                credentials: "include",
            });

            if (!res.ok) throw new Error("Logout failed");

            queryClient.removeQueries({ queryKey: ["profile", "me"] });
            queryClient.clear();
            if (window.location.pathname.startsWith('/profile')) {
                window.location.replace('/');
            } else {
                window.location.reload();
            }
        });
    }

    return {
        loginWithPassword,
        verifyLoginOtp,
        registerWithPassword,
        getCurrentUser,
        logout,
    };
}
