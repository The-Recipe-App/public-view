// SecurityCenterExpanded.jsx
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import backendUrlV1 from "../../urls/backendUrl";
import Modal from "../popUpModal";
import {
    Fingerprint,
    Laptop,
    Plus,
    Info,
    PlayCircle,
    ShieldCheck,
    Lock,
    BookOpenText,
    User,
    CheckCircle,
    XCircle,
    Globe,
    Key,
} from "lucide-react";
import { ensure_unique_label, registerPasskey_1, registerPasskey_2 } from "../../features/auth/passkey";
import { Tooltip } from "react-tooltip";

/**
 * Responsive-ready SecurityCenterExpanded
 * - Full drop-in replacement of your original file
 * - Preserves all logic and behavior
 * - Adds a small useWindowSize hook and a few responsive/touch-size improvements
 * - Keeps existing modal flows, passkey flows, password flows and all handlers intact
 */

/* ------------------------- small responsive hook ------------------------- */
function useWindowSize() {
    const [size, setSize] = useState({
        width: typeof window !== "undefined" ? window.innerWidth : 1024,
        height: typeof window !== "undefined" ? window.innerHeight : 768,
    });

    useEffect(() => {
        function onResize() {
            setSize({ width: window.innerWidth, height: window.innerHeight });
        }
        window.addEventListener("resize", onResize);
        return () => window.removeEventListener("resize", onResize);
    }, []);

    return size;
}

/* ------------------------- helpers ------------------------- */
function validatePassword(pwd) {
    if (!pwd) return "Password is required.";
    if (pwd.length < 8) return "Password must be at least 8 characters.";
    if (pwd.length > 72) return "Password is too long.";
    if (!/[A-Za-z]/.test(pwd)) return "Password must contain at least one letter.";
    if (!/\d/.test(pwd)) return "Password must contain at least one number.";
    return null;
}

function formatDateISO(iso) {
    try {
        return new Date(iso).toLocaleString();
    } catch {
        return iso;
    }
}

function formatRelative(iso) {
    try {
        const d = new Date(iso);
        const now = Date.now();
        const diff = Math.floor((now - d.getTime()) / 1000); // seconds
        if (diff < 60) return `${diff}s ago`;
        if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
        if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
        return new Date(iso).toLocaleDateString();
    } catch {
        return iso;
    }
}

function parseUA(ua = "") {
    if (/windows/i.test(ua)) return "Windows";
    if (/mac os/i.test(ua)) return "macOS";
    if (/iphone|ipad/i.test(ua)) return "iOS";
    if (/android/i.test(ua)) return "Android";
    if (/linux/i.test(ua)) return "Linux";
    return "Unknown OS";
}

/* ------------------------- small UI helpers ------------------------- */
function Stat({ label, value }) {
    return (
        <div className="text-xs text-zinc-400 text-right">
            <div className="font-semibold text-white text-sm">{value}</div>
            <div className="text-[11px]">{label}</div>
        </div>
    );
}

function SectionHeader({ icon: Icon, title, subtitle, actions }) {
    return (
        <div className="flex items-start justify-between">
            <div className="flex items-start gap-3">
                {Icon && <Icon className="w-6 h-6 text-zinc-300 mt-0.5" />}
                <div>
                    <div className="text-lg font-semibold text-zinc-100">{title}</div>
                    {subtitle && <div className="text-sm text-zinc-400">{subtitle}</div>}
                </div>
            </div>

            <div className="flex items-center gap-2">{actions}</div>
        </div>
    );
}

function IdentityPill({ provider, type, is_primary }) {
    return (
        <div className="inline-flex items-center gap-2 px-2 py-1 rounded bg-zinc-900/40 border border-white/5 text-xs">
            <Globe className="w-3.5 h-3.5 text-zinc-300" />
            <span className="font-medium">{provider}</span>
            {is_primary && <span className="text-emerald-400 text-[11px] px-1">Primary</span>}
            {type && <span className="text-[11px] text-zinc-500 px-1">{type}</span>}
        </div>
    );
}

/* small Rule indicator used in password modal */
const Rule = ({ ok, text }) => (
    <div className={`flex items-center gap-2 transition-all duration-200 ${ok ? "text-green-400" : "text-red-400"}`}>
        <span className="w-4 text-center">{ok ? "✓" : "•"}</span>
        <span className="text-xs">{text}</span>
    </div>
);

