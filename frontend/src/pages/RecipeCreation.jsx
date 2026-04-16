import { useState, useRef, useCallback, useEffect } from "react";
import { useMe } from "../hooks/useMe";
import backendUrlV1 from "../urls/backendUrl";
import { useContentLicense } from "../hooks/contentLicense/contentLicense";
import { useContextManager } from "../features/ContextProvider";
import RequireAuthGate from "../components/auth/RequireAuthGate";
import { useNavigate } from "react-router-dom";
import { ArrowRightFromLine } from "lucide-react";

/* ═══════════════════════════════════════════════════════════
    CONSTANTS
═══════════════════════════════════════════════════════════ */
const PLAN_LIMITS = {
    FREE: { images: 5, videos: 0, stepImages: false, allowVideos: false },
    CREATOR: { images: 15, videos: 0, stepImages: false, allowVideos: false },
    PRO: { images: 50, videos: 5, stepImages: true, allowVideos: true },
    ORG: { images: 500, videos: 100, stepImages: true, allowVideos: true },
};

const PLAN_COLOR = { FREE: "#555", CREATOR: "#38bdf8", PRO: "#e8a020", ORG: "#a78bfa" };

const TECHNIQUES = [
    "Prep", "Melting", "Folding", "Baking", "Roasting", "Frying",
    "Sautéing", "Simmering", "Boiling", "Steaming", "Chilling",
    "Resting", "Marinating", "Blending", "Plating", "Grilling",
];

const DEFAULT_TAGS = ["Quick", "Comfort", "Vegan", "Low salt", "Baking", "Spicy", "Healthy", "Dessert"];

/* 4 stages - Ingredients & Steps merged into one "Recipe" stage */
const STAGES = [
    { key: "details", label: "Details" },
    { key: "recipe", label: "Recipe" },
    { key: "media", label: "Media" },
    { key: "publish", label: "Publish" },
];

const STAGE_HINTS = [
    "Give it a name worth forking. Add tags and a short description.",
    "List every ingredient, then walk through each step.",
    "Show the world what it looks like.",
    "Choose a license, review everything, then send it live.",
];

const BLANK = {
    title: "", body: "", prepTime: "", servings: "", tags: [], customTags: [],
    licenseId: null,
    imageFiles: [], videoFiles: [],
    ingredients: [{ name: "", quantity: "", unit: "", is_animal: false, is_allergen: false }],
    steps: [{ instruction: "", technique: "", estimated_minutes: "", imageFile: null }],
};

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

function Field({ as = "input", className = "", ...p }) {
    const Tag = as;
    return (
        <div className="fk-input-wrap">
            <Tag {...p} className={`fk-field ${className}`} />
        </div>
    );
}

function Pill({ active, onClick, children, variant = "amber", className = "" }) {
    return (
        <button
            onClick={onClick}
            className={`fk-pill ${active ? "active" : ""} ${variant !== "amber" ? variant : ""} ${className}`}
        >
            {children}
        </button>
    );
}

function SectionDivider({ icon, label, sub = "" }) {
    return (
        <div className="flex items-center gap-3 mb-1">
            {icon && <span className="text-amber-500/60 text-base leading-none">{icon}</span>}
            <div>
                <p className="text-white/80 text-sm font-semibold leading-tight">{label}</p>
                {sub && <p className="text-neutral-300 text-xs mt-0.5">{sub}</p>}
            </div>
        </div>
    );
}

function AddBtn({ onClick, label, className = "" }) {
    return (
        <button
            onClick={onClick}
            className={`w-full py-3 rounded-2xl border border-dashed border-[#979090] text-[#afafaf] text-xs
        hover:border-amber-500/30 hover:text-amber-500/60 transition-all duration-250 ${className}`}
        >
            + {label}
        </button>
    );
}

/* ═══════════════════════════════════════════════════════════
   PROGRESS BAR
   Thin ambient strip at the very top; fills proportionally
   to how many required fields are touched.
═══════════════════════════════════════════════════════════ */
function ProgressBar({ stage, data }) {
    const pct = (() => {
        // weight each stage equally (25 pts each), then add partial credit within
        const base = stage * 25;
        const inStage = (() => {
            if (stage === 0) return data.title.trim() ? 25 : (data.body.trim() ? 10 : 0);
            if (stage === 1) {
                const hasIng = data.ingredients.some(i => i.name.trim());
                const hasStep = data.steps.some(s => s.instruction.trim());
                return (hasIng ? 12 : 0) + (hasStep ? 13 : 0);
            }
            if (stage === 2) return data.imageFiles.length > 0 ? 25 : 5;
            return 25;
        })();
        return Math.min(100, base + inStage);
    })();

    return (
        <div className="h-[2px] w-full bg-[#111] flex-shrink-0 relative overflow-hidden">
            <div
                className="absolute inset-y-0 left-0 bg-gradient-to-r from-amber-500 to-orange-400 transition-all duration-700 ease-out"
                style={{ width: `${pct}%` }}
            />
        </div>
    );
}

