import { startRegistration, startAuthentication } from '@simplewebauthn/browser';
import backendUrlV1 from '../../urls/backendUrl';

async function parseError(res) {
    let payload;
    try {
        payload = await res.json();
    } catch {
        const text = await res.text();
        throw new Error(text || "Something went wrong");
    }

    throw new Error(payload.message || payload.detail || payload.error || "Something went wrong");
}


export async function registerPasskey_1() {
    const optRes = await fetch(`${backendUrlV1}/auth/passkey/register/options`, {
        method: 'POST',
        credentials: 'include',
    });

    if (!optRes.ok) {
        await parseError(optRes);
    }

    let { options } = await optRes.json();

    if (options.hints == null) delete options.hints;

    if (!options.pubKeyCredParams) {
        options.pubKeyCredParams = [
            { type: "public-key", alg: -7 },
            { type: "public-key", alg: -257 },
        ];
    }

    return options;
}

export async function ensure_unique_label(label) {
    const res = await fetch(`${backendUrlV1}/auth/passkey/register/verify-label`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ label }),
    });

    if (!res.ok) {
        await parseError(res);
    } else {
        return true;
    }
}

export async function registerPasskey_2(options, label) {
    const attestation = await startRegistration(options);

    const verifyRes = await fetch(`${backendUrlV1}/auth/passkey/register/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ attestation, label }),
    });

    if (!verifyRes.ok) {
        await parseError(verifyRes);
    }

    return true;
}


export async function loginWithPasskey(identifier) {
    const optRes = await fetch(`${backendUrlV1}/auth/passkey/login/options`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ identifier }),
    });

    if (!optRes.ok) {
        await parseError(optRes);
    }

    let { options } = await optRes.json();

    if (options.hints == null) delete options.hints;

    const assertion = await startAuthentication(options);

    const verifyRes = await fetch(`${backendUrlV1}/auth/passkey/login/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ assertion }),
    });

    if (!verifyRes.ok) {
        await parseError(verifyRes);
    }

    return true;
}

