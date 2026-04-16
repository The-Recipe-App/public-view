import { useQuery } from "@tanstack/react-query";
import backendUrlV1 from "../urls/backendUrl";

export function useMe(enabled = true) {
    return useQuery({
        queryKey: ["profile", "me"],
        enabled: window.location.pathname !== "/oauth/callback",
        queryFn: async () => {
            const res = await fetch(`${backendUrlV1}/profile/me`, {
                credentials: "include",
            });
            if (!res.ok) throw new Error("Not authenticated");
            return res.json();
        },
    });
}

export function useProfile(username, enabled = true) {
    return useQuery({
        queryKey: ["profile", username],
        enabled: enabled && Boolean(username),
        queryFn: async () => {
            const res = await fetch(`${backendUrlV1}/profile/${encodeURIComponent(username)}`, {
                credentials: "include",
            });
            if (!res.ok) throw new Error("Profile not found");
            return res.json();
        },
    });
}
