import { useCallback, useEffect, useRef, useReducer, useState, useMemo } from "react";
import Logo from "../features/Logo";
import { useAuthApi } from "../features/auth/authApi";
import { useNavigate } from "react-router-dom";
import { useMe } from "../hooks/useMe";
import { loginWithPasskey } from "../features/auth/passkey";
import { supabase } from "../lib/supabase";
import backendUrlV1 from "../urls/backendUrl";
import Modal from "../components/popUpModal";
import { useContextManager } from "../features/ContextProvider";
import { Fingerprint } from "lucide-react";
import { Tooltip } from "react-tooltip";
import toast from 'react-hot-toast';
import ProcessingLoginCanvas from "../canvases/ProcessingLoginCanvas";


function Spinner({ size = 20, className = "" }) {
    return (
        <svg
            width={size}
            height={size}
            viewBox="0 0 24 24"
            className={`animate-spin ${className}`}
            role="img"
            aria-hidden="true"
            
        >
            <defs>
                <linearGradient id="spinnerGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stopColor="#f97316" stopOpacity="1" />
                    <stop offset="100%" stopColor="#f97316" stopOpacity="0.2" />
                </linearGradient>
            </defs>

            <circle
                cx="12"
                cy="12"
                r="10"
                stroke="url(#spinnerGradient)"
                strokeWidth="3"
                strokeLinecap="round"
                fill="none"
                strokeDasharray="60"
                strokeDashoffset="20"
            />
        </svg>
    );
}


const initialState = {
    identifier: "",
    password: "",
    otp: "",
    challengeId: null,
    maskedEmail: "",
    oauthEmail: "",
    showPassword: false,
    error: "",
    loading: {
        password: false,
        otp: false,
        passkey: false,
        oauth: false,
    },
};

function reducer(state, action) {
    switch (action.type) {
        case "SET":
            return { ...state, [action.key]: action.value };
        case "SET_MANY":
            return { ...state, ...action.payload };
        case "SET_LOADING":
            return { ...state, loading: { ...state.loading, ...action.payload } };
        case "RESET":
            return {
                ...initialState,
                loading: { password: false, otp: false, passkey: false, oauth: false },
            };
        default:
            return state;
    }
}

