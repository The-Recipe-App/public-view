import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import DOMPurify from "dompurify";

export default function PolicyContentRenderer({ markdown }) {
    return <PolicyContent markdown={markdown} />;
}

function PolicyContent({ markdown }) {
    const mdObj = markdown || {};
    const hasHtml = typeof mdObj.html === "string" && mdObj.html.length > 0;
    const hasMd = typeof mdObj.markdown === "string" && mdObj.markdown.length > 0;
    const contentMd = hasMd ? mdObj.markdown : hasHtml ? mdObj.html : "";

    const baseClass =
        "prose prose-invert max-w-none prose-p:leading-relaxed prose-li:my-1 prose-ul:pl-6 prose-ol:pl-6 prose-headings:text-orange-300 prose-a:text-orange-400 prose-a:underline prose-strong:text-white text-sm";

    if (hasHtml && !hasMd) {
        const sanitized = DOMPurify.sanitize(mdObj.html, {
            ADD_TAGS: ["iframe"],
            ADD_ATTR: ["allow", "allowfullscreen", "frameborder", "scrolling"],
        });
        return <div className={baseClass} dangerouslySetInnerHTML={{ __html: sanitized }} />;
    }

    if (!contentMd) {
        return <div className="text-sm text-neutral-400">Click on "Read" to view the policy</div>;
    }

    return (
        <div className={baseClass}>
            <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                    pre: ({ node, ...props }) => (
                        <pre
                            {...props}
                            className="whitespace-pre rounded-md bg-neutral-900 p-3 overflow-auto text-xs"
                            style={{ tabSize: 4 }}
                        />
                    ),
                    code: ({ node, inline, className, children, ...props }) => {
                        if (inline) {
                            return (
                                <code {...props} className={`px-1 py-0.5 rounded text-sm bg-neutral-800 ${className || ""}`}>
                                    {children}
                                </code>
                            );
                        }
                        return (
                            <code
                                {...props}
                                className={`whitespace-pre block rounded-md bg-neutral-900 p-3 overflow-auto text-xs ${className || ""}`}
                                style={{ tabSize: 4 }}
                            >
                                {children}
                            </code>
                        );
                    },
                    p: ({ node, ...props }) => <p {...props} className="leading-relaxed" />,
                    li: ({ node, ...props }) => <li {...props} className="my-1" />,
                }}
            >
                {contentMd}
            </ReactMarkdown>
        </div>
    );
}