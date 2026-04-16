import { useEffect, useRef, useState } from "react";
import backendUrlV1 from "../urls/backendUrl";

export function useUsernameAvailability(username, enabled = true) {
    const controllerRef = useRef(null);
    const writerRef = useRef(null);
    const [status, setStatus] = useState(null);

    useEffect(() => {
        if (!enabled) return;

        const controller = new AbortController();
        controllerRef.current = controller;

        const stream = new ReadableStream({
            start(controllerStream) {
                writerRef.current = controllerStream;
            },
        });

        fetch(`${backendUrlV1}/profile/username/stream`, {
            method: "POST",
            signal: controller.signal,
            credentials: "include",
            body: stream,
        })
            .then(async (res) => {
                const reader = res.body.getReader();
                const decoder = new TextDecoder();
                let buffer = "";

                while (true) {
                    const { value, done } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split("\n");
                    buffer = lines.pop();

                    for (const line of lines) {
                        if (!line.trim()) continue;
                        const data = JSON.parse(line);

                        if (data.reason === "invalid_format") {
                            setStatus("invalid");
                        } else {
                            setStatus(data.available ? "available" : "taken");
                        }
                    }
                }
            })
            .catch(() => {
                // aborted / closed
            });

        return () => {
            controller.abort();
            writerRef.current = null;
            controllerRef.current = null;
            setStatus(null);
        };
    }, [enabled]);

    useEffect(() => {
        if (!username || !writerRef.current) {
            setStatus(null);
            return;
        }

        setStatus("checking");
        writerRef.current.enqueue(
            JSON.stringify({ username }) + "\n"
        );
    }, [username]);

    return status;
}