function Login() {
    const [state, dispatch] = useReducer(reducer, initialState);
    const [isLoggingIn, setIsLoggingIn] = useState(false);

    const { setIsLoading } = useContextManager();

    const [popupPermissionAsked, setPopupPermissionAsked] = useState(
        () => localStorage.getItem("allowPopup") === "true"
    );
    const [showPopupPrompt, setShowPopupPrompt] = useState(false);
    const popupRef = useRef(null);

    const anyLoading = useMemo(
        () =>
            state.loading.password ||
            state.loading.otp ||
            state.loading.passkey ||
            state.loading.oauth,
        [state.loading]
    );

    const navigate = useNavigate();
    const { loginWithPassword, verifyLoginOtp } = useAuthApi();
    const { data: me } = useMe();

    const isMountedRef = useRef(true);
    const oauthStartAbortRef = useRef(null);
    const oauthLoginAbortRef = useRef(null);
    const pollAbortRef = useRef(null);
    const pollTimerRef = useRef(null);
    const handledFlowRef = useRef(null);

    const [flowId, setFlowId] = useState(null);
    const [needsReg, setNeedsReg] = useState(false);

    function isMobileDevice() {
        return /Mobi|Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
    }

    function safeDispatch(action) {
        if (isMountedRef.current) dispatch(action);
    }

    useEffect(() => {
        return () => {
            isMountedRef.current = false;
            if (oauthStartAbortRef.current) {
                try { oauthStartAbortRef.current.abort(); } catch { }
            }
            if (oauthLoginAbortRef.current) {
                try { oauthLoginAbortRef.current.abort(); } catch { }
            }
            if (pollAbortRef.current) {
                try { pollAbortRef.current.abort(); } catch { }
            }
            if (pollTimerRef.current) {
                clearInterval(pollTimerRef.current);
                pollTimerRef.current = null;
            }
        };
    }, []);

    useEffect(() => {
        if (me) {
            const redirect = localStorage.getItem("redirectAfterLogin");
            navigate(redirect || "/");
            localStorage.removeItem("redirectAfterLogin");
        }
    }, [me, navigate]);

    useEffect(() => {
        const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => {
            if (session?.user) {
                const email = session.user.email;
                safeDispatch({ type: "SET", key: "oauthEmail", value: email || "" });

                try {
                    const url = new URL(window.location.href);
                    url.searchParams.delete("req_id");
                    window.history.replaceState({}, "", url.pathname);
                } catch { }
            }
        });

        setIsLoading(false);

        return () => {
            sub?.subscription?.unsubscribe?.();
        };
    }, []);

    const handleGoogleLogin = useCallback(async () => {
        if (anyLoading) return;

        resetLoginState(false);
        safeDispatch({ type: "SET", key: "error", value: "" });

        // If permission not yet granted, show the consent prompt first
        if (!popupPermissionAsked) {
            setShowPopupPrompt(true);
            return;
        }

        _doGoogleLogin();
    }, [anyLoading, popupPermissionAsked]);

    const startPolling = useCallback((fid) => {
        if (!fid) return;

        if (pollTimerRef.current) {
            clearInterval(pollTimerRef.current);
            pollTimerRef.current = null;
        }
        if (pollAbortRef.current) {
            try { pollAbortRef.current.abort(); } catch { }
            pollAbortRef.current = null;
        }

        const controller = new AbortController();
        pollAbortRef.current = controller;

        const tick = async () => {
            try {
                const res = await fetch(`${backendUrlV1}/auth/oauth/flow/${encodeURIComponent(fid)}`, {
                    credentials: "include",
                    signal: controller.signal,
                });

                if (!res.ok) return;

                const body = await res.json().catch(() => null);
                if (!body) return;

                if (body.status === "complete" && body.ok) {
                    try {
                        if (popupRef.current && !popupRef.current.closed) {
                            popupRef.current.close();
                            popupRef.current = null;
                        }
                        const url = new URL(window.location.href);
                        url.searchParams.delete("req_id");
                        window.history.replaceState({}, "", url.pathname);
                    } catch { }

                    toast.success("Logged in successfully");
                    window.location.replace(localStorage.getItem("redirectAfterLogin") || "/");
                    return;
                }

                if (body.status === "otp_required") {
                    // FIX 2: removed dangling `sta` statement that caused a ReferenceError
                    clearInterval(pollTimerRef.current);
                    pollTimerRef.current = null;
                    controller.abort();

                    safeDispatch({
                        type: "SET_MANY",
                        payload: {
                            challengeId: body.challenge_id || null,
                            maskedEmail: body.masked_email || "",
                        },
                    });

                    // FIX 4: OTP challenge means we stop the loading canvas so the OTP form is visible
                    setIsLoggingIn(false);

                    toast.info(
                        `OTP sent to ${body.masked_email || "your email"}. Enter it to continue.`,
                        { autoClose: 5000 }
                    );
                    return;
                }

                if (body.status === "needs_registration") {
                    safeDispatch({ type: "SET", key: "oauthEmail", value: body.email || "" });
                    setNeedsReg(true);
                    // FIX 4: reset isLoggingIn so the modal renders correctly
                    setIsLoggingIn(false);
                    controller.abort();
                    return;
                }

                if (body.status === "error") {
                    safeDispatch({ type: "SET", key: "error", value: body.message || "OAuth failed" });
                    toast.error(body.message || "OAuth failed");
                    // FIX 4: reset isLoggingIn on error so the UI recovers
                    setIsLoggingIn(false);
                    controller.abort();
                    return;
                }

            } catch (err) {
                // silent; network errors or aborts are expected during polling
            }
        };

        pollTimerRef.current = setInterval(tick, 1200);
    }, []);


    const _doGoogleLogin = useCallback(async () => {
        setIsLoggingIn(true);
        safeDispatch({ type: "SET_LOADING", payload: { oauth: true } });

        if (oauthStartAbortRef.current) {
            try { oauthStartAbortRef.current.abort(); } catch { }
            oauthStartAbortRef.current = null;
        }
        const controller = new AbortController();
        oauthStartAbortRef.current = controller;

        try {
            const res = await fetch(`${backendUrlV1}/auth/oauth/start`, {
                method: "POST",
                credentials: "include",
                signal: controller.signal,
            });

            const body = await res.json().catch(() => ({}));
            if (!res.ok || !body.req_id) {
                throw new Error(body.detail || "Failed to start OAuth flow");
            }

            const fid = body.req_id;
            const redirectTo = `${window.location.origin}/login?req_id=${encodeURIComponent(fid)}`;

            const { data, error } = await supabase.auth.signInWithOAuth({
                provider: "google",
                options: {
                    redirectTo,
                    queryParams: { prompt: "select_account" },
                    skipBrowserRedirect: true,
                },
            });

            if (error || !data?.url) {
                throw new Error(error?.message || "Failed to get OAuth URL");
            }

            // Always same-tab — cookies, device hash, everything stays consistent
            window.location.href = data.url;

        } catch (err) {
            if (err?.name === "AbortError") {
                safeDispatch({ type: "SET", key: "error", value: "OAuth start aborted" });
                toast.error("OAuth start aborted");
            } else {
                const message = err?.message || "OAuth initiation failed";
                safeDispatch({ type: "SET", key: "error", value: message });
                toast.error(message);
            }
            setIsLoggingIn(false);
        } finally {
            oauthStartAbortRef.current = null;
            safeDispatch({ type: "SET_LOADING", payload: { oauth: false } });
        }
    }, [anyLoading]);

    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        const fid = params.get("req_id");
        if (!fid) return;

        setIsLoggingIn(true);
        if (handledFlowRef.current === fid) return;
        handledFlowRef.current = fid;

        setFlowId(fid);
        safeDispatch({ type: "SET_LOADING", payload: { oauth: true } });

        (async () => {
            if (oauthLoginAbortRef.current) {
                try { oauthLoginAbortRef.current.abort(); } catch { }
                oauthLoginAbortRef.current = null;
            }
            const controller = new AbortController();
            oauthLoginAbortRef.current = controller;

            try {
                const { data } = await supabase.auth.getSession();
                const session = data?.session;
                const access_token =
                    session?.access_token ?? session?.accessToken ?? session?.provider_token ?? null;

                if (access_token) {
                    await fetch(`${backendUrlV1}/auth/oauth/login?req_id=${encodeURIComponent(fid)}`, {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json",
                            Authorization: `Bearer ${access_token}`,
                        },
                        credentials: "include",
                        body: JSON.stringify({ fingerprint: null }),
                        signal: controller.signal,
                    });
                }
            } catch (err) {
                console.warn("OAuth login error: ", err);
            } finally {
                oauthLoginAbortRef.current = null;
                safeDispatch({ type: "SET_LOADING", payload: { oauth: false } });

                // Same tab the whole time — poll once to check OTP/registration/complete
                startPolling(fid);
            }
        })();

    }, [startPolling]);


    function cancelRegisterHandler() {
        setNeedsReg(false);
        setFlowId(null);
        safeDispatch({ type: "SET_MANY", payload: { challengeId: null, maskedEmail: "", oauthEmail: "" } });
    }

    function registerHandler() {
        setNeedsReg(false);
        setIsLoading(true);
        if (flowId) {
            navigate(`/register?req_id=${encodeURIComponent(flowId)}`);
        } else {
            navigate("/register");
        }
    }


    // FIX 5: signature accepts a plain boolean - removed the accidental object call-site below
    function resetLoginState(showToast = true) {
        dispatch({ type: "RESET" });
        setNeedsReg(false);
        setFlowId(null);
        setIsLoggingIn(false);

        if (pollTimerRef.current) {
            clearInterval(pollTimerRef.current);
            pollTimerRef.current = null;
        }
        if (pollAbortRef.current) {
            try { pollAbortRef.current.abort(); } catch { }
            pollAbortRef.current = null;
        }
        if (showToast) {
            toast.info("Form reset");
        }
    }


    const handlePasswordLogin = useCallback(
        async (e) => {
            e.preventDefault();
            if (anyLoading) return;

            setIsLoggingIn(true);
            safeDispatch({ type: "SET", key: "error", value: "" });
            safeDispatch({ type: "SET_LOADING", payload: { password: true } });

            try {
                if (!state.identifier || !state.password) {
                    throw new Error("Please enter both your email/username and password");
                }
                const res = await loginWithPassword(state.identifier, state.password);

                if (res?.challenge === "otp_required") {
                    safeDispatch({
                        type: "SET_MANY",
                        payload: {
                            challengeId: res.challenge_id,
                            maskedEmail: res.masked_email || "",
                        },
                    });
                    // FIX 4: OTP challenge - stop loading canvas so the OTP form is visible
                    setIsLoggingIn(false);
                    toast.info(`OTP sent to ${res.masked_email || "your email"}.`);
                } else {
                    toast.success("Signed in successfully");
                    window.location.replace(localStorage.getItem("redirectAfterLogin") || "/");
                }

            } catch (err) {
                const message = err?.message || "Invalid credentials.";
                safeDispatch({ type: "SET", key: "error", value: message });
                toast.error(message);
            } finally {
                setIsLoggingIn(false);
                safeDispatch({ type: "SET_LOADING", payload: { password: false } });
            }
        },
        [anyLoading, loginWithPassword, state.identifier, state.password]
    );


    const handleVerifyOtp = useCallback(
        async (e) => {
            e.preventDefault();
            if (anyLoading) return;

            safeDispatch({ type: "SET", key: "error", value: "" });
            safeDispatch({ type: "SET_LOADING", payload: { otp: true } });
            setIsLoggingIn(true);

            try {
                await verifyLoginOtp({
                    identifier: state.identifier || state.oauthEmail || undefined,
                    challenge_id: state.challengeId,
                    code: state.otp,
                });

            } catch (err) {
                safeDispatch({ type: "SET", key: "error", value: "Invalid OTP" });
                toast.error("Invalid OTP");
            } finally {
                safeDispatch({ type: "SET_LOADING", payload: { otp: false } });
                setIsLoggingIn(false);
            }
        },
        [anyLoading, verifyLoginOtp, state.identifier, state.oauthEmail, state.challengeId, state.otp]
    );


    const handlePasskey = useCallback(async () => {
        if (!state.identifier) {
            dispatch({ type: "SET", key: "error", value: "Enter your email or username first." });
            toast.error("Enter your email or username first.");
            return;
        }
        if (anyLoading) return;

        setIsLoggingIn(true);
        safeDispatch({ type: "SET", key: "error", value: "" });
        safeDispatch({ type: "SET_LOADING", payload: { passkey: true } });

        try {
            await loginWithPasskey(state.identifier);
            toast.success("Passkey authentication succeeded");
            window.location.replace(localStorage.getItem("redirectAfterLogin") || "/");
        } catch (err) {
            const message = err?.message || "Passkey login failed";
            safeDispatch({ type: "SET", key: "error", value: message });
            toast.error(message);
        } finally {
            safeDispatch({ type: "SET_LOADING", payload: { passkey: false } });
            setIsLoggingIn(false);
        }
    }, [anyLoading, state.identifier, loginWithPasskey]);

    // FIX 1: use the derived `hasChallenge` variable (was incorrectly reading `state.hasChallenge`
    // which is always undefined - challengeId lives at state.challengeId)
    const hasChallenge = Boolean(state.challengeId);


    return (
        <div className="min-h-screen flex items-center justify-center">
            <div className="w-full sm:max-w-[500px] max-w-[90%] rounded-2xl bg-white/5 backdrop-blur border border-white/10 shadow-xl p-8">
                <div className="flex justify-center mb-6">
                    <Logo width={140} />
                </div>
                <h1 className="text-xl font-semibold text-white text-center">Sign in to Forkit</h1>

                {anyLoading || isLoggingIn ? (
                    <ProcessingLoginCanvas />
                ) : (
                    <>
                        {state.error && (
                            <div
                                className="mt-4 text-sm text-red-400 text-center underline px-3 py-2 bg-red-900/30 rounded-lg"
                                role="alert"
                                aria-live="assertive"
                            >
                                {state.error}
                            </div>
                        )}

                        <div className="space-y-4 mt-6">
                            {/* FIX 1: was `state.hasChallenge` (always undefined) - now uses the
                                derived `hasChallenge` boolean so the OTP form actually renders */}
                            {!hasChallenge ? (
                                <div className="flex flex-col justify-evenly">
                                    {/* ---- IDENTIFIER + PASSWORD ---- */}
                                    <div className="space-y-4 w-full">
                                        <form onSubmit={handlePasswordLogin} className="space-y-4 w-full">

                                            {/* hidden username field improves password manager matching */}
                                            <input
                                                type="text"
                                                name="username"
                                                autoComplete="username"
                                                value={state.identifier}
                                                readOnly
                                                tabIndex={-1}
                                                className="hidden"
                                            />

                                            {/* ---------- IDENTIFIER ---------- */}
                                            <div className="space-y-1">
                                                <label htmlFor="identifier" className="sr-only">
                                                    Email or username
                                                </label>

                                                <input
                                                    id="identifier"
                                                    type="text"
                                                    name="identifier"
                                                    autoComplete="username"
                                                    inputMode="email"
                                                    placeholder="Email or Username"
                                                    value={state.identifier}
                                                    onChange={(e) =>
                                                        dispatch({
                                                            type: "SET",
                                                            key: "identifier",
                                                            value: e.target.value,
                                                        })
                                                    }
                                                    disabled={anyLoading}
                                                    className="w-full px-4 py-2.5 rounded-lg bg-neutral-900 border border-gray-700 text-white disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-orange-500/40"
                                                />
                                            </div>

                                            {/* ---------- PASSWORD ---------- */}
                                            <div className="relative space-y-1">
                                                <label htmlFor="password" className="sr-only">
                                                    Password
                                                </label>

                                                <input
                                                    id="password"
                                                    type={state.showPassword ? "text" : "password"}
                                                    name="password"
                                                    autoComplete="current-password"
                                                    placeholder="Password"
                                                    value={state.password}
                                                    onChange={(e) =>
                                                        dispatch({
                                                            type: "SET",
                                                            key: "password",
                                                            value: e.target.value,
                                                        })
                                                    }
                                                    disabled={anyLoading}
                                                    className="w-full px-4 py-2.5 pr-12 rounded-lg bg-neutral-900 border border-gray-700 text-white disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-orange-500/40"
                                                />

                                                <button
                                                    type="button"
                                                    onClick={() =>
                                                        dispatch({
                                                            type: "SET",
                                                            key: "showPassword",
                                                            value: !state.showPassword,
                                                        })
                                                    }
                                                    disabled={anyLoading}
                                                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm disabled:opacity-50"
                                                    aria-pressed={state.showPassword}
                                                >
                                                    {state.showPassword ? "Hide" : "Show"}
                                                </button>
                                            </div>

                                            {/* ---------- SUBMIT ---------- */}
                                            <button
                                                type="submit"
                                                disabled={anyLoading || !state.identifier || !state.password}
                                                aria-busy={state.loading.password}
                                                className={`w-full py-2.5 rounded-lg flex items-center justify-center ${anyLoading || !state.identifier || !state.password
                                                    ? "bg-orange-600/70 cursor-not-allowed"
                                                    : "bg-orange-600 hover:bg-orange-500"
                                                    } text-white`}
                                            >
                                                {state.loading.password ? (
                                                    <div className="text-xs flex items-center gap-x-2">
                                                        <Spinner />
                                                        <span>Signing in…</span>
                                                    </div>
                                                ) : (
                                                    "Continue with Password"
                                                )}
                                            </button>
                                        </form>

                                        {/* ---- DIVIDER ---- */}
                                        <div className="flex items-center gap-3 w-full my-5 text-gray-500 text-sm">
                                            <div className="flex-1 h-px bg-gray-700" />
                                            OR
                                            <div className="flex-1 h-px bg-gray-700" />
                                        </div>
                                    </div>

                                    {/* ---- PASSKEY + GOOGLE ---- */}
                                    <div className={`flex flex-col md:flex-row gap-3 w-full items-center justify-center ${anyLoading ? "pointer-events-none" : ""}`}>
                                        <button
                                            onClick={() => {
                                                if (anyLoading || !state.identifier) {
                                                    dispatch({
                                                        type: "SET",
                                                        key: "error",
                                                        value: "Enter your email or username first.",
                                                    });
                                                    toast.error("Enter your email or username first.");
                                                } else {
                                                    handlePasskey();
                                                }
                                            }}
                                            data-tooltip-id={`${!state.identifier ? "no-data-passkey-tooltip" : ""}`}
                                            aria-busy={state.loading.passkey}
                                            className={`w-full py-2.5 rounded-lg border border-gray-600 flex items-center justify-center text-white hover:bg-white/5 disabled:opacity-50 ${!state.identifier ? "cursor-not-allowed" : ""}`}
                                        >
                                            {state.loading.passkey ? (
                                                <div className="text-xs flex flex-row items-center gap-x-2">
                                                    <Spinner />
                                                    <span>Continuing with Passkey…</span>
                                                </div>
                                            ) : (
                                                <div className="flex flex-row items-center gap-x-2">
                                                    <Fingerprint size={16} />
                                                    <span>Continue with Passkey</span>
                                                </div>
                                            )}
                                            <Tooltip id="no-data-passkey-tooltip" place="top" effect="solid" className="bg-gray-700 text-white text-xs px-2 py-1 rounded">
                                                <p className="text-center">Enter your email or username first to use Passkey login.</p>
                                            </Tooltip>
                                        </button>

                                        <button
                                            onClick={handleGoogleLogin}
                                            className={`w-full gap-x-2 py-2.5 rounded-lg border border-gray-600 flex items-center justify-center text-white hover:bg-white/5 disabled:opacity-50 ${anyLoading ? "cursor-not-allowed" : ""
                                                }`}
                                            disabled={anyLoading}
                                            aria-busy={state.loading.oauth || isLoggingIn}
                                        >
                                            {anyLoading || state.loading.oauth || isLoggingIn ? (
                                                <div className="text-xs flex flex-row items-center gap-x-2">
                                                    <Spinner />
                                                    <span>Continuing with Google...</span>
                                                </div>
                                            ) : (
                                                <div className="flex flex-row items-center gap-x-2">
                                                    <svg version="1.1" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" xmlnsXlink="http://www.w3.org/1999/xlink" className="block w-5" aria-hidden="true">
                                                        <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"></path>
                                                        <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"></path>
                                                        <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"></path>
                                                        <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"></path>
                                                        <path fill="none" d="M0 0h48v48H0z"></path>
                                                    </svg>
                                                    <span>Continue with Google</span>
                                                </div>
                                            )}
                                        </button>
                                    </div>
                                </div>
                            ) : (
                                <form
                                    onSubmit={handleVerifyOtp}
                                    className="w-full flex pt-4 border-t justify-center border-gray-700"
                                >
                                    <div className="w-fit space-y-3">
                                        <p className="text-sm text-gray-400 text-center">
                                            Enter the code sent to{" "}
                                            <strong className="text-white">
                                                {state.maskedEmail || state.oauthEmail || "your email"}
                                            </strong>
                                        </p>

                                        <input
                                            type="text"
                                            placeholder="6-digit code"
                                            value={state.otp}
                                            onChange={(e) =>
                                                dispatch({
                                                    type: "SET",
                                                    key: "otp",
                                                    value: e.target.value,
                                                })
                                            }
                                            maxLength={6}
                                            disabled={anyLoading}
                                            className="w-full px-4 py-2.5 text-center tracking-widest rounded-lg bg-neutral-900 border border-gray-700 text-white disabled:opacity-50"
                                            inputMode="numeric"
                                            aria-label="OTP code"
                                        />

                                        <button
                                            type="submit"
                                            disabled={anyLoading}
                                            aria-busy={state.loading.otp}
                                            className={`w-full py-2.5 rounded-lg flex items-center justify-center ${anyLoading
                                                ? "bg-orange-600/70 cursor-not-allowed"
                                                : "bg-orange-600 hover:bg-orange-500"
                                                } text-white`}
                                        >
                                            {state.loading.otp ? (
                                                <div className="text-xs flex flex-row items-center gap-x-2">
                                                    <Spinner />
                                                    <span>Verifying…</span>
                                                </div>
                                            ) : (
                                                "Verify & Continue"
                                            )}
                                        </button>
                                    </div>
                                </form>
                            )}

                            {/* ---- FOOTER ---- */}
                            <div className="pt-4 border-t border-gray-700 space-y-3">
                                <p className="text-sm text-gray-400 text-center">
                                    Don&apos;t have an account?{" "}
                                    <a
                                        href="/register"
                                        className="text-orange-400 hover:underline"
                                        onClick={() => {setIsLoading(true);}}
                                    >
                                        Sign up
                                    </a>
                                </p>

                                <p className="text-sm text-gray-400 text-center">
                                    Reset Form{" "}
                                    {/* FIX 5: was passing an object `{ clearOAuth: true }` to a
                                        function that expects a boolean - now passes `true` correctly */}
                                    <button
                                        onClick={() => resetLoginState(true)}
                                        className="text-orange-400 hover:underline"
                                    >
                                        here
                                    </button>
                                </p>
                            </div>
                        </div>
                    </>
                )}
            </div>

            {/* OAuth needs-registration modal */}
            <Modal
                isOpen={needsReg}
                lock
                type="warning"
                title="No account found"
                description={`We couldn't find an account for ${state.oauthEmail || "this email"}. What would you like to do?`}
                primaryAction={{
                    label: "Register a new account",
                    onClick: registerHandler,
                }}
                secondaryAction={{
                    label: "Cancel",
                    onClick: cancelRegisterHandler,
                }}
            >
                <div className="p-3 text-sm text-zinc-300">
                    <p className="mb-2">
                        Registering will create a new site account for <strong>{state.oauthEmail || "this email"}</strong> with OAuth login.
                    </p>
                    <p className="mb-2">
                        You can add a password login later from account settings if you want - not mandatory.
                    </p>
                </div>
            </Modal>

            {/* Popup permission prompt */}
            <Modal
                isOpen={showPopupPrompt}
                lock
                type="info"
                title="Allow popup window?"
                description="Signing in with Google opens a small popup window. Allow popups for this site to continue."
                primaryAction={{
                    label: "Allow & Continue",
                    onClick: () => {
                        localStorage.setItem("allowPopup", "true");
                        setPopupPermissionAsked(true);
                        setShowPopupPrompt(false);
                        _doGoogleLogin();
                    },
                }}
                secondaryAction={{
                    label: "Cancel",
                    onClick: () => setShowPopupPrompt(false),
                }}
            />
        </div>
    );
}

export default Login;