/* ═══════════════════════════════════════════════════════════
   STAGE 0 - DETAILS  (no license here anymore)
═══════════════════════════════════════════════════════════ */
function StageDetails({ data, setData }) {
    const [customInput, setCustomInput] = useState("");
    const set = (k, v) => setData(d => ({ ...d, [k]: v }));
    const allTags = [...DEFAULT_TAGS, ...data.customTags];

    const toggleTag = t => set("tags", data.tags.includes(t) ? data.tags.filter(x => x !== t) : [...data.tags, t]);

    const addCustomTag = () => {
        const val = customInput.trim();
        if (!val || data.customTags.includes(val) || DEFAULT_TAGS.includes(val)) { setCustomInput(""); return; }
        setData(d => ({ ...d, customTags: [...d.customTags, val], tags: [...d.tags, val] }));
        setCustomInput("");
    };

    return (
        <div className="flex flex-col gap-7">
            {/* Name */}
            <div>
                <Label>Recipe name</Label>
                <Field
                    placeholder="e.g. Brown Butter Chocolate Chip Cookies"
                    value={data.title}
                    onChange={e => set("title", e.target.value)}
                    autoFocus
                />
            </div>

            {/* Description */}
            <div>
                <Label>Description <span className="normal-case text-neutral-500 tracking-normal font-normal">- shows on card</span></Label>
                <Field as="textarea" rows={3} placeholder="What makes this worth making?"
                    value={data.body} onChange={e => set("body", e.target.value)} />
            </div>

            {/* Prep + servings */}
            <div className="grid grid-cols-2 gap-3">
                <div>
                    <Label>Prep time (mins)</Label>
                    <Field type="number" placeholder="20" value={data.prepTime} onChange={e => set("prepTime", e.target.value)} />
                </div>
                <div>
                    <Label>Servings</Label>
                    <Field type="number" placeholder="4" value={data.servings} onChange={e => set("servings", e.target.value)} />
                </div>
            </div>

            {/* Tags */}
            <div>
                <Label>Tags</Label>
                <div className="flex flex-wrap gap-2">
                    {allTags.map((t, i) => (
                        <span key={t} className="tag-pop" style={{ animationDelay: `${i * 0.03}s` }}>
                            <Pill active={data.tags.includes(t)} onClick={() => toggleTag(t)}>
                                {data.customTags.includes(t) && <span className="opacity-40 text-[9px]">✦</span>}
                                {t}
                            </Pill>
                        </span>
                    ))}
                    <div className="flex items-center gap-1">
                        <input
                            value={customInput}
                            onChange={e => setCustomInput(e.target.value)}
                            onKeyDown={e => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); addCustomTag(); } }}
                            placeholder="+ custom"
                            className="h-8 px-3 rounded-full border border-dashed border-[#222] bg-transparent
                                        text-[11px] text-neutral-600 placeholder-neutral-300 outline-none w-24
                                        focus:border-amber-500/30 focus:text-amber-500/60 transition-all duration-200"
                        />
                        {customInput.trim() && (
                            <button onClick={addCustomTag}
                                className="tag-pop w-7 h-7 rounded-full bg-amber-500/15 border border-amber-500/30
                                text-amber-500/70 text-sm flex items-center justify-center hover:bg-amber-500/25 transition-all">
                                ↵
                            </button>
                        )}
                    </div>
                </div>
                {data.customTags.length > 0 && (
                    <p className="text-[10px] text-neutral-500 mt-2 flex items-center gap-1.5">
                        <span className="text-amber-500/30">✦</span> custom tags
                    </p>
                )}
            </div>
        </div>
    );
}

/* ═══════════════════════════════════════════════════════════
   STAGE 1 - RECIPE  (Ingredients + Steps unified)
═══════════════════════════════════════════════════════════ */
function StageRecipe({ data, setData, plan }) {
    const lim = PLAN_LIMITS[plan] || PLAN_LIMITS.FREE;

    /* ── Ingredients ── */
    const addIng = () => setData(d => ({ ...d, ingredients: [...d.ingredients, { name: "", quantity: "", unit: "", is_animal: false, is_allergen: false }] }));
    const updIng = (i, f, v) => setData(d => { const n = [...d.ingredients]; n[i] = { ...n[i], [f]: v }; return { ...d, ingredients: n }; });
    const delIng = i => setData(d => ({ ...d, ingredients: d.ingredients.filter((_, j) => j !== i) }));

    /* ── Steps ── */
    const addStep = () => setData(d => ({ ...d, steps: [...d.steps, { instruction: "", technique: "", estimated_minutes: "", imageFile: null }] }));
    const updStep = (i, f, v) => setData(d => { const n = [...d.steps]; n[i] = { ...n[i], [f]: v }; return { ...d, steps: n }; });
    const delStep = i => setData(d => ({ ...d, steps: d.steps.filter((_, j) => j !== i) }));
    const mvStep = (i, dir) => setData(d => {
        const n = [...d.steps]; const j = i + dir;
        if (j < 0 || j >= n.length) return d;
        [n[i], n[j]] = [n[j], n[i]]; return { ...d, steps: n };
    });

    return (
        <div className="flex flex-col gap-10">
            {/* ── Ingredients section ── */}
            <section>
                <div className="flex items-center gap-3 mb-4">
                    <span className="text-amber-500/50 text-lg leading-none">◈</span>
                    <div>
                        <p className="text-white/80 text-sm font-semibold leading-tight">Ingredients</p>
                        <p className="text-neutral-400 text-xs mt-0.5">
                            Name, amount, and unit for each. Flag allergens so readers know upfront.
                        </p>
                    </div>
                </div>

                <div className="flex flex-col gap-2.5">
                    {data.ingredients.map((ing, i) => (
                        <IngCard key={i} ing={ing} idx={i}
                            isNew={i === data.ingredients.length - 1 && !ing.name}
                            onUpd={updIng} onDel={delIng} />
                    ))}
                </div>
                <div className="mt-3">
                    <AddBtn onClick={addIng} label="Add ingredient" />
                </div>
            </section>

            {/* ── Subtle divider ── */}
            <div className="flex items-center gap-3">
                <div className="flex-1 h-px bg-gradient-to-r from-transparent via-[#1f1f1f] to-transparent" />
                <span className="text-[10px] text-neutral-500 tracking-widest uppercase">then</span>
                <div className="flex-1 h-px bg-gradient-to-r from-transparent via-[#1f1f1f] to-transparent" />
            </div>

            {/* ── Steps section ── */}
            <section>
                <div className="flex items-center gap-3 mb-4">
                    <span className="text-amber-500/50 text-lg leading-none">◎</span>
                    <div>
                        <p className="text-white/80 text-sm font-semibold leading-tight">Steps</p>
                        <p className="text-neutral-400 text-xs mt-0.5">
                            Write each step clearly. Tag the technique and add timing{lim.stepImages ? " - PRO: attach a step photo" : ""}.
                        </p>
                    </div>
                </div>

                <div className="flex flex-col gap-3">
                    {data.steps.map((step, i) => (
                        <StepCard key={i} step={step} idx={i} total={data.steps.length}
                            isNew={i === data.steps.length - 1 && !step.instruction}
                            onUpd={updStep} onDel={delStep} onMv={mvStep} canStepImage={lim.stepImages} />
                    ))}
                </div>

                <div className="flex gap-3 mt-3">
                    <div className="w-8 flex-shrink-0" />
                    <AddBtn onClick={addStep} label="Add step" className="flex-1" />
                </div>
            </section>
        </div>
    );
}

