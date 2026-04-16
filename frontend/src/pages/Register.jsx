
import { useEffect, useRef, useReducer, useCallback, useState, useMemo } from "react";
import Logo from "../features/Logo";
import backendUrlV1 from "../urls/backendUrl";
import { useUsernameAvailabilitySimple } from "../features/userNameAvailability";
import Modal from "../components/popUpModal";
import { supabase } from "../lib/supabase";

import { Info } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useContextManager } from "../features/ContextProvider";
import PolicyContentRenderer from "../features/PolicyContentRenderer";

/* --------------------------
   Utilities
   -------------------------- */
function validatePassword(pwd) {
  if (pwd.length < 8) return "Password must be at least 8 characters.";
  if (pwd.length > 72) return "Password is too long.";
  if (!/[A-Za-z]/.test(pwd)) return "Password must contain at least one letter.";
  if (!/\d/.test(pwd)) return "Password must contain at least one number.";
  return null;
}

/* --------------------------
   Constants & initialState
   -------------------------- */
const LEGAL_BASE = `/api/legal`;
const REGISTER_BASE = `${backendUrlV1}/auth/registration`;
const initialState = {
  isBootstrapping: true,
  stage: "email", 
  email: "",
  challengeId: "",
  otp: "",
  otpError: "",
  resendCooldown: 0,
  password: "",
  confirmPassword: "",
  showPassword: false,
  showConfirmPassword: false,
  userName: "",
  showConsentModal: false,
  policiesMeta: [],
  policiesFull: {},
  policyLoadingKey: null,
  consentLoading: false,
  consentError: "",
  emailUnacceptable: false,
  whyEmailUnacceptable: "",
  showEmailBlockedModal: false,
  loading: {
    requestOtp: false,
    resendOtp: false,
    verifyOtp: false,
    policyMeta: false,
    policyFile: false,
    preRegisterConsent: false,
    register: false,
  },
  error: "",
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
      return { ...initialState };
    default:
      return state;
  }
}

function LoadingSkeleton() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="w-full sm:max-w-md max-w-[88%] rounded-2xl bg-white/5 backdrop-blur border border-white/10 shadow-xl p-8 animate-pulse">
        {/* Logo placeholder */}
        <div className="flex justify-center mb-6">
          <div className="h-8 w-36 bg-white/10 rounded-lg" />
        </div>

        {/* Title + subtitle */}
        <div className="h-6 w-3/4 bg-white/10 rounded-md mx-auto mb-2" />
        <div className="h-4 w-1/2 bg-white/10 rounded-md mx-auto mb-8" />

        {/* Input fields */}
        <div className="space-y-4">
          <div className="h-11 w-full bg-white/10 rounded-lg" />
          <div className="h-11 w-full bg-white/10 rounded-lg" />
          <div className="h-11 w-full bg-white/10 rounded-lg" />
        </div>

        {/* Button */}
        <div className="h-11 w-full bg-orange-500/20 rounded-lg mt-4" />

        {/* Footer link */}
        <div className="h-4 w-2/3 bg-white/10 rounded-md mx-auto mt-6" />
      </div>
    </div>
  );
}

/* --------------------------
   Register component
   -------------------------- */