/* ------------------------- main component ------------------------- */
export default function SecurityCenterExpanded() {
    const { width: windowWidth } = useWindowSize();
    const qc = useQueryClient();
    const [confirm, setConfirm] = useState(null); // { type, id }
    const [working, setWorking] = useState(false);

    const [alertModal, setAlertModal] = useState(false);
    const [alertModalTitle, setAlertModalTitle] = useState(null);
    const [alertModalMessage, setAlertModalMessage] = useState(null);

    const [infoModal, setInfoModal] = useState(false);
    const [infoModalTitle, setInfoModalTitle] = useState(null);
    const [infoModalMessage, setInfoModalMessage] = useState(null);

    const [labelModalOpen, setLabelModalOpen] = useState(false);
    const [newPasskeyLabel, setNewPasskeyLabel] = useState("");
    const [pendingOptions, setPendingOptions] = useState(null);
    const [refreshNotice, setRefreshNotice] = useState(null);
    const [refetchingOptions, setRefetchingOptions] = useState(false);

    const [expiresAt, setExpiresAt] = useState(null);
    const [timeoutMs, setTimeoutMs] = useState(60000);
    const [progress, setProgress] = useState(100);
    const [secondsLeft, setSecondsLeft] = useState(null);

    const [existingPasskeyLabels, setExistingPasskeyLabels] = useState([]);

    const [clickedAddPK, setClickedAddPK] = useState(false);

    // --- Password change (two-modal) state ---
    const [pwOtpModalOpen, setPwOtpModalOpen] = useState(false);
    const [pwConfirmModalOpen, setPwConfirmModalOpen] = useState(false);
    const [pwChallengeId, setPwChallengeId] = useState(null);
    const [pwOtp, setPwOtp] = useState("");
    const [pwOtpError, setPwOtpError] = useState("");
    const [pwResendCooldown, setPwResendCooldown] = useState(0);
    const pwCooldownRef = useRef(null);
    const [pwRequesting, setPwRequesting] = useState(false);

    const [OTPsent, setOTPsent] = useState(false);

    const [newPassword, setNewPassword] = useState("");
    const [confirmPassword, setConfirmPassword] = useState("");
    const [showNewPassword, setShowNewPassword] = useState(false);
    const [showConfirmPassword, setShowConfirmPassword] = useState(false);

    const [passkeyInfoOpen, setPasskeyInfoOpen] = useState(false);
    const [oauthInfoOpen, setOAuthInfoOpen] = useState(false);

    const refreshAttemptsRef = useRef(0);

    const securityQuery = useQuery({
        queryKey: ["security", "me"],
        queryFn: async () => {
            const res = await fetch(`${backendUrlV1}/profile/me/security`, {
                credentials: "include",
            });
            if (!res.ok) throw new Error("Failed to load security info");
            return res.json();
        },
        staleTime: 60_000,
    });

    /* ------------------------- action helpers (unchanged logic) ------------------------- */
    const revokeDevice = async (id) => {
        setWorking(true);
        try {
            await fetch(`${backendUrlV1}/profile/me/devices/${id}/revoke`, {
                method: "POST",
                credentials: "include",
            });
            await qc.invalidateQueries({ queryKey: ["security", "me"] });
            setConfirm(null);
        } catch (e) {
            setAlertModalTitle("Failed to sign out device");
            setAlertModalMessage(e.message || "Something went wrong");
            setAlertModal(true);
        } finally {
            setWorking(false);
        }
    };

    const revokeOthers = async () => {
        setWorking(true);
        try {
            await fetch(`${backendUrlV1}/profile/me/devices/revoke-others`, {
                method: "POST",
                credentials: "include",
            });
            await qc.invalidateQueries({ queryKey: ["security", "me"] });
            setConfirm(null);
        } catch (e) {
            setAlertModalTitle("Failed to sign out other devices");
            setAlertModalMessage(e.message || "Something went wrong");
            setAlertModal(true);
        } finally {
            setWorking(false);
        }
    };

    const removePasskey = async (id) => {
        setWorking(true);
        try {
            await fetch(`${backendUrlV1}/auth/passkey/${id}`, {
                method: "DELETE",
                credentials: "include",
            });
            await qc.invalidateQueries({ queryKey: ["security", "me"] });
            setConfirm(null);
        } catch (e) {
            setAlertModalTitle("Failed to remove passkey");
            setAlertModalMessage(e.message || "Something went wrong");
            setAlertModal(true);
        } finally {
            setWorking(false);
        }
    };

    useEffect(() => {
        if (pwResendCooldown <= 0) {
            clearInterval(pwCooldownRef.current);
            return;
        }
        pwCooldownRef.current = setInterval(() => {
            setPwResendCooldown((s) => {
                if (s <= 1) {
                    clearInterval(pwCooldownRef.current);
                    return 0;
                }
                return s - 1;
            });
        }, 1000);
        return () => clearInterval(pwCooldownRef.current);
    }, [pwResendCooldown]);

    useEffect(() => {
        if (!expiresAt) return;

        let animationFrame;
        let isMounted = true;
        let refreshing = false;

        const loop = async () => {
            if (!isMounted) return;

            const remaining = expiresAt - Date.now();

            if (remaining <= 0) {
                setProgress(0);
                setSecondsLeft(0);

                if (!refreshing) {
                    refreshing = true;

                    try {
                        setRefetchingOptions(true);
                        setRefreshNotice("Refreshing secure session…");

                        const freshOptions = await registerPasskey_1();
                        if (!isMounted) return;

                        refreshAttemptsRef.current = 0;

                        const newTimeout = freshOptions.timeout || 60000;

                        setPendingOptions(freshOptions);
                        setTimeoutMs(newTimeout);
                        setExpiresAt(Date.now() + newTimeout);
                        setProgress(100);
                        setSecondsLeft(Math.ceil(newTimeout / 1000));

                        setRefreshNotice("Session refreshed.");
                        setTimeout(() => {
                            setRefreshNotice(null);
                        }, 5000);
                    } catch {
                        if (!isMounted) return;

                        refreshAttemptsRef.current += 1;

                        if (refreshAttemptsRef.current >= 3) {
                            setRefreshNotice("Session expired. Please restart registration.");
                            setPendingOptions(null);
                            return;
                        }

                        setRefreshNotice(`Refresh failed (${refreshAttemptsRef.current}/3). Retrying…`);
                    } finally {
                        if (isMounted) setRefetchingOptions(false);
                    }

                    refreshing = false;
                }
            } else {
                setSecondsLeft(Math.ceil(remaining / 1000));
                const pct = parseFloat(((remaining / timeoutMs) * 100).toFixed(3));
                setProgress(pct);
            }

            animationFrame = requestAnimationFrame(loop);
        };

        animationFrame = requestAnimationFrame(loop);

        return () => {
            isMounted = false;
            cancelAnimationFrame(animationFrame);
        };
    }, [expiresAt, timeoutMs]);

    const startPasswordChangeFlow = () => {
        setPwOtp("");
        setPwOtpError("");
        setPwChallengeId(null);
        setPwResendCooldown(0);
        setPwOtpModalOpen(true);
    };

    const requestPasswordOtp = async () => {
        setPwRequesting(true);
        setWorking(true);
        setPwOtpError("");
        try {
            const fingerprint = window.localStorage.getItem("device_fp") || "";
            const res = await fetch(`${backendUrlV1}/auth/password-change/request-otp`, {
                method: "POST",
                credentials: "include",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ fingerprint }),
            });
            const body = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(body?.detail || "Failed to request OTP");
            setOTPsent(true);
            setPwChallengeId(body.challenge_id);
            setPwResendCooldown(body.resend_cooldown || 30);
        } catch (e) {
            resetProcess();
            setPwOtpError(e.message || "Could not request verification code");
        } finally {
            setPwRequesting(false);
            setWorking(false);
        }
    };

    const resendPasswordOtp = async () => {
        if (!pwChallengeId) return;
        setPwRequesting(true);
        setWorking(true);
        setPwOtpError("");
        try {
            const res = await fetch(`${backendUrlV1}/auth/password-change/resend-otp`, {
                method: "POST",
                credentials: "include",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ challenge_id: pwChallengeId }),
            });
            const body = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(body?.detail || "Failed to resend OTP");
            setPwResendCooldown(body.resend_cooldown || 30);
            setAlertModalTitle("Code sent");
            setAlertModalMessage("A new verification code was sent to your email.");
            setAlertModal(true);
        } catch (e) {
            resetProcess();
            setPwOtpError(e.message || "Could not resend verification code");
        } finally {
            setPwRequesting(false);
            setWorking(false);
        }
    };

    const verifyPasswordOtp = async () => {
        if (!pwChallengeId || !pwOtp) {
            setPwOtpError("Enter the code");
            return;
        }
        setWorking(true);
        setPwOtpError("");
        try {
            const res = await fetch(`${backendUrlV1}/auth/password-change/verify-otp`, {
                method: "POST",
                credentials: "include",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ challenge_id: pwChallengeId, code: pwOtp }),
            });
            const body = await res.json().catch(() => ({}));
            if (!res.ok) {
                throw new Error(body?.message || "Failed to verify OTP");
            }
            setPwOtpModalOpen(false);
            setPwConfirmModalOpen(true);
        } catch (e) {
            setPwOtpError(e.message || "Verification failed");
        } finally {
            setWorking(false);
        }
    };

    const resetProcess = () => {
        setNewPassword("");
        setConfirmPassword("");
        setPwOtpModalOpen(false);
        setPwConfirmModalOpen(false);
        setPwChallengeId(null);
        setPwOtpError("");
        setPwOtp("");
        setPwResendCooldown(0);
        setOTPsent(false);
    };

    const confirmPasswordChange = async () => {
        const vErr = validatePassword(newPassword);
        if (vErr) {
            setAlertModalTitle("Weak password");
            setAlertModalMessage(vErr);
            setAlertModal(true);
            return;
        }
        if (newPassword !== confirmPassword) {
            setAlertModalTitle("Password mismatch");
            setAlertModalMessage("Passwords do not match.");
            setAlertModal(true);
            return;
        }

        setWorking(true);
        try {
            const res = await fetch(`${backendUrlV1}/auth/password-change/confirm`, {
                method: "POST",
                credentials: "include",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    challenge_id: pwChallengeId,
                    code: pwOtp,
                    new_password: newPassword,
                }),
            });
            const body = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(body?.detail || "Failed to change password");

            resetProcess();
            setAlertModalTitle("Password changed");
            setAlertModalMessage("Your password was updated. If this wasn't you, check your email for instructions.");
            setAlertModal(true);

            await qc.invalidateQueries({ queryKey: ["security", "me"] });
        } catch (e) {
            setAlertModalTitle("Failed to change password");
            setAlertModalMessage(e.message || "Verification failed");
            setAlertModal(true);
        } finally {
            setWorking(false);
        }
    };

    if (securityQuery.isLoading) {
        return (
            <div className="p-6 rounded-xl bg-white/3 flex flex-col items-center gap-3">
                <div className="h-9 w-9 rounded-full border-2 border-white/20 border-t-white animate-spin" />
                <span className="text-sm text-white/70">Loading security…</span>
            </div>
        );
    }

    const data = securityQuery.data || {};
    const {
        email,
        devices = [],
        passkeys = [],
        current_device_id,
        plan,
        can_vote,
        can_moderate,
        identities = [],
        is_banned,
    } = data;

    const has_password_login = identities.some((id) => id.type.toLowerCase() === "password");

    const trustedDevicesCount = devices.filter((d) => d.is_trusted).length;
    const currentDevice = devices.find((d) => d.is_current) || devices.find((d) => d.id === current_device_id);

    // password strength indicators for the new password input (live feedback)
    const passwordRules = {
        length: newPassword.length >= 8,
        upper: /[A-Z]/.test(newPassword),
        lower: /[a-z]/.test(newPassword),
        number: /[0-9]/.test(newPassword),
        match: newPassword && newPassword === confirmPassword,
    };
    const isPasswordStrong = Object.values(passwordRules).every(Boolean);
    const strengthScore = [passwordRules.length, passwordRules.upper, passwordRules.lower, passwordRules.number].filter(Boolean).length;
    const strengthPct = (strengthScore / 4) * 100;

    // Combine identities for UI: include password identity if backend says it exists
    const combinedIdentities = identities;

    /* ------------------------- Render ------------------------- */
    return (
        <section className="overflow-hidden space-y-6">
            {/* Confirm / Alert / Info modals (same as before) */}
            <Modal
                isOpen={!!confirm}
                lock
                type="warning"
                title="Confirm action"
                description={
                    confirm?.type === "device"
                        ? "This will sign out this device."
                        : confirm?.type === "others"
                            ? "This will sign out all other devices."
                            : "This will permanently remove this passkey."
                }
                primaryAction={{
                    label: working ? "Working…" : "Confirm",
                    onClick: () => {
                        if (confirm.type === "device") revokeDevice(confirm.id);
                        if (confirm.type === "others") revokeOthers();
                        if (confirm.type === "passkey") removePasskey(confirm.id);
                    },
                }}
                secondaryAction={{
                    label: "Cancel",
                    onClick: () => setConfirm(null),
                }}
            />

            <Modal
                isOpen={alertModal}
                lock
                type="error"
                title={alertModalTitle}
                description={alertModalMessage}
                secondaryAction={{
                    label: "Close",
                    onClick: () => {
                        setAlertModalTitle(null);
                        setAlertModalMessage(null);
                        setAlertModal(false);
                    },
                }}
            />

            <Modal
                isOpen={infoModal}
                lock
                type="info"
                title={infoModalTitle}
                description={infoModalMessage}
                secondaryAction={{
                    label: "Close",
                    onClick: () => {
                        setInfoModalTitle(null);
                        setInfoModalMessage(null);
                        setInfoModal(false);
                    },
                }}
            />

            {/* ---------- Top summary ---------- */}
            <div className="p-4 sm:p-6 rounded-xl bg-zinc-900/30 border border-zinc-800 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                <div className="flex items-start gap-4 w-full sm:w-auto">
                    <div className="rounded-full bg-zinc-800/50 w-12 h-12 flex items-center justify-center flex-shrink-0">
                        <User className="w-6 h-6 text-zinc-200" />
                    </div>

                    <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                            <div className="text-sm text-zinc-200 font-medium truncate max-w-[60vw] sm:max-w-xs">{email}</div>
                            {is_banned && <span className="text-xs text-red-400 px-2 py-0.5 rounded bg-red-600/10">BANNED</span>}
                            <span className="text-xs px-2 py-0.5 rounded bg-zinc-800 text-zinc-300">{plan || "FREE"}</span>
                        </div>
                        <div className="text-xs text-zinc-400 mt-1">
                            <span className="inline-flex items-center gap-1 mr-3">
                                {can_vote ? <CheckCircle className="w-3 h-3 text-emerald-400" /> : <XCircle className="w-3 h-3 text-red-400" />} {can_vote ? "Can vote" : "Cannot vote"}
                            </span>
                            <span className="inline-flex items-center gap-1">
                                {can_moderate ? <ShieldCheck className="w-3 h-3 text-emerald-400" /> : <XCircle className="w-3 h-3 text-red-400" />} {can_moderate ? "Moderator" : "Not a moderator"}
                            </span>
                        </div>
                        <div className="text-xs text-zinc-500 mt-2">Manage your sign-in methods, devices and passkeys below.</div>
                    </div>
                </div>

                <div className="flex items-center gap-4 ml-0 sm:ml-auto">
                    {/* On very small screens show condensed stats */}
                    <div className="flex gap-3">
                        <div className="hidden sm:block">
                            <Stat label="Passkeys" value={passkeys.length} />
                        </div>
                        <div className="hidden sm:block">
                            <Stat label="Devices" value={devices.length} />
                        </div>
                        <div className="hidden sm:block">
                            <Stat label="Trusted" value={trustedDevicesCount} />
                        </div>

                        {/* Condensed mobile view */}
                        <div className="sm:hidden flex gap-2 text-xs text-zinc-400">
                            <div className="inline-flex items-center gap-1"><Fingerprint className="w-3 h-3" />{passkeys.length}</div>
                            <div className="inline-flex items-center gap-1"><Laptop className="w-3 h-3" />{devices.length}</div>
                            <div className="inline-flex items-center gap-1"><CheckCircle className="w-3 h-3" />{trustedDevicesCount}</div>
                        </div>
                    </div>
                </div>
            </div>

            {/* ---------- Credentials / Login methods ---------- */}
            <div className="p-4 sm:p-6 border border-zinc-800 rounded-xl">
                <SectionHeader
                    icon={Key}
                    title="Credentials & Login methods"
                    subtitle="Manage how you sign in - passwords, OAuth providers, and primary identity."
                    actions={
                        !has_password_login && (
                            <button
                                className="text-sm text-zinc-300 hover:text-white"
                                onClick={() => {
                                    startPasswordChangeFlow();
                                    setPwOtpModalOpen(true);
                                }}
                                aria-label="Add password"
                            >
                                Add password
                            </button>
                        )
                    }
                />

                <div className="mt-4 space-y-2">
                    {combinedIdentities.length === 0 ? (
                        <div className="text-sm text-zinc-500">No login methods found.</div>
                    ) : (
                        combinedIdentities.map((id, idx) => {
                            const provider = id.provider || "unknown";
                            const type = id.type || (provider === "password" ? "password" : "OAuth");
                            const isPrimary = !!id.is_primary;

                            return (
                                <div key={`${provider}-${idx}`} className={`${idx !== combinedIdentities.length - 1 && "border-b border-zinc-800"} pt-1 pb-3`}>
                                    <div className="flex items-center justify-between rounded-lg px-3 py-2 hover:bg-white/5 transition">
                                        <div className="flex items-center gap-3 min-w-0">
                                            <Globe className="w-3.5 h-3.5 text-zinc-300" />
                                            <div className="min-w-0">
                                                <div className="font-medium truncate">
                                                    {provider.charAt(0).toUpperCase() + provider.slice(1)} {isPrimary && <span className="ml-2 text-xs text-emerald-400">Primary</span>}
                                                </div>
                                                <div className="text-xs text-zinc-500">{`${type.charAt(0).toUpperCase() + type.slice(1)} provider`}</div>
                                            </div>
                                        </div>

                                        <div className="flex items-center gap-3">
                                            {type.toLowerCase() === "password" ? (
                                                <button
                                                    className="text-sm text-zinc-300 hover:text-white transition"
                                                    onClick={() => {
                                                        // password identity: change password flow
                                                        startPasswordChangeFlow();
                                                        setPwOtpModalOpen(true);
                                                    }}
                                                    aria-label="Change password"
                                                >
                                                    Change password
                                                </button>
                                            ) : (
                                                <div className="flex flex-row items-center gap-x-2 text-xs">
                                                    {type}{" "}
                                                    <Info
                                                        data-tooltip-id={`info-tooltip-${idx}`}
                                                        className="w-4 h-4 cursor-pointer"
                                                        onClick={() => setOAuthInfoOpen(true)}
                                                        aria-label={`About ${provider} OAuth`}
                                                    />
                                                    <Tooltip
                                                    style={{backgroundColor: "black", color: "white", padding: "6px 8px", borderRadius: "4px", fontSize: "12px"}}
                                                        data-tooltip-place="top"
                                                        id={`info-tooltip-${idx}`}
                                                        content="Learn more about OAuth"
                                                    />
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            );
                        })
                    )}
                </div>
            </div>

            {/* ---------- Passkeys ---------- */}
            <div className="p-4 sm:p-6 border border-zinc-800 rounded-xl">
                <SectionHeader
                    icon={Fingerprint}
                    title="Passkeys"
                    subtitle="Passwordless sign-in using your device's secure authenticator."
                    actions={
                        <div className="flex items-center gap-2">
                            <button
                                className="text-sm flex items-center gap-2 text-zinc-300 hover:text-white transition px-3 py-2 rounded touch-manipulation"
                                onClick={async () => {
                                    setClickedAddPK(true);
                                    try {
                                        setExistingPasskeyLabels(passkeys.map((pk) => pk.name));
                                        const options = await registerPasskey_1();
                                        const t = options.timeout || 60000;
                                        setPendingOptions(options);
                                        setTimeoutMs(t);
                                        setExpiresAt(Date.now() + t);
                                        setProgress(1);
                                        setSecondsLeft(Math.ceil(t / 1000));
                                        setLabelModalOpen(true);
                                    } catch (e) {
                                        setAlertModalTitle("Failed to start passkey registration");
                                        setAlertModalMessage(e.message || "Failed to register passkey");
                                        setAlertModal(true);
                                    } finally {
                                        setClickedAddPK(false);
                                    }
                                }}
                                aria-label="Add passkey"
                            >
                                {!clickedAddPK ? (
                                    <>
                                        <Plus size={16} />
                                        <span className="hidden sm:inline">Add passkey</span>
                                    </>
                                ) : (
                                    <div className="flex items-center gap-2 text-sm text-zinc-400">
                                        <Fingerprint className="w-4 h-4 fingerprint-loading" />
                                        Checking with the server...
                                    </div>
                                )}
                            </button>

                            <button
                                className="text-xs px-3 py-1 rounded bg-transparent text-zinc-400 hover:bg-white/3 touch-manipulation"
                                onClick={() => setPasskeyInfoOpen(true)}
                                aria-label="About passkeys"
                            >
                                About passkeys
                            </button>
                        </div>
                    }
                />

                {passkeys.length === 0 ? (
                    <div className="text-sm text-zinc-500 mt-4">You haven't added any passkeys yet. Passkeys let you sign in without passwords and are strongly recommended.</div>
                ) : (
                    <div className="mt-4 space-y-2">
                        {passkeys.map((pk) => (
                            <div key={pk.id} className="flex items-center justify-between rounded-lg px-3 py-2 hover:bg-white/5 transition">
                                <div className="min-w-0">
                                    <div className="font-medium truncate">
                                        {pk.name}
                                        {pk.is_current && <span className="ml-2 text-xs text-emerald-400">This device</span>}
                                    </div>
                                    <div className="text-xs text-zinc-500">Added {pk.created_at ? new Date(pk.created_at).toLocaleDateString() : "unknown"}</div>
                                </div>

                                <button className="text-xs text-red-400 hover:underline" onClick={() => setConfirm({ type: "passkey", id: pk.id })} aria-label={`Remove passkey ${pk.name}`}>
                                    Remove
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* ---------- Devices ---------- */}
            <div className="p-4 sm:p-6 border border-zinc-800 rounded-xl">
                <div className="flex items-center justify-between">
                    <div className="font-medium flex items-center gap-2">
                        <Laptop className="w-5 h-5" /> Devices ({devices.length})
                    </div>

                    <div className="flex items-center gap-3">
                        <div className="text-xs text-zinc-400">Trusted: <span className="font-semibold text-white">{trustedDevicesCount}</span></div>
                        <button className="text-sm text-red-400 hover:underline" onClick={() => setConfirm({ type: "others" })} aria-label="Sign out other devices">
                            Sign out others
                        </button>
                    </div>
                </div>

                {devices.length === 0 && <div className="text-sm text-zinc-500 mt-3">No devices found.</div>}

                <div className="mt-3 space-y-2">
                    {devices.map((d) => (
                        <div key={d.id} className="flex items-center justify-between rounded-lg px-3 py-2 hover:bg-white/5 transition">
                            <div className="min-w-0">
                                <div className="font-medium truncate">
                                    {parseUA(d.user_agent)}
                                    {d.is_current && <span className="ml-2 text-xs text-emerald-400">This device</span>}
                                    {d.is_trusted && <span className="ml-2 text-xs text-blue-400">Trusted</span>}
                                </div>

                                <div className="text-xs text-zinc-500">
                                    First seen {formatDateISO(d.first_seen_at)} • Last used {formatRelative(d.last_seen_at)}
                                </div>

                                <div className="text-xs text-zinc-400 mt-1 truncate max-w-full">{d.user_agent}</div>
                            </div>

                            {!d.is_current ? (
                                <button className="text-xs text-red-400 hover:underline" onClick={() => setConfirm({ type: "device", id: d.id })}>
                                    Sign out
                                </button>
                            ) : (
                                <div className="text-xs text-zinc-500">Active</div>
                            )}
                        </div>
                    ))}
                </div>

                {/* current device quick info */}
                {currentDevice && (
                    <div className="mt-4 rounded-lg bg-zinc-900/40 border border-white/5 p-3 text-sm">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3 min-w-0">
                                <Laptop className="w-5 h-5 text-zinc-300" />
                                <div className="min-w-0">
                                    <div className="font-medium truncate">{parseUA(currentDevice.user_agent)} <span className="text-xs text-zinc-400">({currentDevice.user_agent.split(" ").slice(0, 2).join(" ")})</span></div>
                                    <div className="text-xs text-zinc-500">Last used {formatDateISO(currentDevice.last_seen_at)}</div>
                                </div>
                            </div>

                            <div className="text-xs text-zinc-400">
                                {currentDevice.is_trusted ? <span className="inline-flex items-center gap-1"><CheckCircle className="w-4 h-4 text-emerald-400" /> Trusted</span> : <span className="inline-flex items-center gap-1"><XCircle className="w-4 h-4 text-red-400" /> Not trusted</span>}
                            </div>
                        </div>
                    </div>
                )}
            </div>

            {/* ---------- Hidden/Modal content (passkey label modal, password OTP + confirm, passkey info) ---------- */}
            <Modal
                isOpen={labelModalOpen}
                lock
                type="info"
                title="Name this passkey"
                description="Give this device a friendly name so it's easy to recognize later."
                primaryAction={{
                    label: refetchingOptions ? "Refreshing…" : working ? "Saving…" : "Save Passkey",
                    onClick: async () => {
                        if (!newPasskeyLabel.trim() || !pendingOptions) return;

                        try {
                            setWorking(true);

                            const trimmed = newPasskeyLabel.trim();

                            if (existingPasskeyLabels.includes(trimmed)) {
                                setAlertModalTitle("Duplicate passkey name");
                                setAlertModalMessage("You already have a passkey with this name. Please choose another.");
                                setAlertModal(true);
                                return;
                            }

                            await registerPasskey_2(pendingOptions, trimmed);

                            setLabelModalOpen(false);
                            setPendingOptions(null);
                            qc.invalidateQueries({ queryKey: ["security", "me"] });
                            setExistingPasskeyLabels([]);
                            setNewPasskeyLabel("");
                        } catch (e) {
                            setAlertModalTitle("Passkey registration failed");
                            setAlertModalMessage(e?.message || "Verification failed");
                            setAlertModal(true);
                        } finally {
                            setWorking(false);
                        }
                    },
                }}
                secondaryAction={{
                    label: "Cancel",
                    onClick: () => {
                        setLabelModalOpen(false);
                        setPendingOptions(null);
                        setNewPasskeyLabel("");
                    },
                }}
            >
                <div className="p-5 space-y-5 max-h-[60vh] overflow-auto touch-manipulation">
                    {/* Session Status */}
                    {secondsLeft != null && (
                        <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 px-4 py-3">
                            <div className="flex items-center justify-between mb-2">
                                <div className="flex flex-col">
                                    <div className="flex items-center gap-2">
                                        <span className={`text-sm font-medium ${progress <= 10 ? "text-red-400" : "text-zinc-300"}`}>
                                            Session valid for {secondsLeft}s
                                        </span>

                                        <Info
                                            className="text-zinc-500 cursor-pointer"
                                            size={16}
                                            onClick={() => {
                                                setInfoModalTitle("Why the timer?");
                                                setInfoModalMessage(
                                                    "We refresh the session automatically. This session is used to securely complete the passkey registration. If the timer runs out, we'll get a fresh session for you without losing your progress."
                                                );
                                                setInfoModal(true);
                                            }}
                                        />
                                    </div>

                                    <span className="text-[11px] text-zinc-500">This session refreshes automatically</span>
                                </div>
                            </div>

                            <div className="h-2 w-full bg-zinc-800 rounded-full">
                                <div className={`h-full rounded-full ${progress <= 10 ? "bg-red-500" : "bg-blue-400"}`} style={{ width: `${progress}%` }} />
                            </div>

                            {refreshNotice && <div className="text-xs text-blue-400 mt-2">{refreshNotice}</div>}
                        </div>
                    )}

                    {/* Label Input */}
                    <div className="space-y-2">
                        <label className="text-xs text-zinc-400">Passkey name</label>

                        <input
                            autoFocus
                            className="input-dark w-full"
                            placeholder="e.g. Work Laptop, Personal Phone"
                            value={newPasskeyLabel}
                            onChange={(e) => setNewPasskeyLabel(e.target.value)}
                            aria-label="Passkey name"
                        />
                    </div>
                </div>
            </Modal>

            {/* Password OTP modal */}
            <Modal
                isOpen={pwOtpModalOpen}
                lock
                type="info"
                title="Verify it's you"
                description="We will send a one-time code to your email. Enter it below to continue."
                secondaryAction={{
                    label: "Cancel",
                    onClick: () => {
                        resetProcess();
                        setPwOtpModalOpen(false);
                    },
                }}
            >
                <div className="p-3 space-y-3 max-h-[60vh] overflow-auto touch-manipulation">
                    <div className="text-sm text-zinc-400">
                        A verification code will be sent to your email: <span className="font-semibold">{email}</span>
                        <div className="mt-2 text-xs text-zinc-500">We will not change your password until you confirm the code.</div>
                    </div>

                    <div className="space-y-2">
                        <input
                            type="text"
                            inputMode="numeric"
                            pattern="[0-9]*"
                            className="input-dark w-full"
                            placeholder="One-time code (6 digits)"
                            value={pwOtp}
                            onChange={(e) => setPwOtp(e.target.value.replace(/\D/g, "").slice(0, 6))}
                            aria-label="One-time verification code"
                        />
                        {pwOtpError && <div className="text-sm text-red-400">{pwOtpError}</div>}

                        <div className="flex items-center justify-between text-xs ">
                            {OTPsent ? (
                                <div>
                                    {pwResendCooldown > 0 ? <span>Resend available in {pwResendCooldown}s</span> : <button className="underline" onClick={resendPasswordOtp} disabled={pwRequesting || working || !pwChallengeId}>Resend code</button>}
                                </div>
                            ) : (
                                <div />
                            )}

                            <div className="flex gap-2">
                                <button
                                    className="px-3 py-1 rounded bg-neutral-800 border border-gray-700 text-xs"
                                    onClick={() => {
                                        if (!OTPsent) {
                                            requestPasswordOtp();
                                        } else {
                                            verifyPasswordOtp();
                                        }
                                    }}
                                    aria-label={OTPsent ? "Verify code" : "Send code"}
                                >
                                    {pwRequesting ? "Sending..." : OTPsent ? "Verify code" : "Send code"}
                                </button>
                                <button
                                    className="px-3 py-1 rounded bg-transparent text-xs"
                                    onClick={() => {
                                        setPwOtp("");
                                        setPwChallengeId(null);
                                        setOTPsent(false);
                                        setPwResendCooldown(0);
                                        setPwOtpError(null);
                                    }}
                                    aria-label="Start over"
                                >
                                    Start over
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </Modal>

            {/* Password confirm modal */}
            <Modal
                isOpen={pwConfirmModalOpen}
                lock
                type="warning"
                title="Set a new password"
                description="Enter a strong password to replace your existing one."
                primaryAction={{
                    label: working ? "Working…" : "Save password",
                    onClick: async () => {
                        await confirmPasswordChange();
                    },
                }}
                secondaryAction={{
                    label: "Cancel",
                    onClick: () => {
                        resetProcess();
                        setPwConfirmModalOpen(false);
                    },
                }}
            >
                <div className="p-3 space-y-3 max-h-[70vh] overflow-auto touch-manipulation">
                    <form autoComplete="on" className="space-y-3" onSubmit={(e) => e.preventDefault()}>
                        <div className="relative">
                            <input
                                type={showNewPassword ? "text" : "password"}
                                placeholder="Password"
                                value={newPassword}
                                onChange={(e) => setNewPassword(e.target.value)}
                                required
                                className={`w-full px-4 py-2.5 pr-10 rounded-lg bg-neutral-900 border ${newPassword ? (isPasswordStrong ? "border-green-500" : "border-red-500") : "border-gray-700"} text-white placeholder-gray-500 focus:outline-none`}
                                aria-label="New password"
                                autoComplete="new-password"
                            />
                            <button type="button" onClick={() => setShowNewPassword((v) => !v)} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm" aria-label={showNewPassword ? "Hide new password" : "Show new password"}>
                                {showNewPassword ? "Hide" : "Show"}
                            </button>
                        </div>

                        <div className="relative">
                            <input
                                type={showConfirmPassword ? "text" : "password"}
                                placeholder="Confirm password"
                                value={confirmPassword}
                                onChange={(e) => setConfirmPassword(e.target.value)}
                                required
                                className={`w-full px-4 py-2.5 pr-10 rounded-lg bg-neutral-900 border ${confirmPassword ? (passwordRules.match ? "border-green-500" : "border-red-500") : "border-gray-700"} text-white placeholder-gray-500 focus:outline-none`}
                                aria-label="Confirm password"
                                autoComplete="new-password"
                            />
                            <button type="button" onClick={() => setShowConfirmPassword((v) => !v)} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm" aria-label={showConfirmPassword ? "Hide confirm password" : "Show confirm password"}>
                                {showConfirmPassword ? "Hide" : "Show"}
                            </button>
                        </div>
                    </form>

                    <div className="text-xs text-neutral-400">Password strength</div>
                    <div className="h-1 w-full bg-neutral-800 rounded overflow-hidden">
                        <div className="h-full bg-orange-500 transition-all duration-300" style={{ width: `${strengthPct}%` }} />
                    </div>

                    <div className="flex items-center flex-col text-xs space-y-1 mt-2">
                        <div className="flex w-full justify-between gap-2">
                            <div>
                                <Rule ok={passwordRules.length} text="At least 8 characters" />
                                <Rule ok={passwordRules.upper} text="One uppercase letter" />
                            </div>
                            <div>
                                <Rule ok={passwordRules.lower} text="One lowercase letter" />
                                <Rule ok={passwordRules.number} text="One number" />
                            </div>
                        </div>
                        <div className="flex w-full items-center">
                            <Rule ok={passwordRules.match} text="Passwords match" />
                        </div>
                    </div>
                </div>
            </Modal>

            {/* About passkeys */}
            <Modal
                isOpen={passkeyInfoOpen}
                lock
                type="info"
                title="About passkeys"
                description="A safer, simpler way to sign in"
                primaryAction={{ label: "Got it", onClick: () => setPasskeyInfoOpen(false) }}
                secondaryAction={{ label: "Close", onClick: () => setPasskeyInfoOpen(false) }}
            >
                <div className="p-3 space-y-4 max-h-[60vh] overflow-auto touch-manipulation">
                    <div className="flex items-center gap-3">
                        <Fingerprint className="w-6 h-6 text-emerald-400 animate-pulse-soft" />
                        <p className="text-sm text-zinc-300 leading-relaxed">
                            Passkeys let you sign in <strong>without passwords</strong>, using your device's built-in security.
                        </p>
                    </div>

                    <div className="space-y-2 text-sm text-zinc-300">
                        <div className="flex items-start gap-2">
                            <ShieldCheck className="w-4 h-4 text-emerald-400 mt-0.5" />
                            <span>Protected by Face ID, fingerprint, or your device's screen lock</span>
                        </div>

                        <div className="flex items-start gap-2">
                            <Lock className="w-4 h-4 text-emerald-400 mt-0.5" />
                            <span>Resistant to phishing, leaks, and reused passwords</span>
                        </div>

                        <div className="flex items-start gap-2">
                            <Laptop className="w-4 h-4 text-emerald-400 mt-0.5" />
                            <span>Your biometric data never leaves your device</span>
                        </div>
                    </div>

                    <div className="pt-3 border-t border-white/5 flex items-center justify-between">
                        <span className="text-xs text-zinc-400">Supported on most modern devices</span>
                        <a href="https://oauth.net/about/introduction/" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs font-medium text-emerald-400 hover:text-emerald-300 transition">
                            <PlayCircle className="w-4 h-4" />
                            Learn more about related standards
                        </a>
                    </div>
                </div>
            </Modal>

            {/* About OAuth */}
            <Modal
                isOpen={oauthInfoOpen}
                lock
                type="info"
                title="About OAuth"
                description="A secure way to grant limited access without sharing passwords"
                primaryAction={{ label: "Got it", onClick: () => setOAuthInfoOpen(false) }}
                secondaryAction={{ label: "Close", onClick: () => setOAuthInfoOpen(false) }}
            >
                <div className="p-3 space-y-4 max-h-[60vh] overflow-auto touch-manipulation">

                    <div className="flex items-center gap-3">
                        <ShieldCheck className="w-6 h-6 text-emerald-400 animate-pulse-soft" />
                        <p className="text-sm text-zinc-300 leading-relaxed">
                            <strong>OAuth</strong> is an open authorization standard that allows apps to access
                            your information from another service <strong>without sharing your password</strong>.
                        </p>
                    </div>

                    <div className="space-y-2 text-sm text-zinc-300">
                        <div className="flex items-start gap-2">
                            <Lock className="w-4 h-4 text-emerald-400 mt-0.5" />
                            <span>
                                You sign in directly with the provider (like Google or Apple), not with the app.
                            </span>
                        </div>

                        <div className="flex items-start gap-2">
                            <Fingerprint className="w-4 h-4 text-emerald-400 mt-0.5" />
                            <span>
                                The app receives a secure access token instead of your actual credentials.
                            </span>
                        </div>

                        <div className="flex items-start gap-2">
                            <Laptop className="w-4 h-4 text-emerald-400 mt-0.5" />
                            <span>
                                Access can be limited in scope and revoked at any time from your provider settings.
                            </span>
                        </div>
                    </div>

                    <div className="pt-3 border-t border-white/5 flex items-center justify-between">
                        <span className="text-xs text-zinc-400">
                            Widely used by Google, Apple, GitHub and many others
                        </span>
                        <a
                            href="https://oauth.net/about/introduction/"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-xs font-medium text-emerald-400 hover:text-emerald-300 transition"
                        >
                            <PlayCircle className="w-4 h-4" />
                            Learn more
                        </a>
                    </div>
                </div>
            </Modal>

        </section>
    );
}