/* ═══════════════════════════════════════════════════════════
   INGREDIENT CARD
═══════════════════════════════════════════════════════════ */
function IngCard({ ing, idx, isNew, onUpd, onDel }) {
    const [open, setOpen] = useState(isNew);
    return (
        <div className={`fk-card overflow-hidden`} style={open ? { borderColor: "#252525" } : {}}>
            <div className="flex items-center gap-3 px-4 py-3.5 cursor-pointer select-none" onClick={() => setOpen(o => !o)}>
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold flex-shrink-0 transition-all duration-300
                ${open ? "bg-amber-500 text-black" : "bg-amber-500/10 text-amber-500/50"}`}>
                    {idx + 1}
                </div>
                <div className="flex-1 min-w-0">
                    <p className={`text-sm truncate ${ing.name ? "text-white/90" : "text-[#9d9d9d]"}`}>
                        {ing.name || `Ingredient ${idx + 1}`}
                    </p>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                    {ing.is_allergen && <span className="text-orange-400/60 text-[10px]">⚠</span>}
                    {ing.is_animal && <span className="text-emerald-400/60 text-[10px]">🌿</span>}
                    {ing.quantity && <span className="text-neutral-300 text-[11px]">{ing.quantity}{ing.unit ? ` ${ing.unit}` : ""}</span>}
                    <span className={`text-[#ffffff] text-md transition-transform duration-300 ${open ? "rotate-180" : ""}`}>▾</span>
                </div>
            </div>
            {open && (
                <div className="accordion-body px-4 pb-4 flex flex-col gap-3 border-t border-[#111]">
                    <div className="pt-3">
                        <Field placeholder="Ingredient name" value={ing.name}
                            onChange={e => onUpd(idx, "name", e.target.value)} autoFocus={!ing.name} />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <Field placeholder="Amount" value={ing.quantity} onChange={e => onUpd(idx, "quantity", e.target.value)} />
                        <Field placeholder="Unit (g, cups…)" value={ing.unit} onChange={e => onUpd(idx, "unit", e.target.value)} />
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                        <Pill active={ing.is_allergen} onClick={() => onUpd(idx, "is_allergen", !ing.is_allergen)} variant="orange">⚠ Allergen</Pill>
                        <Pill active={ing.is_animal} onClick={() => onUpd(idx, "is_animal", !ing.is_animal)} variant="green">🌿 Animal-derived</Pill>
                        <button onClick={() => onDel(idx)}
                            className="ml-auto text-[10px] text-[#ffd7d7] hover:text-red-400/60 transition-colors">
                            Remove
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}

/* ═══════════════════════════════════════════════════════════
   STEP CARD
═══════════════════════════════════════════════════════════ */
function StepCard({ step, idx, total, isNew, onUpd, onDel, onMv, canStepImage }) {
    const [open, setOpen] = useState(isNew);
    const imgRef = useRef();

    const setStepImage = file => {
        if (!file) { onUpd(idx, "imageFile", null); return; }
        onUpd(idx, "imageFile", { file, url: URL.createObjectURL(file) });
    };

    return (
        <div className="flex gap-3 items-start">
            <div className="flex flex-col items-center flex-shrink-0 w-8">
                <div className={`w-8 h-8 rounded-full text-xs font-bold flex items-center justify-center transition-all duration-300 flex-shrink-0
                ${open ? "bg-amber-500 text-black step-num-open" : "bg-[#111] border border-[#222] text-amber-500/40"}`}>
                    {idx + 1}
                </div>
                {idx < total - 1 && (
                    <div className="connector-line w-px bg-gradient-to-b from-amber-500/25 to-transparent flex-1" style={{ minHeight: 16 }} />
                )}
            </div>
            <div className="flex-1 min-w-0">
                <div className={`fk-card overflow-hidden`} style={open ? { borderColor: "#252525" } : {}}>
                    <div className="flex items-start gap-2 px-4 py-3.5 cursor-pointer select-none" onClick={() => setOpen(o => !o)}>
                        <div className="flex-1 min-w-0">
                            <p className={`text-xs leading-snug ${step.instruction ? "text-white/60" : "text-neutral-500"}`}
                                style={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                                {step.instruction || "Describe this step…"}
                            </p>
                            <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                                {step.technique && (
                                    <span className="text-[9px] text-amber-600/70 bg-amber-500/8 border border-amber-500/12 rounded-full px-2 py-0.5">
                                        {step.technique}
                                    </span>
                                )}
                                {step.estimated_minutes && <span className="text-neutral-500 text-[10px]">⏱ {step.estimated_minutes}m</span>}
                            </div>
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                            {step.imageFile && (
                                <div className="w-8 h-8 rounded-lg overflow-hidden border border-[#222] flex-shrink-0">
                                    <img src={step.imageFile.url} className="w-full h-full object-cover" alt="" />
                                </div>
                            )}
                            <span className={`text-neutral-500 text-[11px] transition-transform duration-300 ${open ? "rotate-180" : ""}`}>▾</span>
                        </div>
                    </div>
                    {open && (
                        <div className="accordion-body px-4 pb-4 flex flex-col gap-4 border-t border-[#111]">
                            <div className="pt-3">
                                <Field as="textarea" rows={3} placeholder="Describe this step in detail…"
                                    value={step.instruction} onChange={e => onUpd(idx, "instruction", e.target.value)}
                                    autoFocus={!step.instruction} />
                            </div>
                            <div>
                                <Label>Technique</Label>
                                <div className="flex flex-wrap gap-1.5">
                                    {TECHNIQUES.map(t => (
                                        <Pill key={t} active={step.technique === t}
                                            onClick={() => onUpd(idx, "technique", step.technique === t ? "" : t)}>
                                            {t}
                                        </Pill>
                                    ))}
                                </div>
                            </div>
                            <div className="flex items-end gap-3 flex-wrap">
                                <div style={{ minWidth: 100, flex: 1 }}>
                                    <Label>Duration (mins)</Label>
                                    <Field type="number" placeholder="5" value={step.estimated_minutes}
                                        onChange={e => onUpd(idx, "estimated_minutes", e.target.value)} />
                                </div>
                                {canStepImage && (
                                    <div className="flex-shrink-0">
                                        <Label>Step photo</Label>
                                        <div className="flex items-center gap-2">
                                            {step.imageFile ? (
                                                <div className="media-thumb w-12 h-10 rounded-lg border border-[#222]">
                                                    <img src={step.imageFile.url} className="w-full h-full object-cover rounded-lg" alt="" />
                                                    <div className="overlay rounded-lg">
                                                        <button onClick={() => setStepImage(null)} className="text-white/60 text-lg hover:text-white transition-colors">×</button>
                                                    </div>
                                                </div>
                                            ) : (
                                                <button onClick={() => imgRef.current?.click()}
                                                    className="w-12 h-10 rounded-lg border border-dashed border-[#222] text-neutral-500
                                                    hover:border-amber-500/30 hover:text-amber-500/50 text-sm flex items-center justify-center transition-all duration-200">
                                                    ⬡
                                                </button>
                                            )}
                                        </div>
                                        <input ref={imgRef} type="file" accept="image/*" className="hidden"
                                            onChange={e => { const f = e.target.files?.[0]; if (f) setStepImage(f); e.target.value = ""; }} />
                                    </div>
                                )}
                                <div className="flex items-center gap-1 flex-shrink-0 pb-0.5">
                                    <button onClick={() => onMv(idx, -1)} disabled={idx === 0}
                                        className="w-8 h-8 rounded-full border border-neutral-400 text-neutral-500 text-sm
                                        flex items-center justify-center hover:border-neutral-500 hover:text-[#666] disabled:opacity-15 transition-all">↑</button>
                                    <button onClick={() => onMv(idx, 1)} disabled={idx === total - 1}
                                        className="w-8 h-8 rounded-full border border-neutral-400 text-neutral-500 text-sm
                                        flex items-center justify-center hover:border-neutral-500 hover:text-[#666] disabled:opacity-15 transition-all">↓</button>
                                    <button onClick={() => onDel(idx)} className="text-[10px] text-neutral-400 hover:text-red-400/60 transition-colors ml-1">
                                        Remove
                                    </button>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

/* ═══════════════════════════════════════════════════════════
   STAGE 2 - MEDIA
   • Video zone hidden entirely for plans without allowVideos
═══════════════════════════════════════════════════════════ */
function StageMedia({ data, setData, plan }) {
    const lim = PLAN_LIMITS[plan] || PLAN_LIMITS.FREE;
    const imgRef = useRef();
    const vidRef = useRef();
    const [imgOver, setImgOver] = useState(false);
    const [vidOver, setVidOver] = useState(false);
    const [dragIdx, setDragIdx] = useState(null);
    const [dropIdx, setDropIdx] = useState(null);

    const addImages = files => {
        const arr = Array.from(files).filter(f => f.type.startsWith("image/"));
        if (data.imageFiles.length + arr.length > lim.images) {
            alert(`${plan} plan: max ${lim.images} images.`); return;
        }
        setData(d => ({ ...d, imageFiles: [...d.imageFiles, ...arr.map(f => ({ file: f, url: URL.createObjectURL(f), name: f.name }))] }));
    };

    const addVideos = files => {
        const arr = Array.from(files).filter(f => f.type.startsWith("video/"));
        if (data.videoFiles.length + arr.length > lim.videos) {
            alert(`${plan} plan: max ${lim.videos} videos.`); return;
        }
        setData(d => ({ ...d, videoFiles: [...d.videoFiles, ...arr.map(f => ({ file: f, url: URL.createObjectURL(f), name: f.name }))] }));
    };

    const onThumbDragStart = (e, i) => { setDragIdx(i); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("thumb", "1"); };
    const onThumbDragOver = (e, i) => { e.preventDefault(); e.stopPropagation(); setDropIdx(i); };
    const onThumbDrop = (e, i) => {
        e.preventDefault(); e.stopPropagation();
        if (dragIdx === null || dragIdx === i) { setDragIdx(null); setDropIdx(null); return; }
        setData(d => {
            const next = [...d.imageFiles];
            const [moved] = next.splice(dragIdx, 1);
            next.splice(i, 0, moved);
            return { ...d, imageFiles: next };
        });
        setDragIdx(null); setDropIdx(null);
    };
    const onThumbDragEnd = () => { setDragIdx(null); setDropIdx(null); };
    const onZoneDragOver = e => { if (e.dataTransfer.types.includes("thumb")) return; e.preventDefault(); setImgOver(true); };
    const onZoneDrop = e => { if (e.dataTransfer.types.includes("thumb")) return; e.preventDefault(); setImgOver(false); addImages(e.dataTransfer.files); };

    return (
        <div className="flex flex-col gap-6">
            {/* Plan badge */}
            <div className="flex items-center gap-2.5 px-4 py-3 rounded-2xl border border-[#161616] bg-[#0a0a0a]">
                <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: PLAN_COLOR[plan] || "#555" }} />
                <span className="text-neutral-300 text-xs font-medium">{plan} plan</span>
                <div className="ml-auto flex items-center gap-3 text-[10px] text-neutral-500">
                    <span>{lim.images} image{lim.images !== 1 ? "s" : ""}</span>
                    {lim.allowVideos && <span>· {lim.videos} video{lim.videos !== 1 ? "s" : ""}</span>}
                    {lim.stepImages && <span>· Step photos ✓</span>}
                </div>
            </div>

            {/* Images */}
            <div>
                <SectionDivider icon="⬡" label="Images" sub={`${data.imageFiles.length} of ${lim.images} uploaded`} />
                <div className="mt-3">
                    <div
                        onDragOver={onZoneDragOver}
                        onDragLeave={() => setImgOver(false)}
                        onDrop={onZoneDrop}
                        onClick={() => imgRef.current?.click()}
                        className={`border border-dashed rounded-2xl px-6 py-8 flex flex-col items-center gap-3 cursor-pointer
                            transition-all duration-300 ${imgOver ? "dropzone-over" : "border-[#181818] hover:border-amber-500/70"}`}
                    >
                        <span className={`text-3xl transition-all duration-300 ${imgOver ? "text-amber-500/40" : "text-neutral-400"}`}>⬡</span>
                        <div className="text-center">
                            <p className={`text-xs transition-colors ${imgOver ? "text-amber-400/60" : "text-neutral-300"}`}>
                                Drag images here or <span className="text-amber-500/80">browse</span>
                            </p>
                            <p className="text-[10px] text-neutral-400 mt-1">JPG · PNG · WEBP · max 20 MB each</p>
                        </div>
                    </div>
                    <input ref={imgRef} type="file" accept="image/*" multiple className="hidden" onChange={e => addImages(e.target.files)} />
                </div>

                {data.imageFiles.length > 0 && (
                    <>
                        <p className="text-[12px] underline text-amber-400 mt-3 mb-2">Drag to reorder · First image is the cover</p>
                        <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
                            {data.imageFiles.map((img, i) => (
                                <div
                                    key={img.url}
                                    draggable
                                    onDragStart={e => onThumbDragStart(e, i)}
                                    onDragOver={e => onThumbDragOver(e, i)}
                                    onDrop={e => onThumbDrop(e, i)}
                                    onDragEnd={onThumbDragEnd}
                                    className="media-thumb aspect-square rounded-xl border bg-[#0d0d0d] cursor-grab active:cursor-grabbing transition-all duration-200"
                                    style={{
                                        borderColor: dropIdx === i && dragIdx !== i ? "rgba(232,160,32,0.6)" : dragIdx === i ? "rgba(255,255,255,0.08)" : "#1a1a1a",
                                        opacity: dragIdx === i ? 0.45 : 1,
                                        transform: dropIdx === i && dragIdx !== i ? "scale(1.03)" : "scale(1)",
                                    }}
                                >
                                    <img src={img.url} alt={img.name} className="w-full h-full object-cover rounded-xl" />
                                    {i === 0 && (
                                        <span className="absolute bottom-1 left-1 bg-amber-500 text-black text-[8px] font-bold px-1.5 py-0.5 rounded-full z-10 pointer-events-none">
                                            Cover
                                        </span>
                                    )}
                                    <div className="overlay rounded-xl">
                                        <button
                                            onClick={e => { e.stopPropagation(); setData(d => ({ ...d, imageFiles: d.imageFiles.filter((_, j) => j !== i) })); }}
                                            className="w-7 h-7 rounded-full bg-black/70 border border-white/10 text-white/70 text-sm
                                                flex items-center justify-center hover:text-white transition-colors"
                                        >×</button>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </>
                )}
            </div>

            {/* Videos - only rendered when plan supports them */}
            {lim.allowVideos && (
                <div>
                    <SectionDivider icon="▷" label="Videos" sub={`${data.videoFiles.length} of ${lim.videos}`} />
                    <div className="mt-3">
                        <div
                            onDragOver={e => { e.preventDefault(); setVidOver(true); }}
                            onDragLeave={() => setVidOver(false)}
                            onDrop={e => { e.preventDefault(); setVidOver(false); addVideos(e.dataTransfer.files); }}
                            onClick={() => vidRef.current?.click()}
                            className={`border border-dashed rounded-2xl px-6 py-8 flex flex-col items-center gap-3 cursor-pointer
                                transition-all duration-300 ${vidOver ? "dropzone-over" : "border-[#181818] hover:border-amber-500/60"}`}
                        >
                            <span className={`text-3xl transition-all duration-300 ${vidOver ? "text-amber-500/40" : "text-neutral-400"}`}>▷</span>
                            <div className="text-center">
                                <p className={`text-xs transition-colors ${vidOver ? "text-amber-400/60" : "text-neutral-300"}`}>
                                    Drag videos here or <span className="text-amber-500/80">browse</span>
                                </p>
                                <p className="text-[10px] text-neutral-400 mt-1">MP4 · MOV · WEBM · max 200 MB each</p>
                            </div>
                        </div>
                        <input ref={vidRef} type="file" accept="video/*" multiple className="hidden" onChange={e => addVideos(e.target.files)} />
                    </div>
                    {data.videoFiles.length > 0 && (
                        <div className="flex flex-col gap-2 mt-3">
                            {data.videoFiles.map((vid, i) => (
                                <div key={i} className="flex items-center gap-3 px-3 py-2.5 fk-card rounded-xl">
                                    <span className="text-amber-500/30 flex-shrink-0">▷</span>
                                    <span className="text-neutral-600 text-xs flex-1 truncate">{vid.name}</span>
                                    <button
                                        onClick={() => setData(d => ({ ...d, videoFiles: d.videoFiles.filter((_, j) => j !== i) }))}
                                        className="text-neutral-400 text-[10px] hover:text-red-400/60 transition-colors"
                                    >Remove</button>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

/* ═══════════════════════════════════════════════════════════
   STAGE 3 - PUBLISH  (now includes license picker)
═══════════════════════════════════════════════════════════ */
function StagePublish({ data, setData, licenses, onPublish, onDraft, submitting, error }) {
    const cover = data.imageFiles[0]?.url;
    const ings = data.ingredients.filter(i => i.name.trim());
    const steps = data.steps.filter(s => s.instruction.trim());
    const allTags = [...data.tags];
    const checks = [!!data.title.trim(), ings.length > 0, steps.length > 0];
    const pct = Math.round(checks.filter(Boolean).length / checks.length * 100);
    const ready = pct === 100;

    const set = (k, v) => setData(d => ({ ...d, [k]: v }));

    return (
        <div className="flex flex-col gap-6">
            {/* Readiness card */}
            <div className="fk-card p-4 flex items-center gap-5" style={ready ? { borderColor: "rgba(34,197,94,0.2)" } : {}}>
                <div className="relative w-16 h-16 flex-shrink-0">
                    <svg viewBox="0 0 36 36" className="w-16 h-16" style={{ transform: "rotate(-90deg)" }}>
                        <circle cx="18" cy="18" r="15.9" fill="none" stroke="#141414" strokeWidth="2.5" />
                        <circle cx="18" cy="18" r="15.9" fill="none"
                            stroke={ready ? "#22c55e" : "#e8a020"} strokeWidth="2.5"
                            strokeDasharray={`${pct} ${100 - pct}`} strokeLinecap="round"
                            className="ring-circle" />
                    </svg>
                    <span className="absolute inset-0 flex items-center justify-center text-xs font-bold"
                        style={{ color: ready ? "#22c55e" : "#e8a020" }}>{pct}%</span>
                </div>
                <div>
                    <p className="text-white/70 text-sm font-semibold mb-2">Recipe readiness</p>
                    {[["Title", checks[0]], ["Ingredients", checks[1]], ["Steps", checks[2]]].map(([l, ok]) => (
                        <div key={l} className="flex items-center gap-2 mb-1.5">
                            <span className={`w-3 h-3 rounded-full text-[7px] flex items-center justify-center flex-shrink-0
                ${ok ? "bg-emerald-500 text-black" : "bg-[#1a1a1a] text-transparent"}`}>{ok ? "✓" : ""}</span>
                            <span className={`text-xs ${ok ? "text-[#888]" : "text-neutral-300"}`}>{l}</span>
                        </div>
                    ))}
                </div>
            </div>

            {/* License - moved here from Details */}
            <div>
                <Label>How can others use this recipe?</Label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {licenses.map(lic => (
                        <button key={lic.id}
                            onClick={() => set("licenseId", lic.id === data.licenseId ? null : lic.id)}
                            className={`flex items-center gap-3 px-3 py-2.5 rounded-xl border text-left transition-all duration-200
                        ${data.licenseId === lic.id
                                    ? "border-amber-500/40 bg-amber-500/5"
                                    : "border-[#181818] hover:border-[#252525]"}`}
                        >
                            <span className={`w-3.5 h-3.5 rounded-full border flex-shrink-0 flex items-center justify-center transition-all duration-200
                        ${data.licenseId === lic.id ? "border-amber-500 bg-amber-500" : "border-neutral-500"}`}>
                                {data.licenseId === lic.id && <span className="w-1.5 h-1.5 rounded-full bg-black" />}
                            </span>
                            <div>
                                <p className={`text-xs font-medium leading-tight transition-colors ${data.licenseId === lic.id ? "text-amber-300/90" : "text-neutral-300"}`}>
                                    {lic.title ?? lic.label}
                                </p>
                                <p className="text-[10px] text-neutral-500 mt-0.5">{lic.desc}</p>
                            </div>
                        </button>
                    ))}
                </div>
            </div>

            {/* Recipe preview card */}
            <div className="fk-card p-0 overflow-hidden">
                {cover
                    ? <div className="h-40 w-full"><img src={cover} className="w-full h-full object-cover" alt="cover" /></div>
                    : <div className="h-40 flex items-center justify-center text-[#161616] text-4xl bg-[#0a0a0a] border-b border-[#111]">⬡</div>
                }
                <div className="p-4">
                    <h2 className="text-white/90 text-xl font-semibold leading-tight mb-1" style={{ fontFamily: "'Georgia',serif" }}>
                        {data.title || <span className="text-neutral-400">Untitled Recipe</span>}
                    </h2>
                    {data.body && <p className="text-neutral-300 text-xs leading-relaxed mb-3 line-clamp-2">{data.body}</p>}

                    <div className="flex flex-wrap gap-2 mb-3">
                        {data.prepTime && <span className="text-neutral-300 text-[10px] bg-[#0d0d0d] border border-[#141414] rounded-full px-2.5 py-1">⏱ {data.prepTime} min</span>}
                        {data.servings && <span className="text-neutral-300 text-[10px] bg-[#0d0d0d] border border-[#141414] rounded-full px-2.5 py-1">🍽 {data.servings} servings</span>}
                        {data.imageFiles.length > 0 && <span className="text-neutral-300 text-[10px] bg-[#0d0d0d] border border-[#141414] rounded-full px-2.5 py-1">⬡ {data.imageFiles.length} image{data.imageFiles.length !== 1 ? "s" : ""}</span>}
                    </div>

                    {allTags.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 mb-4">
                            {allTags.map(t => (
                                <span key={t} className="text-[9px] text-neutral-300 border border-[#141414] rounded-full px-2 py-0.5">{t}</span>
                            ))}
                        </div>
                    )}

                    {ings.length > 0 && (
                        <div className="border-t border-[#111] pt-3 mb-4">
                            <p className="text-neutral-500 text-[9px] uppercase tracking-widest mb-2">Ingredients</p>
                            {ings.slice(0, 5).map((ing, i) => (
                                <div key={i} className="flex items-center gap-2.5 py-1.5 border-b border-[#0d0d0d]">
                                    <span className="text-amber-500/25 text-[7px] flex-shrink-0">●</span>
                                    <span className="text-[#666] text-xs flex-1">{ing.name}</span>
                                    {(ing.is_allergen || ing.is_animal) && (
                                        <span className="flex gap-1">
                                            {ing.is_allergen && <span className="text-orange-400/50 text-[9px]">⚠</span>}
                                            {ing.is_animal && <span className="text-emerald-400/50 text-[9px]">🌿</span>}
                                        </span>
                                    )}
                                    <span className="text-neutral-300 text-[10px]">{ing.quantity} {ing.unit}</span>
                                </div>
                            ))}
                            {ings.length > 5 && <p className="text-neutral-400 text-[10px] mt-1.5">+{ings.length - 5} more</p>}
                        </div>
                    )}

                    {steps.length > 0 && (
                        <div className="border-t border-[#111] pt-3">
                            <p className="text-neutral-500 text-[9px] uppercase tracking-widest mb-3">Steps</p>
                            <div className="flex flex-col gap-3">
                                {steps.map((step, i) => (
                                    <div key={i} className="flex gap-3 items-start">
                                        <div className="flex flex-col items-center flex-shrink-0">
                                            <div className="w-5 h-5 rounded-full bg-amber-500/15 border border-amber-500/25 text-amber-500/60 text-[9px] font-bold flex items-center justify-center">{i + 1}</div>
                                            {i < steps.length - 1 && <div className="w-px h-3 bg-amber-500/15 mt-0.5" />}
                                        </div>
                                        <div className="flex-1 min-w-0 pb-1">
                                            <div className="flex items-start gap-2">
                                                <p className="text-neutral-600 text-xs leading-snug flex-1"
                                                    style={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                                                    {step.instruction}
                                                </p>
                                                {step.imageFile && (
                                                    <div className="w-10 h-8 rounded-lg overflow-hidden border border-[#1a1a1a] flex-shrink-0">
                                                        <img src={step.imageFile.url} className="w-full h-full object-cover" alt="" />
                                                    </div>
                                                )}
                                            </div>
                                            <div className="flex items-center gap-2 mt-1">
                                                {step.technique && <span className="text-[8px] text-amber-600/50 bg-amber-500/6 rounded-full px-1.5 py-0.5">{step.technique}</span>}
                                                {step.estimated_minutes && <span className="text-neutral-500 text-[9px]">⏱ {step.estimated_minutes}m</span>}
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            </div>

            {error && (
                <div className="bg-red-500/7 border border-red-500/15 rounded-xl px-4 py-3 text-red-400/70 text-xs">{error}</div>
            )}

            <button onClick={onPublish} disabled={submitting || !data.title.trim()}
                className={`w-full py-4 rounded-2xl font-semibold text-sm transition-all duration-300
                ${data.title.trim()
                        ? "bg-gradient-to-r from-amber-500 to-orange-500 text-black shadow-[0_4px_30px_rgba(232,160,32,0.2)] hover:shadow-[0_6px_40px_rgba(232,160,32,0.35)] active:scale-[0.99]"
                        : "bg-[#0d0d0d] text-neutral-400 border border-[#141414] cursor-not-allowed"}`}>
                {submitting
                    ? <span className="flex items-center justify-center gap-2">
                        <span className="w-4 h-4 rounded-full border-2 border-black/30 border-t-black spin" />
                        Publishing…
                    </span>
                    : "Publish"
                }
            </button>

            <button onClick={onDraft} disabled={submitting || !data.title.trim()}
                className="w-full py-3.5 rounded-2xl border border-[#707070] text-neutral-300 text-sm
                hover:border-orange-400 hover:text-orange-400 disabled:opacity-20 transition-all duration-200">
                Save as draft
            </button>
        </div>
    );
}

/* ═══════════════════════════════════════════════════════════
   LIVE PREVIEW PANEL  (desktop only, sticky alongside form)
   Shows a compact version of the recipe-in-progress.
═══════════════════════════════════════════════════════════ */
function LivePreview({ data }) {
    const cover = data.imageFiles[0]?.url;
    const ings = data.ingredients.filter(i => i.name.trim());
    const steps = data.steps.filter(s => s.instruction.trim());

    return (
        <div className="hidden lg:flex flex-col gap-4 sticky top-6 h-fit">
            {/* Header label */}
            <div className="flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-amber-500/60 animate-pulse" />
                <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-amber-500/50">Live preview</span>
            </div>

            {/* Card */}
            <div className="fk-card p-0 overflow-hidden">
                {/* Cover */}
                <div className="h-32 w-full overflow-hidden">
                    {cover
                        ? <img src={cover} className="w-full h-full object-cover" alt="cover" />
                        : <div className="w-full h-full bg-[#0a0a0a] flex items-center justify-center text-[#1a1a1a] text-5xl">⬡</div>
                    }
                </div>

                <div className="p-4 flex flex-col gap-3">
                    {/* Title */}
                    <h3 className="text-white/85 text-base font-semibold leading-snug" style={{ fontFamily: "'Georgia',serif" }}>
                        {data.title || <span className="text-neutral-500 italic font-normal text-sm">Untitled</span>}
                    </h3>

                    {/* Description */}
                    {data.body && (
                        <p className="text-neutral-400 text-[11px] leading-relaxed line-clamp-3">{data.body}</p>
                    )}

                    {/* Meta pills */}
                    {(data.prepTime || data.servings) && (
                        <div className="flex flex-wrap gap-1.5">
                            {data.prepTime && <span className="text-neutral-400 text-[9px] bg-[#0d0d0d] border border-[#141414] rounded-full px-2 py-0.5">⏱ {data.prepTime}m</span>}
                            {data.servings && <span className="text-neutral-400 text-[9px] bg-[#0d0d0d] border border-[#141414] rounded-full px-2 py-0.5">🍽 {data.servings}</span>}
                        </div>
                    )}

                    {/* Tags */}
                    {data.tags.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                            {data.tags.slice(0, 6).map(t => (
                                <span key={t} className="text-[9px] text-neutral-400 border border-[#1a1a1a] rounded-full px-1.5 py-0.5">{t}</span>
                            ))}
                            {data.tags.length > 6 && <span className="text-[9px] text-neutral-500">+{data.tags.length - 6}</span>}
                        </div>
                    )}

                    {/* Ingredient count */}
                    {ings.length > 0 && (
                        <div className="border-t border-[#111] pt-3">
                            <p className="text-[9px] text-neutral-500 uppercase tracking-widest mb-1.5">Ingredients</p>
                            {ings.slice(0, 4).map((ing, i) => (
                                <div key={i} className="flex items-center gap-2 py-1">
                                    <span className="text-amber-500/20 text-[6px]">●</span>
                                    <span className="text-neutral-500 text-[10px] flex-1 truncate">{ing.name}</span>
                                    <span className="text-neutral-600 text-[9px]">{ing.quantity} {ing.unit}</span>
                                </div>
                            ))}
                            {ings.length > 4 && <p className="text-neutral-600 text-[9px] mt-1">+{ings.length - 4} more</p>}
                        </div>
                    )}

                    {/* Step count */}
                    {steps.length > 0 && (
                        <div className="border-t border-[#111] pt-3">
                            <p className="text-[9px] text-neutral-500 uppercase tracking-widest mb-1">
                                {steps.length} step{steps.length !== 1 ? "s" : ""}
                            </p>
                            {steps.slice(0, 2).map((step, i) => (
                                <p key={i} className="text-neutral-600 text-[10px] leading-snug line-clamp-1 mb-1">
                                    <span className="text-amber-500/30 mr-1 font-bold">{i + 1}.</span>
                                    {step.instruction}
                                </p>
                            ))}
                            {steps.length > 2 && <p className="text-neutral-600 text-[9px]">+{steps.length - 2} more</p>}
                        </div>
                    )}

                    {/* Image count */}
                    {data.imageFiles.length > 1 && (
                        <div className="flex gap-1 mt-1">
                            {data.imageFiles.slice(1, 4).map((img, i) => (
                                <div key={i} className="w-10 h-8 rounded-lg overflow-hidden border border-[#1a1a1a] flex-shrink-0">
                                    <img src={img.url} className="w-full h-full object-cover" alt="" />
                                </div>
                            ))}
                            {data.imageFiles.length > 4 && (
                                <div className="w-10 h-8 rounded-lg border border-[#1a1a1a] flex items-center justify-center flex-shrink-0">
                                    <span className="text-neutral-600 text-[9px]">+{data.imageFiles.length - 4}</span>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

/* ═══════════════════════════════════════════════════════════
   SUCCESS SCREEN
═══════════════════════════════════════════════════════════ */
function SuccessScreen({ recipeId, onReset }) {
    const navigate = useNavigate();
    return (
        <div className="fk-root min-h-screen flex items-center justify-center px-6">
            <div className="fk-glow" />
            <div className="text-center max-w-xs mx-auto relative z-10">
                <div className="w-24 h-24 rounded-full bg-amber-500/10 border border-amber-500/60
                    flex items-center justify-center text-4xl mx-auto mb-8 burst-in">⑂</div>
                <h2 className="text-white text-2xl font-semibold mb-3 fade-up-d1" style={{ fontFamily: "'Georgia',serif" }}>
                    On the bench.
                </h2>
                <p className="text-neutral-300 text-sm leading-relaxed fade-up-d2">
                    Your recipe is live. The kitchen decides what works.
                </p>
                <div className="flex flex-col items-center">
                    <button onClick={onReset}
                        className="mt-10 px-7 py-3 rounded-2xl bg-amber-500 text-black text-sm font-semibold
                    hover:bg-amber-400 active:scale-[0.98] transition-all duration-200 fade-up-d3">
                        Create another
                    </button>
                    <a onClick={() => {
                        navigate(`/recipes/${recipeId}`);
                    }}
                        className="flex flex-row w-fit justify-center gap-x-2 mt-10 text-white text-sm
                        active:scale-[0.98] transition-all duration-200 fade-up-d hover:text-amber-500 hover:gap-x-3 hover:underline hover:cursor-pointer">
                        View recipe <ArrowRightFromLine size={20} /> 
                    </a>
                </div>
            </div>
        </div>
    );
}

/* ═══════════════════════════════════════════════════════════
    ROOT APP
═══════════════════════════════════════════════════════════ */
export default function RecipeCreate() {
    const userQuery = useMe();
    const usr_data = userQuery.data || {};
    const { plan } = usr_data;
    const { isAuthorized, setIsLoading } = useContextManager();
    const USER_PLAN = plan;

    const { licenses = [] } = useContentLicense();

    const [stage, setStage] = useState(0);
    const [animKey, setAnimKey] = useState(0);
    const [data, setData] = useState({ ...BLANK });
    const [submitting, setSub] = useState(false);
    const [submitError, setErr] = useState(null);
    const [done, setDone] = useState(false);

    const [recipeId, setRecipeId] = useState(null);

    useEffect(() => {
        setIsLoading(false);
    }, []);

    const goTo = useCallback((i) => {
        if (i === stage) return;
        setStage(i);
        setAnimKey(k => k + 1);
    }, [stage]);

    const submit = async (publish) => {
        if (!data.title.trim()) { setErr("A title is required."); return; }
        setSub(true); setErr(null);
        const payload = {
            title: data.title.trim(),
            body: data.body || null,
            is_draft: !publish,
            license_id: data.licenseId || null,
            ingredients: data.ingredients.filter(i => i.name.trim()).map(i => ({
                name: i.name.trim(), is_animal: i.is_animal, is_allergen: i.is_allergen,
            })),
            steps: data.steps.filter(s => s.instruction.trim()).map((s, idx) => ({
                step_number: idx + 1,
                instruction: s.instruction.trim(),
                technique: s.technique || null,
                estimated_minutes: parseInt(s.estimated_minutes) || 0,
            })),
            media: [],
        };
        const form = new FormData();
        form.append("data", JSON.stringify(payload));
        data.imageFiles.forEach(f => form.append("images", f.file));
        data.videoFiles.forEach(f => form.append("videos", f.file));

        try {
            const res = await fetch(`${backendUrlV1}/recipes/`, { method: "POST", body: form });
            const json = await res.json();
            if (!res.ok) throw new Error(json.detail || "Failed");
            setRecipeId(json.recipe_id);
            if (publish) {
                const p = await fetch(`${backendUrlV1}/recipes/${json.recipe_id}/publish`, { method: "POST" });
                if (!p.ok) throw new Error("Failed to publish");
            }
            await new Promise(r => setTimeout(r, 1800));
            setDone(true);
        } catch (e) { setErr(e.message); }
        finally { setSub(false); }
    };

    if (done) {
        return <SuccessScreen recipeId={recipeId} onReset={() => { setDone(false); setStage(0); setAnimKey(k => k + 1); setData({ ...BLANK }); }} />;
    }

    if (!isAuthorized) {
        return (
            <div className="my-10">
                <RequireAuthGate returnTo="/recipes" />
            </div>
        );
    }

    return (
        <div className="fk-root min-h-screen flex flex-col">
            <div className="fk-glow" />

            {/* ── Ambient progress bar ── */}
            <ProgressBar stage={stage} data={data} />

            {/* ── Tab rail ── */}
            <div className="relative z-10 flex-shrink-0">
                <div className="flex items-end px-2 sm:px-4 overflow-x-auto relative"
                    style={{ scrollbarWidth: "none", msOverflowStyle: "none" }}>
                    {STAGES.map((s, i) => {
                        const done_ = i < stage;
                        const active = i === stage;
                        return (
                            <button key={s.key}
                                onClick={() => goTo(i)}
                                className={`flex items-center gap-1.5 px-3 py-3.5 border-b-2 text-[11px] sm:text-xs whitespace-nowrap
                                    flex-shrink-0 transition-all duration-250 relative cursor-pointer
                                    ${active
                                        ? "border-amber-500 text-amber-400 font-semibold"
                                        : done_
                                            ? "border-transparent text-neutral-400 hover:text-neutral-100"
                                            : "border-transparent text-neutral-500"}`}
                            >
                                {done_ && <span className="text-emerald-500/40 text-[9px]">✓</span>}
                                {s.label}
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* ── Stage hint ── */}
            <div className="relative z-10 px-4 sm:px-6 pt-4 pb-0 flex-shrink-0">
                <p key={stage} className="text-neutral-400 text-[10px] italic fade-up">
                    {STAGE_HINTS[stage]}
                </p>
            </div>

            {/* ── Main content: 2-col on lg+ ── */}
            <div className="relative z-10 flex-1">
                <div className="max-w-5xl mx-auto w-full px-4 sm:px-6 pt-6 pb-8">
                    {/* Grid: form (left) + live preview (right, desktop only) */}
                    <div className="grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-10">

                        {/* ── Form column ── */}
                        <div key={animKey} className="stage-enter min-w-0">
                            {stage === 0 && <StageDetails data={data} setData={setData} />}
                            {stage === 1 && <StageRecipe data={data} setData={setData} plan={USER_PLAN} />}
                            {stage === 2 && <StageMedia data={data} setData={setData} plan={USER_PLAN} />}
                            {stage === 3 && (
                                <StagePublish
                                    data={data} setData={setData} licenses={licenses}
                                    onPublish={() => submit(true)} onDraft={() => submit(false)}
                                    submitting={submitting} error={submitError}
                                />
                            )}

                            {/* ── Inline nav ── */}
                            {stage < 3 && (
                                <div className="flex gap-3 mt-10">
                                    {stage > 0 && (
                                        <button onClick={() => goTo(stage - 1)}
                                            className="flex-1 py-3.5 rounded-2xl border border-[#161616] text-neutral-300 text-sm
                                                hover:border-[#232323] hover:text-neutral-600 transition-all duration-200 active:scale-[0.98]">
                                            ← Back
                                        </button>
                                    )}
                                    <button onClick={() => goTo(stage + 1)}
                                        className="flex-[2] py-3.5 rounded-2xl font-semibold text-sm text-black
                                            bg-gradient-to-r from-amber-500 to-orange-500
                                            shadow-[0_4px_24px_rgba(232,160,32,0.18)] hover:shadow-[0_6px_32px_rgba(232,160,32,0.32)]
                                            active:scale-[0.99] transition-all duration-300">
                                        {stage === 2 ? "Review & publish →" : "Continue →"}
                                    </button>
                                </div>
                            )}
                        </div>

                        {/* ── Live preview column (desktop) ── */}
                        <LivePreview data={data} />
                    </div>
                </div>
            </div>
        </div>
    );
}