export default function Register() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const stateRef = useRef(state);
  stateRef.current = state; 
  const navigate = useNavigate();
  const { setIsLoading } = useContextManager();

  
  const flowId = new URLSearchParams(window.location.search).get("req_id");
  const isOAuth = Boolean(new URLSearchParams(window.location.search).get("oauth") === "1") || Boolean(flowId);

  
  const isMountedRef = useRef(true);
  const otpRequestControllerRef = useRef(null);
  const resendControllerRef = useRef(null);
  const verifyControllerRef = useRef(null);
  const policyMetaControllerRef = useRef(null);
  const policyFileControllersRef = useRef({}); 
  const registerControllerRef = useRef(null);
  const cooldownTimerRef = useRef(null);
  const handledFlowRef = useRef(false);

  
  const anyLoading = useMemo(() => {
    const l = state.loading;
    return (
      l.requestOtp ||
      l.resendOtp ||
      l.verifyOtp ||
      l.policyMeta ||
      l.policyFile ||
      l.preRegisterConsent ||
      l.register
    );
  }, [state.loading]);

  
  useEffect(() => {
    setIsLoading(anyLoading);
  }, [anyLoading, setIsLoading]);

  
  useEffect(() => {
    return () => {
      isMountedRef.current = false;
      
      [otpRequestControllerRef, resendControllerRef, verifyControllerRef, policyMetaControllerRef, registerControllerRef].forEach(
        (r) => {
          try {
            r.current?.abort?.();
          } catch { }
        }
      );
      
      Object.values(policyFileControllersRef.current || {}).forEach((c) => {
        try {
          c.abort();
        } catch { }
      });
      if (cooldownTimerRef.current) {
        clearInterval(cooldownTimerRef.current);
      }
    };
  }, []);

  /* --------------------------------
     Cooldown timer (stable, accurate)
     -------------------------------- */
  useEffect(() => {
    if (cooldownTimerRef.current) {
      clearInterval(cooldownTimerRef.current);
      cooldownTimerRef.current = null;
    }
    if (state.resendCooldown > 0) {
      cooldownTimerRef.current = setInterval(() => {
        
        const current = stateRef.current.resendCooldown || 0;
        if (current <= 1) {
          clearInterval(cooldownTimerRef.current);
          cooldownTimerRef.current = null;
          dispatch({ type: "SET", key: "resendCooldown", value: 0 });
          return;
        }
        dispatch({ type: "SET", key: "resendCooldown", value: current - 1 });
      }, 1000);
    }
    return () => {
      if (cooldownTimerRef.current) {
        clearInterval(cooldownTimerRef.current);
        cooldownTimerRef.current = null;
      }
    };
  }, [state.resendCooldown]);

  /* --------------------------------
     Username availability hook
     -------------------------------- */
  const usernameStatus = useUsernameAvailabilitySimple(state.userName, Boolean(state.userName));
  const isUsernameValid = !state.userName || usernameStatus === "available";

  /* --------------------------------
     Password strength helpers
     -------------------------------- */
  const passwordRules = useMemo(() => {
    return {
      length: state.password.length >= 8,
      upper: /[A-Z]/.test(state.password),
      lower: /[a-z]/.test(state.password),
      number: /[0-9]/.test(state.password),
      match: state.password && state.password === state.confirmPassword,
    };
  }, [state.password, state.confirmPassword]);

  const isPasswordStrong = useMemo(() => Object.values(passwordRules).slice(0, 4).every(Boolean), [passwordRules]);
  const strengthScore = useMemo(() => [passwordRules.length, passwordRules.upper, passwordRules.lower, passwordRules.number].filter(Boolean).length, [passwordRules]);
  const strengthPct = (strengthScore / 4) * 100;

  /* --------------------------------
     Helper: safe dispatch (avoid updates after unmount)
     -------------------------------- */
  function safeDispatch(action) {
    if (isMountedRef.current) dispatch(action);
  }

  /* --------------------------------
     Request OTP
     -------------------------------- */
  const handleRequestOtp = useCallback(
    async (e) => {
      e?.preventDefault();
      safeDispatch({ type: "SET", key: "error", value: "" });
      if (!state.email) {
        safeDispatch({ type: "SET", key: "error", value: "Enter an email" });
        return;
      }

      
      try {
        otpRequestControllerRef.current?.abort();
      } catch { }
      const ctrl = new AbortController();
      otpRequestControllerRef.current = ctrl;

      safeDispatch({ type: "SET_LOADING", payload: { requestOtp: true } });

      try {
        const fingerprint = window.localStorage.getItem("device_fp") || null;
        const payload = { email: state.email, fingerprint };
        const res = await fetch(`${REGISTER_BASE}/request-otp`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
          signal: ctrl.signal,
        });

        const body = await res.json().catch(() => ({}));
        if (!res.ok) {
          if (body.status_code === 406) {
            safeDispatch({ type: "SET", key: "whyEmailUnacceptable", value: body.message || "This email domain is not allowed." });
            safeDispatch({ type: "SET", key: "emailUnacceptable", value: true });
          }
          throw new Error(body.message || "Failed to request OTP");
        }

        safeDispatch({
          type: "SET_MANY",
          payload: {
            challengeId: body.challenge_id,
            resendCooldown: body.resend_cooldown || 30,
            stage: "otp",
            whyEmailUnacceptable: "",
            emailUnacceptable: false,
          },
        });
      } catch (err) {
        if (err?.name !== "AbortError") {
          safeDispatch({ type: "SET", key: "error", value: err.message || String(err) });
        }
      } finally {
        safeDispatch({ type: "SET_LOADING", payload: { requestOtp: false } });
        otpRequestControllerRef.current = null;
      }
    },
    [state.email]
  );

  /* --------------------------------
     Resend OTP
     -------------------------------- */
  const handleResendOtp = useCallback(async () => {
    if (state.resendCooldown > 0) return;

    try {
      resendControllerRef.current?.abort();
    } catch { }
    const ctrl = new AbortController();
    resendControllerRef.current = ctrl;

    safeDispatch({ type: "SET_LOADING", payload: { resendOtp: true } });
    safeDispatch({ type: "SET", key: "otpError", value: "" });

    try {
      const res = await fetch(`${REGISTER_BASE}/resend-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: state.email, challenge_id: state.challengeId }),
        signal: ctrl.signal,
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        if (body.status_code === 406) {
          safeDispatch({ type: "SET", key: "whyEmailUnacceptable", value: body.message || "This email domain is not allowed." });
          safeDispatch({ type: "SET", key: "emailUnacceptable", value: true });
        }
        throw new Error(body.detail || "Failed to resend OTP");
      }
      safeDispatch({ type: "SET", key: "resendCooldown", value: body.resend_cooldown || 30 });
    } catch (err) {
      if (err?.name !== "AbortError") {
        safeDispatch({ type: "SET", key: "otpError", value: err.message || String(err) });
      }
    } finally {
      safeDispatch({ type: "SET_LOADING", payload: { resendOtp: false } });
      resendControllerRef.current = null;
    }
  }, [state.email, state.challengeId]);

  /* --------------------------------
     Verify OTP
     -------------------------------- */
  const handleVerifyOtp = useCallback(
    async (e) => {
      e?.preventDefault();
      safeDispatch({ type: "SET", key: "otpError", value: "" });

      if (!state.otp || !state.challengeId) {
        safeDispatch({ type: "SET", key: "otpError", value: "Enter the code" });
        return;
      }

      try {
        verifyControllerRef.current?.abort();
      } catch { }
      const ctrl = new AbortController();
      verifyControllerRef.current = ctrl;

      safeDispatch({ type: "SET_LOADING", payload: { verifyOtp: true } });

      try {
        const res = await fetch(`${REGISTER_BASE}/verify-otp`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: state.email, challenge_id: state.challengeId, code: state.otp }),
          signal: ctrl.signal,
        });
        const resBody = await res.json().catch(() => null);
        if (!res.ok) {
          throw new Error((resBody && resBody.detail) || `OTP verification failed (status ${res.status})`);
        }
        safeDispatch({ type: "SET", key: "stage", value: "consent" });
        await handlePolicyStep();
      } catch (err) {
        if (err?.name !== "AbortError") {
          safeDispatch({ type: "SET", key: "otpError", value: err.message || String(err) });
        }
      } finally {
        safeDispatch({ type: "SET_LOADING", payload: { verifyOtp: false } });
        verifyControllerRef.current = null;
      }
    },
    
    
    
    [state.otp, state.challengeId, state.email]
  );

  /* --------------------------------
     Load policy metadata + show consent modal
     -------------------------------- */
  const handlePolicyStep = useCallback(async () => {
    
    try {
      policyMetaControllerRef.current?.abort();
    } catch { }
    const ctrl = new AbortController();
    policyMetaControllerRef.current = ctrl;

    safeDispatch({ type: "SET_LOADING", payload: { policyMeta: true } });
    try {
      
      let metaRes = await fetch(`${LEGAL_BASE}/active?meta_only=1`, { cache: "no-store", signal: ctrl.signal });
      let metaBody = await metaRes.json().catch(() => null);

      if (!metaRes.ok || !metaBody) {
        
        metaRes = await fetch(`${LEGAL_BASE}/active`, { cache: "no-store", signal: ctrl.signal });
        metaBody = await metaRes.json().catch(() => null);
        if (!metaRes.ok) throw new Error("Failed to load policies (both meta and fallback failed)");
      }

      
      let normals = [];
      if (!metaBody) {
        normals = [];
      } else if (Array.isArray(metaBody)) {
        normals = metaBody;
      } else if (Array.isArray(metaBody.policies)) {
        normals = metaBody.policies;
      } else if (Array.isArray(metaBody.data)) {
        normals = metaBody.data;
      } else {
        const arr = Object.values(metaBody).find((v) => Array.isArray(v));
        normals = arr || [];
      }

      safeDispatch({ type: "SET_MANY", payload: { policiesMeta: normals, showConsentModal: true, stage: "consent" } });
    } catch (err) {
      if (err?.name !== "AbortError") {
        safeDispatch({ type: "SET", key: "consentError", value: err.message || String(err) });
        throw err; 
      }
    } finally {
      safeDispatch({ type: "SET_LOADING", payload: { policyMeta: false } });
      policyMetaControllerRef.current = null;
    }
  }, []);

  /* --------------------------------
     Load full policy file (html or markdown)
     - caches policyFileControllers
     -------------------------------- */
  async function loadPolicyFull(key) {
    
    if (state.policiesFull[key]) {
      const copy = { ...state.policiesFull };
      delete copy[key];
      safeDispatch({ type: "SET", key: "policiesFull", value: copy });
      return;
    }

    const meta = state.policiesMeta.find((p) => p.key === key || p.id === key || p.slug === key);

    
    async function tryUrls(urls) {
      let body = null;
      for (const url of urls) {
        try {
          const res = await fetch(url);
          body = await res.json().catch(() => null);
          if (res.ok && body) return { body, ok: true, res };
        } catch (err) {
          
        }
      }
      return { body: null, ok: false };
    }

    safeDispatch({ type: "SET", key: "policyLoadingKey", value: key });
    safeDispatch({ type: "SET_LOADING", payload: { policyFile: true } });

    try {
      if (!meta) {
        
        const tryUrlsList = [
          `${LEGAL_BASE}/${encodeURIComponent(key)}/versions`,
          `${LEGAL_BASE}/${encodeURIComponent(key)}`,
          `${LEGAL_BASE}/${encodeURIComponent(key)}/latest`,
        ];
        const attempt = await tryUrls(tryUrlsList);
        if (!attempt.ok || !attempt.body) throw new Error("Failed to load policy (all endpoints failed)");

        const body = attempt.body;
        if (Array.isArray(body.versions) && body.versions.length) {
          safeDispatch({ type: "SET", key: "policiesFull", value: { ...state.policiesFull, [key]: body.versions[0] } });
          return;
        }
        if (Array.isArray(body) && body.length) {
          safeDispatch({ type: "SET", key: "policiesFull", value: { ...state.policiesFull, [key]: body[0] } });
          return;
        }
        safeDispatch({ type: "SET", key: "policiesFull", value: { ...state.policiesFull, [key]: body } });
        return;
      }

      if (!meta.file_url) {
        safeDispatch({ type: "SET", key: "consentError", value: "Policy metadata missing file_url" });
        return;
      }

      const fileUrlAbsolute = ((fileUrl) => {
        if (!fileUrl) return null;
        if (/^https?:\/\//i.test(fileUrl)) return fileUrl;
        return fileUrl.startsWith("/") ? fileUrl : `/${fileUrl}`;
      })(meta.file_url);

      
      try {
        policyFileControllersRef.current[key]?.abort();
      } catch { }
      const ctrl = new AbortController();
      policyFileControllersRef.current[key] = ctrl;

      const res = await fetch(fileUrlAbsolute, { signal: ctrl.signal });
      if (!res.ok) {
        throw new Error(`Failed to fetch policy file: ${res.status}`);
      }
      const text = await res.text();
      const fmt = (meta.file_format || meta.format || "markdown").toLowerCase();
      if (fmt === "html") {
        safeDispatch({
          type: "SET",
          key: "policiesFull",
          value: { ...state.policiesFull, [key]: { html: text, text_hash: meta.text_hash, file_url: meta.file_url, file_format: fmt } },
        });
      } else {
        safeDispatch({
          type: "SET",
          key: "policiesFull",
          value: { ...state.policiesFull, [key]: { markdown: text, text_hash: meta.text_hash, file_url: meta.file_url, file_format: fmt } },
        });
      }
    } catch (err) {
      if (err?.name !== "AbortError") {
        safeDispatch({ type: "SET", key: "consentError", value: err.message || String(err) });
      }
    } finally {
      safeDispatch({ type: "SET", key: "policyLoadingKey", value: null });
      safeDispatch({ type: "SET_LOADING", payload: { policyFile: false } });
      delete policyFileControllersRef.current[key];
    }
  }

  /* --------------------------------
    Consent pre-register
  -------------------------------- */
  const handlePreRegisterConsent = useCallback(async () => {
    if (anyLoading) return;
    safeDispatch({ type: "SET_LOADING", payload: { preRegisterConsent: true } });
    safeDispatch({ type: "SET", key: "consentError", value: "" });

    try {
      if (!state.challengeId) throw new Error("Missing registration challenge id");
      const agreements = state.policiesMeta.map((p) => ({
        key: p.key,
        version: p.version,
        text_hash: p.text_hash,
      }));

      const payload = {
        challenge_id: state.challengeId,
        agreements,
        meta: { flow: "registration", ui: "modal_v1", locale: "en" },
      };

      const res = await fetch(`${LEGAL_BASE}/consent/pre-register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(body.detail || "Failed to record consent");
      }

      safeDispatch({ type: "SET", key: "showConsentModal", value: false });
      if (isOAuth) {
        await performRegistration();
      } else {
        safeDispatch({ type: "SET", key: "stage", value: "final" });
      }
    } catch (err) {
      if (err?.name !== "AbortError") {
        safeDispatch({ type: "SET", key: "consentError", value: err.message || String(err) });
      }
    } finally {
      safeDispatch({ type: "SET_LOADING", payload: { preRegisterConsent: false } });
    }
  }, [isOAuth, state.challengeId, state.policiesMeta, anyLoading]);

  /* --------------------------------
     Perform registration (normal or OAuth flow)
     - abortable
     -------------------------------- */
  async function performRegistration() {
    try {
      registerControllerRef.current?.abort();
    } catch { }
    const ctrl = new AbortController();
    registerControllerRef.current = ctrl;

    safeDispatch({ type: "SET_LOADING", payload: { register: true } });
    safeDispatch({ type: "SET", key: "error", value: "" });

    try {
      const consents = state.policiesMeta.map((p) => ({
        agreement_key: p.key,
        agreement_version: p.version,
        text_hash: p.text_hash,
      }));

      let res;
      if (isOAuth && flowId) {
        safeDispatch({ type: "SET", key: "stage", value: "oauthfinal" });

        res = await fetch(`${backendUrlV1}/auth/oauth/registration/register`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          credentials: "include",
          body: JSON.stringify({
            username: state.userName || null,
            challenge_id: state.challengeId,
            consents,
            age_verified: true,
            age_verification_method: "self_asserted",
            req_id: flowId,
          }),
          signal: ctrl.signal,
        });
      } else {
        res = await fetch(`${REGISTER_BASE}/register`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({
            email: state.email,
            password: state.password,
            username: state.userName || null,
            challenge_id: state.challengeId,
            consents,
            age_verified: true,
            age_verification_method: "self_asserted",
          }),
          signal: ctrl.signal,
        });
      }

      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(body.detail || "Registration failed");
      }

      if (isOAuth && flowId && body.auto_logged_in) {
        
        window.location.replace(localStorage.getItem("redirectAfterLogin") || "/");
        localStorage.removeItem("redirectAfterLogin");
      } else if (body.activation_required) {
        safeDispatch({ type: "SET", key: "stage", value: "activation_sent" });
      } else {
        navigate("/login?registered=1");
      }
    } catch (err) {
      if (err?.name !== "AbortError") {
        safeDispatch({ type: "SET", key: "error", value: err.message || String(err) });
      }
    } finally {
      safeDispatch({ type: "SET_LOADING", payload: { register: false } });
      registerControllerRef.current = null;
    }
  }

  /* --------------------------------
     Register handler (final step)
     -------------------------------- */
  const handleRegister = useCallback(
    async (e) => {
      e?.preventDefault();

      if (!isOAuth) {
        const pwdErr = validatePassword(state.password);
        if (pwdErr) {
          safeDispatch({ type: "SET", key: "error", value: pwdErr });
          return;
        }
        if (state.password !== state.confirmPassword) {
          safeDispatch({ type: "SET", key: "error", value: "Passwords do not match." });
          return;
        }
        if (!isUsernameValid) {
          safeDispatch({ type: "SET", key: "error", value: "Choose a different username." });
          return;
        }
      }

      await performRegistration();
    },
    [isOAuth, state.password, state.confirmPassword, isUsernameValid, state.userName]
  );

  const handleGoogleSignUp = useCallback(async () => {
    safeDispatch({ type: "SET", key: "error", value: "" });
    safeDispatch({ type: "SET_LOADING", payload: { requestOtp: true } });

    try {
      const res = await fetch(`${backendUrlV1}/auth/oauth/start`, {
        method: "POST",
        credentials: "include",
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok || !body.req_id) {
        throw new Error(body.detail || "Failed to start OAuth flow");
      }

      const fid = body.req_id;
      
      const redirectTo = `${window.location.origin}/register?req_id=${encodeURIComponent(fid)}`;

      const { data, error } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo,
          queryParams: { prompt: "select_account" },
          skipBrowserRedirect: true,
        },
      });

      if (error || !data?.url) throw new Error(error?.message || "Failed to get OAuth URL");

      window.location.href = data.url;
    } catch (err) {
      safeDispatch({ type: "SET", key: "error", value: err.message || "OAuth initiation failed" });
    } finally {
      safeDispatch({ type: "SET_LOADING", payload: { requestOtp: false } });
    }
  }, []);

  /* --------------------------------
     Unified req_id handling (single effect)
     - read challenge and email from server flow store
     - then open consent step
     -------------------------------- */
  useEffect(() => {
    if (!flowId) {
      safeDispatch({ type: "SET", key: "isBootstrapping", value: false });
      return;
    }
    if (handledFlowRef.current) return;
    handledFlowRef.current = true;

    (async () => {
      try {
        const { data } = await supabase.auth.getSession();
        const session = data?.session;
        const access_token =
          session?.access_token ?? session?.accessToken ?? session?.provider_token ?? null;

        if (access_token) {
          const res = await fetch(
            `${backendUrlV1}/auth/oauth/login?req_id=${encodeURIComponent(flowId)}`,
            {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${access_token}`,
              },
              credentials: "include",
              body: JSON.stringify({ fingerprint: null }),
            }
          );
        } else {
          
          navigate("/register");
          return;
        }

        
        const res = await fetch(
          `${backendUrlV1}/auth/oauth/flow/${encodeURIComponent(flowId)}`,
          { credentials: "include" }
        );
        if (!res.ok) { navigate("/register"); return; }
        const body = await res.json().catch(() => null);
        if (!body) { navigate("/register"); return; }

        
        if (body.status === "complete" && body.ok) {
          window.location.replace(localStorage.getItem("redirectAfterLogin") || "/");
          localStorage.removeItem("redirectAfterLogin");
          return;
        }

        
        if (body.status === "otp_required") {
          navigate(`/login?req_id=${encodeURIComponent(flowId)}`);
          return;
        }

        
        if (body.status === "needs_registration") {
          if (body.email) safeDispatch({ type: "SET", key: "email", value: body.email });
          if (body.challenge_id) safeDispatch({ type: "SET", key: "challengeId", value: body.challenge_id });
          safeDispatch({ type: "SET", key: "stage", value: "consent" });
          await handlePolicyStep();
          return;
        }

        
        navigate("/register");

      } catch (err) {
        console.warn("OAuth register bootstrap error:", err);
        navigate("/register");
      } finally {
        safeDispatch({ type: "SET", key: "isBootstrapping", value: false });
      }
    })();
    
  }, [flowId, navigate]);

  if (state.isBootstrapping) return <LoadingSkeleton />;

  /* --------------------------------
     Render
     -------------------------------- */
  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="w-full sm:max-w-md max-w-[88%] rounded-2xl bg-white/5 backdrop-blur border border-white/10 shadow-xl p-8">
        <div className="flex justify-center mb-6"><Logo width={140} /></div>
        <h1 className="text-xl font-semibold text-white text-center">Create your Forkit account</h1>
        <p className="text-sm text-gray-400 text-center mt-1">Join the community. Evolve recipes together.</p>

        {!isOAuth && (
          <>
            {state.error && (
              <div className="mt-4 text-sm text-red-400 text-center">{state.error}</div>
            )}
            {state.emailUnacceptable && (
              <div className="mt-2 text-sm text-red-400 text-center space-y-1">
                <div>This email can't be used. Please try another address.</div>

                <button
                  type="button"
                  onClick={() => safeDispatch({ type: "SET", key: "showEmailBlockedModal", value: true })}
                  className="inline-flex items-center gap-1 text-xs text-orange-400 hover:text-orange-300 underline underline-offset-2 transition"
                >
                  Why is this blocked?
                  <Info className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {state.stage === "email" && (
              <form onSubmit={handleRequestOtp} className="space-y-4 mt-6" autoComplete="on">
                <label htmlFor="register-email" className="sr-only">Email</label>
                <input
                  id="register-email"
                  type="email"
                  name="email"
                  autoComplete="email"
                  placeholder="Email"
                  value={state.email}
                  onChange={(e) => safeDispatch({ type: "SET", key: "email", value: e.target.value })}
                  required
                  className="w-full px-4 py-2.5 rounded-lg bg-neutral-900 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-orange-500"
                />
                <button
                  type="submit"
                  disabled={state.loading.requestOtp}
                  className="w-full py-2.5 rounded-lg bg-orange-600 hover:bg-orange-500 text-white font-medium transition disabled:opacity-50"
                >
                  {state.loading.requestOtp ? "Requesting…" : "Request OTP"}
                </button>
                {/* ---- DIVIDER ---- */}
                <div className="flex items-center gap-3 w-full my-1 text-gray-500 text-sm">
                  <div className="flex-1 h-px bg-gray-700" />
                  OR
                  <div className="flex-1 h-px bg-gray-700" />
                </div>

                {/* ---- GOOGLE SIGN UP ---- */}
                <button
                  type="button"
                  disabled={state.loading.requestOtp}
                  onClick={handleGoogleSignUp}
                  className="w-full gap-x-2 py-2.5 rounded-lg border border-gray-600 flex items-center justify-center text-white hover:bg-white/5 disabled:opacity-50"
                >
                  <svg version="1.1" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" className="block w-5" aria-hidden="true">
                    <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
                    <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
                    <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
                    <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
                    <path fill="none" d="M0 0h48v48H0z" />
                  </svg>
                  <span>Sign up with Google</span>
                </button>
                <div className="mt-6 text-sm text-center text-gray-400">
                  Already have an account? <a href="/login" className="text-orange-400 hover:underline">Log in</a>
                </div>
              </form>
            )}

            {state.stage === "otp" && (
              <form onSubmit={handleVerifyOtp} className="space-y-4 mt-6">
                <div className="text-sm text-gray-300 text-center">We sent a code to <strong>{state.email}</strong></div>

                <label htmlFor="otp" className="sr-only">OTP</label>
                <input
                  id="otp"
                  type="text"
                  inputMode="numeric"
                  placeholder="Enter 6-digit code"
                  value={state.otp}
                  onChange={(e) =>
                    safeDispatch({ type: "SET", key: "otp", value: e.target.value.replace(/\D/g, "").slice(0, 6) })
                  }
                  required
                  className="w-full px-4 py-2.5 rounded-lg bg-neutral-900 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-orange-500"
                />
                {state.otpError && <div className="text-sm text-red-400 text-center">{state.otpError}</div>}

                <div className="flex gap-2">
                  <button
                    type="submit"
                    disabled={state.loading.verifyOtp}
                    className="flex-1 py-2.5 rounded-lg bg-orange-600 hover:bg-orange-500 text-white font-medium transition disabled:opacity-50"
                  >
                    {state.loading.verifyOtp ? "Verifying…" : "Verify"}
                  </button>
                  <button
                    type="button"
                    onClick={handleResendOtp}
                    disabled={state.resendCooldown > 0 || state.loading.resendOtp}
                    className="px-4 py-2.5 rounded-lg bg-neutral-800 border border-gray-700 text-white text-sm disabled:opacity-50"
                  >
                    {state.resendCooldown > 0 ? `Resend (${state.resendCooldown}s)` : (state.loading.resendOtp ? "Resending…" : "Resend")}
                  </button>
                </div>
                <div className="mt-6 text-sm text-center text-gray-400">Didn't get a code? Wait between resends. Too many bad attempts may block the email.</div>
              </form>
            )}

            {state.stage === "final" && (
              <form onSubmit={handleRegister} className="space-y-4 mt-6" autoComplete="on">
                <div className="text-sm text-green-300 text-center">Email verified – finish set up</div>

                <div>
                  <label htmlFor="username" className="sr-only">Username</label>
                  <input
                    id="username"
                    name="username"
                    type="text"
                    autoComplete="username"
                    placeholder="Username (optional)"
                    value={state.userName}
                    onChange={(e) => safeDispatch({ type: "SET", key: "userName", value: e.target.value })}
                    className="w-full px-4 py-2.5 rounded-lg bg-neutral-900 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-orange-500"
                  />
                  <div className="mt-1 h-4 text-xs">
                    {!state.userName && <span className="text-neutral-500">Leave empty to get an auto-generated username</span>}
                    {state.userName && usernameStatus === "checking" && <span className="text-neutral-400">Checking availability…</span>}
                    {state.userName && usernameStatus === "available" && <span className="text-green-400">Available ✓</span>}
                    {state.userName && usernameStatus === "taken" && <span className="text-red-400">Already taken</span>}
                    {state.userName && usernameStatus === "invalid" && <span className="text-yellow-400">3–30 chars, letters, numbers, underscore</span>}
                  </div>
                </div>

                <div className="relative">
                  <label htmlFor="password" className="sr-only">Password</label>
                  <input
                    id="password"
                    name="password"
                    type={state.showPassword ? "text" : "password"}
                    autoComplete="new-password"
                    placeholder="Password"
                    value={state.password}
                    onChange={(e) => safeDispatch({ type: "SET", key: "password", value: e.target.value })}
                    required
                    className={`w-full px-4 py-2.5 pr-10 rounded-lg bg-neutral-900 border ${state.password ? (isPasswordStrong ? "border-green-500" : "border-red-500") : "border-gray-700"} text-white placeholder-gray-500 focus:outline-none`}
                  />
                  <button
                    type="button"
                    onClick={() => safeDispatch({ type: "SET", key: "showPassword", value: !state.showPassword })}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm"
                  >
                    {state.showPassword ? "Hide" : "Show"}
                  </button>
                </div>

                <div className="relative">
                  <label htmlFor="confirm-password" className="sr-only">Confirm password</label>
                  <input
                    id="confirm-password"
                    name="confirm-password"
                    type={state.showConfirmPassword ? "text" : "password"}
                    placeholder="Confirm password"
                    value={state.confirmPassword}
                    onChange={(e) => safeDispatch({ type: "SET", key: "confirmPassword", value: e.target.value })}
                    required
                    className={`w-full px-4 py-2.5 pr-10 rounded-lg bg-neutral-900 border ${state.confirmPassword ? (passwordRules.match ? "border-green-500" : "border-red-500") : "border-gray-700"} text-white placeholder-gray-500 focus:outline-none`}
                  />
                  <button
                    type="button"
                    onClick={() => safeDispatch({ type: "SET", key: "showConfirmPassword", value: !state.showConfirmPassword })}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm"
                  >
                    {state.showConfirmPassword ? "Hide" : "Show"}
                  </button>
                </div>

                <div className="text-xs text-neutral-400">Password strength</div>
                <div className="h-1 w-full bg-neutral-800 rounded overflow-hidden">
                  <div className="h-full bg-orange-500 transition-all duration-300" style={{ width: `${strengthPct}%` }} />
                </div>

                <div className="flex items-center flex-col text-xs space-y-1 mt-2">
                  <div className="flex w-full justify-between gap-2">
                    <div>
                      <div className={`flex items-center gap-2 transition-all duration-200 ${state.password ? (passwordRules.length ? "text-green-400 scale-[1.02]" : "text-red-400 scale-[1.02]") : "text-neutral-500"}`}>
                        <span className="w-4 text-center">{passwordRules.length ? "✓" : "•"}</span>
                        <span>At least 8 characters</span>
                      </div>
                      <div className={`flex items-center gap-2 transition-all duration-200 ${state.password ? (passwordRules.upper ? "text-green-400 scale-[1.02]" : "text-red-400 scale-[1.02]") : "text-neutral-500"}`}>
                        <span className="w-4 text-center">{passwordRules.upper ? "✓" : "•"}</span>
                        <span>One uppercase letter</span>
                      </div>
                    </div>
                    <div>
                      <div className={`flex items-center gap-2 transition-all duration-200 ${state.password ? (passwordRules.lower ? "text-green-400 scale-[1.02]" : "text-red-400 scale-[1.02]") : "text-neutral-500"}`}>
                        <span className="w-4 text-center">{passwordRules.lower ? "✓" : "•"}</span>
                        <span>One lowercase letter</span>
                      </div>
                      <div className={`flex items-center gap-2 transition-all duration-200 ${state.password ? (passwordRules.number ? "text-green-400 scale-[1.02]" : "text-red-400 scale-[1.02]") : "text-neutral-500"}`}>
                        <span className="w-4 text-center">{passwordRules.number ? "✓" : "•"}</span>
                        <span>One number</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex w-full items-center">
                    <div className={`flex items-center gap-2 transition-all duration-200 ${state.password ? (passwordRules.match ? "text-green-400 scale-[1.02]" : "text-red-400 scale-[1.02]") : "text-neutral-500"}`}>
                      <span className="w-4 text-center">{passwordRules.match ? "✓" : "•"}</span>
                      <span>Passwords match</span>
                    </div>
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={state.loading.register || !isUsernameValid || !isPasswordStrong}
                  className="w-full py-2.5 rounded-lg bg-orange-600 hover:bg-orange-500 text-white font-medium transition disabled:opacity-50"
                >
                  {state.loading.register ? "Creating account…" : "Create account"}
                </button>
              </form>
            )}
          </>
        )}

        {state.stage === "consent" && (
          <div className="mt-6 text-center space-y-4">
            <div className="text-lg text-white font-semibold">Almost there...</div>
            <div className="text-sm text-gray-400 leading-relaxed">Before creating your account, we need you to review and accept our policies.</div>
          </div>
        )}

        {state.stage === "oauthfinal" && (
          <div className="w-full flex flex-col items-center justify-center py-10 space-y-4">
            <div className="h-8 w-8 border-4 border-gray-700 border-t-orange-500 rounded-full animate-spin" />
            <p className="text-sm text-gray-400">Finalizing OAuth login…</p>
          </div>
        )}

        {state.stage === "activation_sent" && (
          <div className="mt-6 text-center space-y-4">
            <div className="text-lg text-white font-semibold">Now, just one last step...</div>
            <div className="text-sm text-gray-400 leading-relaxed">We've sent an activation link to <strong>{state.email}</strong>.<br />Click the link to activate your account and you'll be logged in automatically.</div>
            <div className="text-xs text-neutral-500">The link is valid for 48 hours and can be used once.</div>
            <div className="pt-4 text-sm space-x-1">
              <span className="text-neutral-400">Already activated?</span>
              {isOAuth ? <a href="/login?registered=1" className="text-orange-400 hover:underline text-sm">Log in</a> : <a href="/login" className="text-orange-400 hover:underline text-sm">Log in</a>}
            </div>
          </div>
        )}
      </div>

      {/* Email blocked modal */}
      <Modal isOpen={state.showEmailBlockedModal} onClose={() => safeDispatch({ type: "SET", key: "showEmailBlockedModal", value: false })} title="This email address can't be used" type="warning">
        <div className="space-y-4 text-sm text-neutral-300 leading-relaxed">
          <p>{state.whyEmailUnacceptable || "We couldn't use this email address to create an account."}</p>

          <p className="text-neutral-400">To protect the platform and our community, we restrict sign-ups from certain email domains.</p>

          <div className="bg-neutral-900/60 border border-white/10 rounded-lg p-3 text-xs text-neutral-400">
            <strong className="block mb-1 text-neutral-200">This can happen if the email:</strong>
            <ul className="list-disc pl-4 space-y-1">
              <li>Is from a temporary or disposable email service</li>
              <li>Belongs to a domain with a history of abuse or spam</li>
            </ul>
          </div>

          <div className="bg-neutral-900/60 border border-white/10 rounded-lg p-3 text-xs text-neutral-400">
            <strong className="block mb-1 text-neutral-200">What you can do next:</strong>
            <ul className="list-disc pl-4 space-y-1">
              <li>Use a personal email (Gmail, Outlook, iCloud)</li>
              <li>Or use a verified work email address</li>
            </ul>
          </div>

          <button onClick={() => safeDispatch({ type: "SET", key: "showEmailBlockedModal", value: false })} className="w-full pt-2.5 pb-2 rounded-lg bg-orange-600 hover:bg-orange-500 text-white font-medium transition">Got it, I'll try another email</button>
        </div>
      </Modal>

      {/* Consent modal */}
      <Modal
        isOpen={state.showConsentModal}
        onClose={() => { safeDispatch({ type: "SET", key: "showConsentModal", value: false }); safeDispatch({ type: "SET", key: "stage", value: "consent" }); }}
        title="Before you continue"
        mode="consent"
        type="consent"
        description="You must read and accept all policies."
        requireScroll
        consents={state.policiesMeta.map(p => ({ id: p.key || p.id || p.slug, label: `${p.title || p.name || p.display_name || p.key} ${p.version ? `(${p.version})` : ""}`, required: true }))}
        primaryAction={{
          label: "I Agree",
          onClick: handlePreRegisterConsent
        }}
        secondaryAction={{
          label: "I Do Not Agree",
          onClick: () => {
            safeDispatch({ type: "SET", key: "consentError", value: "You must accept all policies." })
          }
        }}
        lock
      >
        {state.loading.policyMeta ? (
          <div className="space-y-3 animate-pulse">
            {[1, 2].map(i => (
              <div key={i} className="border border-white/10 rounded-lg p-3 space-y-2">
                <div className="h-4 w-1/2 bg-white/10 rounded" />
                <div className="h-3 w-1/3 bg-white/10 rounded" />
              </div>
            ))}
          </div>
        ) : (
          <div className="space-y-4">
            {state.policiesMeta.length === 0 && (
              <div className="text-sm text-neutral-400">No policies loaded. If this persists, check the Network tab for `{LEGAL_BASE}/active` response.</div>
            )}

            {state.policiesMeta.map(p => (
              <div key={p.key || p.id || p.slug} className="border border-white/10 rounded-lg p-3">
                <div className="flex justify-between items-start gap-3">
                  <div>
                    <div className="font-semibold">{p.title || p.name || p.display_name || p.key}</div>
                    {p.effective_at && <div className="text-xs text-neutral-400">Effective: {new Intl.DateTimeFormat("en-GB", { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(p.effective_at))}</div>}
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => loadPolicyFull(p.key || p.id || p.slug)}
                      className="text-xs text-orange-400"
                    >
                      {state.policiesFull[p.key] || state.policiesFull[p.id] ? "Hide" : (state.policyLoadingKey === (p.key || p.id || p.slug) ? "Loading…" : "Read")}
                    </button>
                  </div>
                </div>

                {<PolicyContentRenderer markdown={state.policiesFull[p.key] || state.policiesFull[p.id]} />}
              </div>
            ))}

          </div>
        )}
      </Modal>
    </div>
  );
}