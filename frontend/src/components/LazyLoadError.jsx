// src/components/common/LazyErrorBoundary.jsx
import React from "react";

export default class LazyErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false };
    }

    static getDerivedStateFromError() {
        return { hasError: true };
    }

    componentDidCatch(error, info) {
        console.error("Lazy-loaded component failed:", error, info);

        if (/Loading chunk .* failed/i.test(error?.message)) {
        }
    }

    render() {
        const { hasError } = this.state;
        const { fallback, children } = this.props;

        if (hasError) {
            return (
                fallback ?? (
                    <div className="p-6 rounded-xl border border-red-500/30 bg-red-900/20 text-sm text-red-300">
                        Failed to load this section.
                    </div>
                )
            );
        }

        return children;
    }
}
