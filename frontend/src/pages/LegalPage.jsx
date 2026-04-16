import { useNavigate, useParams } from "react-router-dom";
import { useEffect, useMemo } from "react";
import Select from "react-select";

import { usePolicy } from "../hooks/usePolicy";
import PolicyContentRenderer from "../features/PolicyContentRenderer";

const DEFAULT_POLICY = "tos";

/*
  react-select expects:
  { value, label }
*/
const POLICY_OPTIONS = [
    { value: "tos", label: "Terms of Service" },
    { value: "privacy", label: "Privacy Policy" },
    { value: "community_guidelines", label: "Community Guidelines" },
    { value: "cookie_policy", label: "Cookie Policy" },
    { value: "license", label: "Forkit Open Source License" },
];


// ---------------- POLICY SELECT ----------------

function PolicySelect({ activePolicy }) {
    const navigate = useNavigate();

    const selectedOption = useMemo(
        () => POLICY_OPTIONS.find((o) => o.value === activePolicy),
        [activePolicy]
    );

    return (
        <div className="mt-4 w-full max-w-xs">
            <Select
                value={selectedOption}
                options={POLICY_OPTIONS}
                isSearchable={false}
                menuPortalTarget={document.body}
                styles={selectStyles}
                theme={selectTheme}
                onChange={(option) => {
                    if (option?.value) {
                        navigate(`/legal/${option.value}`);
                    }
                }}
            />
        </div>
    );
}


// ---------------- SELECT STYLES ----------------

const selectTheme = (theme) => ({
    ...theme,
    borderRadius: 12,
    colors: {
        ...theme.colors,
        primary: "#3b82f6",
        primary25: "rgba(59,130,246,0.15)",
        neutral0: "transparent",
    },
});

const selectStyles = {
    container: (base) => ({
        ...base,
        fontSize: "14px",
    }),

    control: (base, state) => ({
        ...base,
        background: "rgba(23,23,23,0.6)",
        backdropFilter: "blur(12px)",
        borderColor: state.isFocused ? "#3b82f6" : "#404040",
        boxShadow: state.isFocused
            ? "0 0 0 2px rgba(59,130,246,0.3)"
            : "none",
        padding: "2px 6px",
        cursor: "pointer",
        transition: "all 0.2s ease",
    }),

    menuPortal: (base) => ({
        ...base,
        zIndex: 9999,
    }),

    menu: (base) => ({
        ...base,
        background: "#171717",
        border: "1px solid #404040",
        borderRadius: "12px",
        overflow: "hidden",
    }),

    option: (base, state) => ({
        ...base,
        background: state.isFocused
            ? "rgba(59,130,246,0.15)"
            : "transparent",
        color: "#e5e5e5",
        cursor: "pointer",
    }),

    singleValue: (base) => ({
        ...base,
        color: "#f5f5f5",
    }),

    dropdownIndicator: (base) => ({
        ...base,
        color: "#a3a3a3",
        ":hover": { color: "#e5e5e5" },
    }),

    indicatorSeparator: () => ({ display: "none" }),
};


// ---------------- LEGAL PAGE ----------------

export default function LegalPage() {
    const { policyKey } = useParams();
    const navigate = useNavigate();

    const activePolicy = policyKey || DEFAULT_POLICY;

    const { data, meta, loading, error } = usePolicy(activePolicy);

    // ensure URL always has policy
    useEffect(() => {
        if (!policyKey) {
            navigate(`/legal/${DEFAULT_POLICY}`, { replace: true });
        }
    }, [policyKey, navigate]);

    if (loading) {
        return (
            <div className="mx-auto max-w-3xl p-6">
                Loading policy...
            </div>
        );
    }

    if (error) {
        return (
            <div className="mx-auto max-w-3xl p-6 text-red-400">
                Error: {error}
            </div>
        );
    }

    return (
        <div className="mx-auto max-w-3xl px-6 py-10">
            <h1 className="text-3xl font-semibold text-neutral-100">
                Legal
            </h1>

            {/* selector */}
            <PolicySelect activePolicy={activePolicy} />

            <div className="mt-8">
                <h2 className="text-xl font-medium text-neutral-100">
                    {meta?.title}
                </h2>

                <div className="mt-8 prose prose-invert max-w-none">
                    {data?.html && (
                        <div dangerouslySetInnerHTML={{ __html: data.html }} />
                    )}

                    {data?.markdown && (
                        <PolicyContentRenderer markdown={data} />
                    )}
                </div>
            </div>
        </div>
    );
}