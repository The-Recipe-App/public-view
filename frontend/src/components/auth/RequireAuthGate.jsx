// components/auth/RequireAuthGate.jsx

import { Lock } from "lucide-react";
import { useNavigate } from "react-router-dom";

export default function RequireAuthGate({
  message = "Sign in to continue",
  sub = "You need to sign-in to access this.",
  returnTo,
}) {
  const navigate = useNavigate();
  const to = returnTo || window.location.pathname + window.location.search;

  return (
    <div className="min-h-[60vh] flex items-center justify-center px-6">
      <div
        className="relative max-w-sm w-full text-center"
      >
        {/* Icon */}
        <div className="mx-auto mb-6 w-16 h-16 rounded-full border border-amber-500/20 bg-amber-500/5 flex items-center justify-center">
          <Lock size={28} />
        </div>

        {/* Text */}
        <h2
          className="text-white text-2xl font-semibold mb-2 leading-snug"
        >
          {message}
        </h2>
        <p className="text-neutral-500 text-sm leading-relaxed mb-8">{sub}</p>

        {/* Actions */}
        <div className="flex flex-col gap-3">
          <button
            onClick={() => {
              localStorage.setItem('redirectAfterLogin', returnTo || window.location.pathname + window.location.search);
              navigate(`/login`);
            }}
            className="w-full py-3 rounded-2xl text-sm font-semibold text-black transition-all duration-200
              bg-gradient-to-r from-amber-500 to-orange-500
              shadow-[0_4px_24px_rgba(232,160,32,0.2)] hover:shadow-[0_6px_32px_rgba(232,160,32,0.35)]
              active:scale-[0.99]"
          >
            Sign in
          </button>
        </div>

        {/* Subtle divider line */}
        <div className="mt-8 flex items-center gap-3">
          <div className="flex-1 h-px bg-neutral-800" />
          <span className="text-[10px] text-neutral-600 uppercase tracking-widest">or</span>
          <div className="flex-1 h-px bg-neutral-800" />
        </div>
        <button
          onClick={() => navigate("/recipes")}
          className="mt-4 text-xs text-neutral-600 hover:text-neutral-400 transition-colors"
        >
          Browse without signing in →
        </button>
      </div>
    </div>
  );
}