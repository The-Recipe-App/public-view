import Logo from "../features/Logo";

const Footer = ({ navOverlay, navOpen, isAuthorized }) => {
    return (
        <footer
            className={`
                z-[40]
                ${!navOverlay && navOpen ? "ml-[240px]" : "ml-0"}
                transition-all duration-300
                bg-gradient-to-b from-[#000000] to-[#000000]/30
                text-gray-400
            `}
        >
            <div className="max-w-full mx-auto">

                {/* ===== Top Section ===== */}
                <div className="px-6 pt-14 pb-12">
                    <div className="grid grid-cols-1 md:grid-cols-5 gap-10">

                        {/* Brand */}
                        <div className="md:col-span-2 flex flex-col md:items-start items-center space-y-4">
                            <Logo
                                width={280}
                                src="/footer_logo.svg"
                                alt="Forkit logo"
                            />
                            <p className="text-gray-500 md:text-left text-center leading-relaxed max-w-md">
                                A community-driven platform to cook, share,
                                and evolve recipes together, openly and collaboratively.
                            </p>
                        </div>

                        {/* Explore */}
                        <FooterSection title="Explore">
                            <FooterLink href="/recipes" label="Browse Recipes" />
                            {isAuthorized && <FooterLink href="/recipes/new" label="Create Recipe" />}
                            {isAuthorized && <FooterLink href="/favorites" label="Favorites" />}
                            {isAuthorized && <FooterLink href="/changelogs" label="Changelogs" />}
                        </FooterSection>

                        {/* Community */}
                        <FooterSection title="Community">
                            <FooterLink
                                href="https://github.com/The-Recipe-App/Forkit/blob/main/README.md"
                                label="READMEs"
                                external
                            />
                            <FooterLink
                                href="https://github.com/The-Recipe-App"
                                label="GitHub"
                                external
                            />
                            <FooterLink href="/contribute" label="Contribute" />
                        </FooterSection>

                        {/* Legal */}
                        <FooterSection title="Legal">
                            <FooterLink
                                href="https://github.com/The-Recipe-App/Forkit/blob/main/LICENSE"
                                label="Forkit Open Source AGPL-3.0 License"
                                external
                            />
                            <FooterLink href="/legal/privacy" label="Privacy Policy" />
                            <FooterLink href="/legal/tos" label="Terms of Use" />
                            <FooterLink href="/legal/community_guidelines" label="Community Guidelines" />
                            <FooterLink href="/legal/cookie_policy" label="Cookie Policy" />
                        </FooterSection>
                    </div>
                </div>

                {/* ===== Divider ===== */}
                <div className="px-6">
                    <div className="h-px bg-gradient-to-r from-transparent via-orange-500 to-transparent" />
                </div>

                {/* ===== Bottom Section ===== */}
                <div className="px-6 py-10">
                    <div className="flex flex-col md:flex-row items-center justify-between gap-10">

                        {/* Identity */}
                        <div className="text-center md:text-left space-y-2">
                            <p className="text-sm text-gray-500">
                                Open-source software ·{" "}
                                <a
                                    href="https://github.com/The-Recipe-App/Forkit/blob/main/LICENSE"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="hover:text-white underline underline-offset-4"
                                >
                                    AGPL-3.0 Licensed
                                </a>
                            </p>
                            <p className="text-xs text-gray-600">
                                © 2026 Forkit · <span className="inline text-orange-500 opacity-85">For cooks who wants to share, adapt, and improve recipes together</span>
                            </p>
                        </div>

                        {/* Tech Stack */}
                        <div className="flex flex-col items-center md:items-end gap-3">
                            <span className="text-[11px] text-center md:text-end w-full uppercase tracking-widest text-gray-500">
                                Built with
                            </span>
                            <div className="h-px w-full bg-gradient-to-r from-transparent via-neutral-500 to-transparent md:from-transparent md:to-neutral-500 " />
                            <div className="flex flex-wrap justify-center md:justify-end gap-2">
                                <TechBadge label="React" href="https://react.dev" />
                                <TechBadge label="Tailwind CSS" href="https://tailwindcss.com" />
                                <TechBadge label="FastAPI" href="https://fastapi.tiangolo.com" />
                                <TechBadge label="Python" href="https://www.python.org" />
                                <TechBadge label="PostgreSQL" href="https://www.postgresql.org" />
                            </div>
                        </div>
                    </div>
                </div>

            </div>
        </footer>
    );
};

export default Footer;

const FooterSection = ({ title, children }) => (
    <nav aria-label={title} className="flex flex-col space-y-4 md:items-start items-center">
        <h4 className="text-white text-center md:text-left font-medium tracking-wide">
            {title}
        </h4>
        <ul className="space-y-2 text-center md:text-left">
            {children}
        </ul>
    </nav>
);

const FooterLink = ({ href, label, external = false }) => (
    <li>
        <a
            href={href}
            target={external ? "_blank" : undefined}
            rel={external ? "noopener noreferrer" : undefined}
            className="
                text-gray-400
                hover:text-white
                transition-colors
            "
        >
            {label}
        </a>
    </li>
);

const TechBadge = ({ label, href }) => (
    <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="
            rounded-full
            border border-gray-700/70
            bg-gray-900/40
            px-3 py-1
            text-[11px]
            font-medium
            text-gray-400
            hover:text-white
            hover:border-gray-500
            hover:bg-gray-800
            hover:-translate-y-0.5
            transition-all
            duration-200
        "
    >
        {label}
    </a>
);
