import { useQuery } from "@tanstack/react-query";
import backendUrlV1 from "../../urls/backendUrl";

export function useContentLicense(enabled = true) {
    const query = useQuery({
        queryKey: ["contentLicense"],
        queryFn: async () => {
            const res = await fetch(`${backendUrlV1}/recipes/licenses/`, {
                method: "GET",
                credentials: "include",
            });
            if (!res.ok) throw new Error("Failed to fetch licenses");
            return res.json();
        },
        enabled,
    });

    return {
        licenses: query.data ?? [],
        isLoading: query.isLoading,
        error: query.error,
    };
}