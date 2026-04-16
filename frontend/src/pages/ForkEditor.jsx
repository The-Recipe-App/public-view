import React, { useState, useMemo, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { GitFork, Lock, Trash2, ArrowUp, ArrowDown, Clock } from "lucide-react";
import { useContextManager } from "../features/ContextProvider";
import { useRecipe } from "../components/recipe/recipeData";
import backendUrlV1 from "../urls/backendUrl";

/* ═══════════════════════════════════════════════════════════
   NORMALISE  - API shape → editor shape
═══════════════════════════════════════════════════════════ */

function normaliseRecipeForEditor(raw) {
    if (!raw) return null;
    return {
        id: raw.id,
        slug: raw.id,   // API has no slug field yet; fall back to id for navigation
        title: raw.title,
        body: raw.body ?? "",
        author: {
            username: raw.author.username,
            avatar_url: raw.author.avatar_url,
        },
        media: {
            imageUrl: raw.media?.images?.[0]
                ? raw.media.images[0].startsWith("/")
                    ? `${backendUrlV1.replace("/api/v1", "")}${raw.media.images[0]}`
                    : raw.media.images[0]
                : null,
        },
        // Keep as objects: { id, name, is_animal, is_allergen }
        ingredients: raw.ingredients ?? [],
        // Keep as objects: { step_number, instruction, technique, estimated_minutes }
        steps: raw.steps ?? [],
    };
}

/* ═══════════════════════════════════════════════════════════
   DIFF LOGIC
═══════════════════════════════════════════════════════════ */

function generateDiff(original, editedIngredients, editedSteps) {
    const origIngNames = original.ingredients.map(i => i.name);
    const editIngNames = editedIngredients.map(i => i.name?.trim()).filter(Boolean);
    const origStepTexts = original.steps.map(s => s.instruction);
    const editStepTexts = editedSteps.map(s => s.instruction?.trim()).filter(Boolean);

    return {
        ingredients: {
            added: editIngNames.filter(n => !origIngNames.includes(n)),
            removed: origIngNames.filter(n => !editIngNames.includes(n)),
        },
        steps: {
            added: editStepTexts.filter(t => !origStepTexts.includes(t)),
            removed: origStepTexts.filter(t => !editStepTexts.includes(t)),
        },
    };
}

function diffCount(diff) {
    return (
        diff.ingredients.added.length +
        diff.ingredients.removed.length +
        diff.steps.added.length +
        diff.steps.removed.length
    );
}

/* ═══════════════════════════════════════════════════════════
   TINY ATOMS
═══════════════════════════════════════════════════════════ */

function Label({ children, className = "" }) {
    return (
        <p className={`text-[10px] font-semibold uppercase tracking-[0.1em] text-amber-500/70 mb-2 ${className}`}>
            {children}
        </p>
    );
}

function AddBtn({ onClick, label }) {
    return (
        <button
            onClick={onClick}
            className="w-full py-3 rounded-2xl border border-dashed border-[#858585] text-[#dadada] text-xs
                hover:border-amber-500/30 hover:text-amber-500/60 transition-all duration-200"
        >
            + {label}
        </button>
    );
}

/* ═══════════════════════════════════════════════════════════
   CONTEXT STRIP
═══════════════════════════════════════════════════════════ */

function ContextStrip({ original }) {
    return (
        <div className="flex items-center gap-4 px-4 py-3.5 rounded-2xl border border-[#1a1a1a] bg-[#080808]">
            <div className="w-12 h-12 rounded-xl overflow-hidden flex-shrink-0 border border-[#1a1a1a] bg-[#0f0f0f]">
                {original.media?.imageUrl ? (
                    <img src={original.media.imageUrl} alt={original.title}
                        className="w-full h-full object-cover" />
                ) : (
                    <div className="w-full h-full flex items-center justify-center text-[#1f1f1f] text-xl">⬡</div>
                )}
            </div>
            <div className="flex-1 min-w-0">
                <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-amber-500/80 mb-0.5">
                    Forking
                </p>
                <p className="text-white/85 text-sm font-semibold truncate leading-tight"
                    style={{ fontFamily: "'Georgia', serif" }}>
                    {original.title}
                </p>
                <p className="text-neutral-200 text-xs mt-0.5">by {original.author?.username}</p>
            </div>
            <div className="flex-shrink-0 w-8 h-8 rounded-full bg-amber-500/8 border border-amber-500/15
                flex items-center justify-center text-amber-500/40">
                <GitFork size={14} />
            </div>
        </div>
    );
}

/* ═══════════════════════════════════════════════════════════
   INTENT PICKER
═══════════════════════════════════════════════════════════ */

function IntentPicker({ mode, setMode }) {
    const opts = [
        {
            key: "copy",
            icon: "⎘",
            label: "Copy for myself",
            desc: "Save this privately. No credit needed, no changes required.",
        },
        {
            key: "evolve",
            icon: "✦",
            label: "Evolve publicly",
            desc: "Publish your variation. Credit the original, describe your changes.",
        },
    ];

    return (
        <div>
            <Label>What are you doing?</Label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {opts.map(opt => {
                    const active = mode === opt.key;
                    return (
                        <button
                            key={opt.key}
                            onClick={() => setMode(opt.key)}
                            className={`flex flex-col gap-2.5 p-4 rounded-2xl border text-left transition-all duration-250
                                ${active
                                    ? "border-amber-500/40 bg-amber-500/5 shadow-[0_0_24px_rgba(232,160,32,0.06)]"
                                    : "border-[#181818] bg-[#0a0a0a] hover:border-[#252525]"
                                }`}
                        >
                            <div className="flex items-center gap-2.5">
                                <span className={`w-8 h-8 rounded-full border flex items-center justify-center text-sm transition-all duration-200
                                    ${active
                                        ? "border-amber-500/50 bg-amber-500/10 text-amber-400"
                                        : "border-[#222] bg-[#111] text-neutral-200"
                                    }`}>
                                    {opt.icon}
                                </span>
                                <span className={`text-sm font-semibold transition-colors ${active ? "text-amber-300/90" : "text-neutral-300"}`}>
                                    {opt.label}
                                </span>
                                <span className={`ml-auto w-3.5 h-3.5 rounded-full border flex items-center justify-center
                                    transition-all duration-200 flex-shrink-0
                                    ${active ? "border-amber-500 bg-amber-500" : "border-neutral-600"}`}>
                                    {active && <span className="w-1.5 h-1.5 rounded-full bg-black" />}
                                </span>
                            </div>
                            <p className={`text-xs leading-relaxed transition-colors ${active ? "text-neutral-400" : "text-neutral-200"}`}>
                                {opt.desc}
                            </p>
                        </button>
                    );
                })}
            </div>
        </div>
    );
}

/* ═══════════════════════════════════════════════════════════
   INGREDIENT EDITOR
   Operates on { id?, name, is_animal, is_allergen } - real API shape.
═══════════════════════════════════════════════════════════ */

function IngredientEditor({ ingredients, setIngredients }) {
    const upd = (i, field, val) => {
        const next = [...ingredients];
        next[i] = { ...next[i], [field]: val };
        setIngredients(next);
    };
    const add = () => setIngredients([...ingredients, { name: "", is_animal: false, is_allergen: false }]);
    const del = i => setIngredients(ingredients.filter((_, j) => j !== i));

    return (
        <div>
            <div className="flex items-center gap-2 mb-4">
                <span className="text-amber-500/50 text-base leading-none">◈</span>
                <div>
                    <p className="text-white/80 text-sm font-semibold">Ingredients</p>
                    <p className="text-neutral-200 text-xs mt-0.5">Edit, add, or remove ingredients.</p>
                </div>
            </div>
            <div className="flex flex-col gap-2">
                {ingredients.map((ing, i) => (
                    <IngRow key={ing.id ?? i} ing={ing} idx={i} onUpd={upd} onDel={del} />
                ))}
            </div>
            <div className="mt-3">
                <AddBtn onClick={add} label="Add ingredient" />
            </div>
        </div>
    );
}

function IngRow({ ing, idx, onUpd, onDel }) {
    return (
        <div className="flex items-center gap-2 px-4 py-3 rounded-2xl border border-[#424242] 
            hover:border-[#222] transition-all duration-200 group">
            <span className="text-amber-500/85 text-[8px] flex-shrink-0">●</span>

            <input
                value={ing.name}
                onChange={e => onUpd(idx, "name", e.target.value)}
                placeholder="Ingredient name"
                className="flex-1 bg-transparent text-neutral-200 text-sm outline-none py-1
                    placeholder-neutral-600 focus:text-white transition-colors min-w-0"
            />

            <div className="flex items-center gap-1.5 flex-shrink-0">
                <button
                    onClick={() => onUpd(idx, "is_allergen", !ing.is_allergen)}
                    title="Toggle allergen"
                    className={`text-[9px] px-1.5 py-0.5 rounded-full border transition-all duration-150
                        ${ing.is_allergen
                            ? "border-orange-500/30 bg-orange-500/8 text-orange-400/70"
                            : "border-[#1f1f1f] text-neutral-200 hover:border-[#2a2a2a]"
                        }`}
                >
                    ⚠ allergen
                </button>
                <button
                    onClick={() => onUpd(idx, "is_animal", !ing.is_animal)}
                    title="Toggle animal-derived"
                    className={`text-[9px] px-1.5 py-0.5 rounded-full border transition-all duration-150
                        ${ing.is_animal
                            ? "border-emerald-500/30 bg-emerald-500/8 text-emerald-400/70"
                            : "border-[#1f1f1f] text-neutral-200 hover:border-[#2a2a2a]"
                        }`}
                >
                    🌿 animal
                </button>
            </div>

            <button
                onClick={() => onDel(idx)}
                className="flex-shrink-0 text-neutral-700 hover:text-red-400/70 transition-colors
                    opacity-0 group-hover:opacity-100"
                aria-label="Remove ingredient"
            >
                <Trash2 size={13} />
            </button>
        </div>
    );
}

/* ═══════════════════════════════════════════════════════════
   STEP EDITOR
   Operates on { step_number, instruction, technique, estimated_minutes }
═══════════════════════════════════════════════════════════ */

function StepEditor({ steps, setSteps }) {
    const upd = (i, field, val) => {
        const next = [...steps];
        next[i] = { ...next[i], [field]: val };
        setSteps(next);
    };
    const add = () => setSteps([...steps, {
        step_number: steps.length + 1,
        instruction: "",
        technique: "",
        estimated_minutes: null,
    }]);
    const del = i => {
        const next = steps.filter((_, j) => j !== i).map((s, j) => ({ ...s, step_number: j + 1 }));
        setSteps(next);
    };
    const mv = (i, d) => {
        const next = [...steps]; const j = i + d;
        if (j < 0 || j >= next.length) return;
        [next[i], next[j]] = [next[j], next[i]];
        setSteps(next.map((s, k) => ({ ...s, step_number: k + 1 })));
    };

    return (
        <div>
            <div className="flex items-center gap-2 mb-4">
                <span className="text-amber-500/80 text-base leading-none">◎</span>
                <div>
                    <p className="text-white/80 text-sm font-semibold">Steps</p>
                    <p className="text-neutral-200 text-xs mt-0.5">Reorder or rewrite each step.</p>
                </div>
            </div>
            <div className="flex flex-col gap-0">
                {steps.map((step, i) => (
                    <StepEditorRow
                        key={step.step_number ?? i}
                        step={step} idx={i} total={steps.length}
                        onUpd={upd} onDel={del} onMv={mv}
                    />
                ))}
            </div>
            <div className="flex gap-3 mt-3">
                <div className="w-8 flex-shrink-0" />
                <div className="flex-1">
                    <AddBtn onClick={add} label="Add step" />
                </div>
            </div>
        </div>
    );
}

function StepEditorRow({ step, idx, total, onUpd, onDel, onMv }) {
    const [focused, setFocused] = useState(false);

    return (
        <div className="flex gap-3 items-start">
            {/* Number + connector */}
            <div className="flex flex-col items-center flex-shrink-0 w-8">
                <div className={`w-8 h-8 rounded-full text-xs font-bold flex items-center justify-center
                    transition-all duration-300 flex-shrink-0
                    ${focused
                        ? "bg-amber-500 text-black shadow-[0_0_14px_rgba(232,160,32,0.2)]"
                        : "bg-[#111] border border-[#222] text-amber-500/40"
                    }`}>
                    {idx + 1}
                </div>
                {idx < total - 1 && (
                    <div className="w-px flex-1 my-1 bg-gradient-to-b from-amber-500/20 to-transparent"
                        style={{ minHeight: 20 }} />
                )}
            </div>

            {/* Card */}
            <div className={`flex-1 min-w-0 mb-3 rounded-2xl border transition-all duration-200
                ${focused ? "border-[#858585] bg-[#0d0d0d]" : "border-[#424242]"}`}>

                <div className="flex items-start gap-2 px-4 py-3 group">
                    <textarea
                        value={step.instruction}
                        rows={focused ? 3 : 1}
                        onChange={e => onUpd(idx, "instruction", e.target.value)}
                        onFocus={() => setFocused(true)}
                        onBlur={() => setFocused(false)}
                        placeholder={`Step ${idx + 1}…`}
                        className="flex-1 bg-transparent text-sm text-neutral-200 outline-none resize-none
                            placeholder-neutral-600 leading-relaxed py-0.5 transition-all duration-200
                            focus:text-white min-w-0"
                        style={{ minHeight: 24 }}
                    />
                    <div className={`flex items-center gap-1 flex-shrink-0 transition-opacity duration-200
                        ${focused ? "opacity-100" : "opacity-0 group-hover:opacity-100"}`}>
                        <button onClick={() => onMv(idx, -1)} disabled={idx === 0}
                            className="w-6 h-6 rounded-lg border border-[#222] text-neutral-200
                                flex items-center justify-center hover:border-neutral-500 hover:text-neutral-400
                                disabled:opacity-80 disabled:cursor-not-allowed transition-all">
                            <ArrowUp size={10} />
                        </button>
                        <button onClick={() => onMv(idx, 1)} disabled={idx === total - 1}
                            className="w-6 h-6 rounded-lg border border-[#222] text-neutral-200
                                flex items-center justify-center hover:border-neutral-500 hover:text-neutral-400
                                disabled:opacity-80 disabled:cursor-not-allowed transition-all">
                            <ArrowDown size={10} />
                        </button>
                        <button onClick={() => onDel(idx)}
                            className="w-6 h-6 rounded-lg border border-[#222] text-neutral-200
                                flex items-center justify-center hover:border-red-500/90 hover:text-red-400/80 transition-all">
                            <Trash2 size={10} />
                        </button>
                    </div>
                </div>

                {/* Technique + duration - editable when focused */}
                {focused && (
                    <div className="px-4 pb-3 flex items-center gap-3 border-t border-[#111] pt-3">
                        <input
                            value={step.technique ?? ""}
                            onChange={e => onUpd(idx, "technique", e.target.value)}
                            placeholder="Technique (e.g. Baking)"
                            className="flex-1 bg-transparent text-xs text-neutral-400 outline-none
                                border-b border-[#222] py-1 focus:border-amber-500/30
                                placeholder-neutral-700 transition-colors"
                        />
                        <div className="flex items-center gap-1.5 flex-shrink-0">
                            <Clock size={10} className="text-neutral-200" />
                            <input
                                type="number"
                                value={step.estimated_minutes ?? ""}
                                onChange={e => onUpd(idx, "estimated_minutes", e.target.value ? parseInt(e.target.value) : null)}
                                placeholder="mins"
                                className="w-16 bg-transparent text-xs text-neutral-400 outline-none
                                    border-b border-[#222] py-1 focus:border-amber-500/30
                                    placeholder-neutral-700 transition-colors text-center"
                            />
                        </div>
                    </div>
                )}

                {/* Collapsed metadata preview */}
                {!focused && (step.technique || step.estimated_minutes != null) && (
                    <div className="px-4 pb-2.5 flex items-center gap-2">
                        {step.technique && (
                            <span className="text-[9px] text-amber-400/80 bg-amber-500/6 border border-amber-500/10
                                rounded-full px-2 py-0.5 capitalize">
                                {step.technique}
                            </span>
                        )}
                        {step.estimated_minutes != null && (
                            <span className="text-[9px] text-neutral-200 flex items-center gap-1">
                                <Clock size={9} /> {step.estimated_minutes}m
                            </span>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}

/* ═══════════════════════════════════════════════════════════
   CHANGE SUMMARY
═══════════════════════════════════════════════════════════ */

function ChangeSummary({ summary, setSummary }) {
    const len = summary.trim().length;
    const ok = len >= 5;

    return (
        <div className="rounded-2xl border border-[#1a1a1a] bg-[#0a0a0a] p-4">
            <div className="flex items-center gap-2 mb-3">
                <span className="text-amber-500/50 text-sm">✦</span>
                <p className="text-white/80 text-sm font-semibold">What changed?</p>
            </div>
            <div className="fk-input-wrap">
                <textarea
                    value={summary}
                    onChange={e => setSummary(e.target.value)}
                    rows={3}
                    placeholder="e.g. Reduced oil by half, added garlic tempering, toasted buns"
                    className="fk-field resize-none"
                />
            </div>
            <div className="flex items-center justify-between mt-2">
                <p className={`text-[10px] transition-colors ${ok ? "text-emerald-500/50" : "text-neutral-200"}`}>
                    {ok ? "✓ Good - readers will see this" : "At least 5 characters required"}
                </p>
                <span className={`text-[10px] transition-colors ${len > 200 ? "text-orange-400/60" : "text-neutral-200"}`}>
                    {len}/200
                </span>
            </div>
        </div>
    );
}

/* ═══════════════════════════════════════════════════════════
   LOADING / ERROR STATES
═══════════════════════════════════════════════════════════ */

function ForkSkeleton() {
    return (
        <div className="max-w-[720px] mx-auto px-4 sm:px-6 py-8 flex flex-col gap-8 animate-pulse">
            <div className="h-16 rounded-2xl bg-neutral-900" />
            <div className="h-4 w-32 bg-neutral-900 rounded" />
            <div className="grid grid-cols-2 gap-3">
                <div className="h-24 rounded-2xl bg-neutral-900" />
                <div className="h-24 rounded-2xl bg-neutral-900" />
            </div>
            <div className="space-y-2">
                {Array.from({ length: 4 }).map((_, i) => (
                    <div key={i} className="h-11 rounded-2xl bg-neutral-900" />
                ))}
            </div>
            <div className="space-y-3">
                {Array.from({ length: 3 }).map((_, i) => (
                    <div key={i} className="h-14 rounded-2xl bg-neutral-900" />
                ))}
            </div>
        </div>
    );
}

function ForkError({ error, onRetry }) {
    return (
        <div className="max-w-[720px] mx-auto px-6 py-16 text-center">
            <p className="text-neutral-200 text-sm mb-4">
                {error?.status === 404
                    ? "That recipe doesn't exist or has been removed."
                    : "Something went wrong loading this recipe."}
            </p>
            {error?.status !== 404 && (
                <button onClick={onRetry}
                    className="px-4 py-2 rounded-xl border border-[#222] text-neutral-400 text-xs
                        hover:border-[#333] transition-colors">
                    Try again
                </button>
            )}
        </div>
    );
}

/* ═══════════════════════════════════════════════════════════
   ROOT
═══════════════════════════════════════════════════════════ */

export default function ForkEditor() {
    const { id } = useParams();
    const navigate = useNavigate();
    const { isAuthorized } = useContextManager();

    const { data: rawRecipe, loading, error, reload } = useRecipe(id);

    const original = useMemo(
        () => rawRecipe ? normaliseRecipeForEditor(rawRecipe) : null,
        [rawRecipe],
    );

    const [mode, setMode] = useState("evolve");
    const [ingredients, setIngredients] = useState(null);  // null = not yet seeded
    const [steps, setSteps] = useState(null);
    const [summary, setSummary] = useState("");
    const [submitting, setSubmitting] = useState(false);
    const [submitError, setSubmitError] = useState(null);

    // Seed editor state once original arrives
    useEffect(() => {
        if (original && ingredients === null) {
            setIngredients(original.ingredients.map(i => ({ ...i })));
            setSteps(original.steps.map(s => ({ ...s })));
        }
    }, [original]);

    const publishFork = async () => {
        if (mode === "evolve" && summary.trim().length < 5) {
            alert("Please describe what you changed.");
            return;
        }
        setSubmitting(true);
        setSubmitError(null);

        const payload = {
            parent_id: original.id,
            mode,
            summary: mode === "evolve" ? summary.trim() : null,
            is_draft: mode === "copy",
            ingredients: ingredients.filter(i => i.name?.trim()).map(i => ({
                name: i.name.trim(),
                is_animal: i.is_animal ?? false,
                is_allergen: i.is_allergen ?? false,
            })),
            steps: steps.filter(s => s.instruction?.trim()).map((s, idx) => ({
                step_number: idx + 1,
                instruction: s.instruction.trim(),
                technique: s.technique || null,
                estimated_minutes: s.estimated_minutes ?? null,
            })),
        };

        try {
            const res = await fetch(`${backendUrlV1}/recipes/${original.id}/fork`, {
                method: "POST",
                credentials: "include",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            const json = await res.json();
            if (!res.ok) throw new Error(json.detail ?? "Failed to publish fork");
            navigate(`/recipes/${json.recipe_id ?? json.id ?? original.slug}`);
        } catch (e) {
            setSubmitError(e.message);
            setSubmitting(false);
        }
    };

    /* ── Unauthorised ── */
    if (!isAuthorized) {
        return (
            <div className="min-h-screen bg-black flex items-center justify-center px-6">
                <div className="text-center max-w-xs">
                    <div className="w-16 h-16 rounded-full bg-amber-500/8 border border-amber-500/15
                        flex items-center justify-center text-amber-500/40 mx-auto mb-6">
                        <Lock size={28} />
                    </div>
                    <h2 className="text-white text-xl font-semibold mb-2"
                        style={{ fontFamily: "'Georgia', serif" }}>
                        Sign in to fork
                    </h2>
                    <p className="text-neutral-200 text-sm leading-relaxed mb-6">
                        You need an account to fork and evolve recipes on Forkit.
                    </p>
                    <button
                        onClick={() => {
                            localStorage.setItem("redirectAfterLogin", window.location.pathname);
                            navigate("/login");
                        }}
                        className="px-6 py-3 rounded-2xl bg-amber-500 text-black text-sm font-semibold
                            hover:bg-amber-400 transition-colors"
                    >
                        Sign in
                    </button>
                </div>
            </div>
        );
    }

    /* ── Loading / error ── */
    if (loading) return <div className="min-h-screen"><ForkSkeleton /></div>;
    if (error || !original) return <div className="min-h-screen"><ForkError error={error} onRetry={reload} /></div>;
    if (!ingredients || !steps) return <div className="min-h-screen"><ForkSkeleton /></div>;

    const diff = generateDiff(original, ingredients, steps);
    const changes = diffCount(diff);

    return (
        <div className="min-h-screen">
            <div className="max-w-[720px] mx-auto px-4 sm:px-6 py-8 flex flex-col gap-8">

                <ContextStrip original={original} />
                <IntentPicker mode={mode} setMode={setMode} />

                {/* edit divider */}
                <div className="flex items-center gap-3">
                    <div className="flex-1 h-px bg-gradient-to-r from-transparent via-[#5e5e5e] to-transparent" />
                    <span className="text-[10px] text-neutral-200 tracking-widest uppercase">edit</span>
                    <div className="flex-1 h-px bg-gradient-to-r from-transparent via-[#5e5e5e] to-transparent" />
                </div>

                <IngredientEditor ingredients={ingredients} setIngredients={setIngredients} />

                {/* then divider */}
                <div className="flex items-center gap-3">
                    <div className="flex-1 h-px bg-gradient-to-r from-transparent via-[#5e5e5e] to-transparent" />
                    <span className="text-[10px] text-neutral-200 tracking-widest uppercase">then</span>
                    <div className="flex-1 h-px bg-gradient-to-r from-transparent via-[#5e5e5e] to-transparent" />
                </div>

                <StepEditor steps={steps} setSteps={setSteps} />

                {mode === "evolve" && (
                    <ChangeSummary summary={summary} setSummary={setSummary} />
                )}

                {/* Publish row */}
                <div className="flex flex-col gap-3 pt-2">
                    {changes > 0 && (
                        <span className="flex items-center gap-1.5 text-[10px] text-amber-500/60
                            bg-amber-500/8 border border-amber-500/15 px-2.5 py-1 rounded-full w-fit">
                            <span className="w-1.5 h-1.5 rounded-full bg-amber-500/60" />
                            {changes} change{changes !== 1 ? "s" : ""} from original
                        </span>
                    )}

                    {submitError && (
                        <div className="bg-red-500/7 border border-red-500/15 rounded-xl px-4 py-3
                            text-red-400/70 text-xs">
                            {submitError}
                        </div>
                    )}

                    <button
                        onClick={publishFork}
                        disabled={submitting}
                        className="w-full py-4 rounded-2xl font-semibold text-sm text-black transition-all duration-300
                            bg-gradient-to-r from-amber-500 to-orange-500
                            shadow-[0_4px_24px_rgba(232,160,32,0.18)]
                            hover:shadow-[0_6px_32px_rgba(232,160,32,0.32)]
                            active:scale-[0.99] disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                        {submitting
                            ? <span className="flex items-center justify-center gap-2">
                                <span className="w-4 h-4 rounded-full border-2 border-black/30 border-t-black animate-spin" />
                                Publishing…
                            </span>
                            : <span className="flex items-center justify-center gap-2">
                                <GitFork size={14} />
                                {mode === "copy" ? "Save to my recipes" : "Publish fork"}
                            </span>
                        }
                    </button>

                    <button
                        onClick={() => navigate(-1)}
                        className="w-full py-3.5 rounded-2xl border border-[#1a1a1a] text-neutral-200 text-sm
                            hover:border-[#282828] hover:text-neutral-400 transition-all duration-200"
                    >
                        Cancel
                    </button>
                </div>

            </div>
        </div>
    );
}