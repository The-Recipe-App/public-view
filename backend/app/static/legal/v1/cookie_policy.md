# Forkit - Cookie Policy (Global)
**Version 1.0**
**Effective Date:** 2026-03-21

---

## 1. Introduction

This Cookie Policy explains how Forkit uses cookies and similar technologies when you access or use the Service. It should be read alongside our Privacy Policy and Terms of Service, both of which are incorporated by reference.

By continuing to use the Service after this policy is made available to you, you acknowledge the use of cookies as described here.

---

## 2. What Are Cookies

Cookies are small data files placed on your device by a web server when you visit a website or use a web application. They are sent back to the originating server on each subsequent request, allowing the server to recognize your device across interactions.

Forkit uses only **server-set cookies**. We do not use client-side scripts to read or write cookie values.

---

## 3. Cookies We Use

Forkit uses exactly **two cookies**, both of which are strictly necessary for the secure and functional operation of the Service. We do not use analytics, advertising, tracking, or any other non-essential cookies.

### 3.1 `_Host-forkit-device`

| Attribute | Value |
|---|---|
| **Purpose** | Device identity and security |
| **Set by** | Server only |
| **`SameSite`** | `Strict` |
| **`Secure`** | Yes - transmitted over HTTPS only |
| **`HttpOnly`** | Yes - not accessible via client-side scripts |
| **`__Host-` prefix** | Yes - enforces `Secure`, no `Domain` attribute, `Path=/` |
| **Persistence** | Persistent (duration determined by server at issuance) |

**Description:** This cookie stores a device identifier used to support security operations. Its purposes include detecting logins from unrecognized devices, triggering appropriate verification steps for new or suspicious device activity, and enabling device-specific security or functionality features that may be introduced over time. It does not store personal identification information.

The `__Host-` cookie name prefix is a security feature defined in RFC 6265bis. It requires that the cookie be set with the `Secure` flag, with no `Domain` attribute, and with `Path=/`, thereby preventing subdomain or path-scoped misuse.

---

### 3.2 `access_token`

| Attribute | Value |
|---|---|
| **Purpose** | User authentication |
| **Set by** | Server only |
| **`SameSite`** | `Strict` |
| **`Secure`** | Yes - transmitted over HTTPS only |
| **`HttpOnly`** | Yes - not accessible via client-side scripts |
| **Persistence** | Session or short-lived (expires with your authenticated session or on logout) |

**Description:** This cookie stores your authentication token, which is issued by our servers upon a successful login. It is presented on each request to verify that you are an authenticated user and to maintain your session. This cookie is invalidated when you log out or when the token expires. It is not used for tracking, advertising, or any purpose beyond session authentication.

---

## 4. Why These Cookies Are Strictly Necessary

Both cookies described above are classified as **strictly necessary**. This means:

- They are essential to providing the Service in a secure and functional manner.
- The Service cannot be delivered without them.
- They are not used for analytics, advertising, profiling, or any purpose unrelated to security and authentication.

Because these cookies are strictly necessary, they do not require your separate opt-in consent under most regulatory frameworks, including the EU ePrivacy Directive and GDPR, where strictly necessary cookies are exempt from consent requirements. However, we are committed to transparency and describe them fully in this policy.

---

## 5. No Third-Party Cookies

Forkit does not permit third parties to set cookies on your device through the Service. All cookies described in this policy are set exclusively by Forkit's own servers.

---

## 6. Cookie Security

Both cookies are protected by the following security attributes:

- **`Secure`**: Cookies are only transmitted over encrypted HTTPS connections and are never sent over plain HTTP.
- **`HttpOnly`**: Cookies cannot be read or modified by JavaScript running in the browser, mitigating cross-site scripting (XSS) risks.
- **`SameSite=Strict`**: Cookies are not sent on cross-site requests, providing strong protection against cross-site request forgery (CSRF) attacks.
- **`__Host-` prefix** (for `_Host-forkit-device`): Enforces additional constraints on cookie scope, preventing subdomain attacks.

These controls are consistent with current security best practices for web authentication and session management.

---

## 7. Cookie Retention

| Cookie | Retention |
|---|---|
| `_Host-forkit-device` | Persistent; retained for a period necessary to support device recognition and security operations, as determined by the server at the time of issuance. |
| `access_token` | Short-lived; expires upon session termination, logout, or token expiry as determined by our authentication system. |

We do not retain cookie-derived data longer than necessary for the purposes described in this policy and our Privacy Policy.

---

## 8. Your Choices

Because the cookies described in this policy are strictly necessary for authentication and security, disabling them will prevent you from logging in or using authenticated features of the Service.

You may manage or delete cookies through your browser settings. Please note:

- Deleting the `access_token` cookie will log you out of your current session.
- Deleting the `_Host-forkit-device` cookie may cause your device to be treated as unrecognized, which may trigger additional verification steps on your next login.

Instructions for managing cookies vary by browser. Most browsers allow you to view, delete, or block cookies through their privacy or settings menus.

---

## 9. Jurisdiction-Specific Notes

### European Union and EEA
Strictly necessary cookies do not require prior consent under the EU ePrivacy Directive (2002/58/EC as amended). We rely on this exemption for the cookies described in this policy. EU residents may exercise data subject rights in relation to any personal data processed in connection with these cookies by contacting privacy@forkit.example.

### United States
For California residents, information collected via strictly necessary cookies may be subject to the California Consumer Privacy Act (CCPA/CPRA). We do not sell or share information derived from these cookies for advertising purposes. To exercise applicable rights, contact privacy@forkit.example.

### India
Indian users may raise questions or complaints regarding this policy through our Grievance Officer at india-grievance@forkit.example, in accordance with applicable Indian data-protection and intermediary guidelines.

---

## 10. Changes to This Policy

We may update this Cookie Policy as the Service evolves or as required by applicable law. If we introduce new cookies, we will update this policy before doing so and, where required by law, seek your consent. The effective date at the top of this document indicates when the policy was last revised.

Continued use of the Service after an update constitutes acceptance of the revised policy.

---

## 11. Contact

For questions about this Cookie Policy or our use of cookies:

**Privacy & Data Protection - Forkit**
Email: privacy@forkit.example

For India-specific concerns:
**Grievance Officer - Forkit India**
Email: india-grievance@forkit.example

---

*This Cookie Policy forms part of Forkit's suite of legal documents, which includes the Terms of Service, Privacy Policy, and Community & Safety Guidelines.*

---

© 2026 Forkit. All rights reserved.