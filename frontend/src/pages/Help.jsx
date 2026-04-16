import { useEffect } from "react";
import { useContextManager } from "../features/ContextProvider";

export default function Help() {
    const { setIsLoading } = useContextManager();
    useEffect(() => {
        setIsLoading(false);
    }, []);
    return (
        <div className="max-w-[1000px] mx-auto px-6 py-12">
            <div className="prose dark:prose-invert">
                <h1>Help</h1>
                <p><strong>Note:</strong>{" "}This page is under construction. Please check back later.</p>
            </div>
        </div>
    );
}