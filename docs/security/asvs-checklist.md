# OWASP ASVS Checklist (L1)

Implements FR-23. Source: OWASP ASVS v5.0.0 (released 2025-05-30, fetched 2026-05-03).
Every row is **unverified** by default. Replace the empty-bracket marker
with an x-marker (`[x]`) when the control is implemented and tested.
Identifier format: `v5.0.0-<chapter>.<section>.<requirement>`.

## V1 Architecture, design, threat modeling

- [ ] `v5.0.0-1.1.1` Use a secure SDLC that addresses security at all stages.
- [ ] `v5.0.0-1.2.1` Use unique low-privilege OS accounts for all application components.
- [ ] `v5.0.0-1.4.1` Trusted enforcement points (gateways, load balancers) enforce access controls.
- [ ] `v5.0.0-1.5.1` Input/output requirements clearly define data handling per type and law.

## V2 Authentication

- [ ] `v5.0.0-2.1.1` User-set passwords are at least 12 characters.
- [ ] `v5.0.0-2.1.2` Passwords up to 128 characters are permitted.
- [ ] `v5.0.0-2.1.7` Passwords are checked against a breached-passwords set on registration.
- [ ] `v5.0.0-2.2.1` Anti-automation controls in place to defeat credential stuffing.
- [ ] `v5.0.0-2.5.1` System-generated initial passwords are high-entropy and one-time-use.

## V3 Session management

- [ ] `v5.0.0-3.2.1` New session token issued on user authentication.
- [ ] `v5.0.0-3.2.3` Session tokens are at least 64 bits of entropy.
- [ ] `v5.0.0-3.3.1` Logout and expiration invalidate the session token server-side.
- [ ] `v5.0.0-3.4.1` Session cookies have HttpOnly, Secure, and SameSite attributes.

## V4 Access control

- [ ] `v5.0.0-4.1.1` Access control rules enforced on a trusted service layer.
- [ ] `v5.0.0-4.1.3` Principle of least privilege is the default for all roles.
- [ ] `v5.0.0-4.2.1` IDORs (insecure direct object references) are prevented per request.

## V5 Validation, sanitization, encoding

- [ ] `v5.0.0-5.1.1` Defenses against HTTP parameter pollution attacks.
- [ ] `v5.0.0-5.2.1` HTML input from rich-text editors is properly sanitized.
- [ ] `v5.0.0-5.3.1` Output encoding is appropriate for the interpreter and context.
- [ ] `v5.0.0-5.3.4` Parameterized queries used for all database access (no string concat).

## V7 Error handling and logging

- [ ] `v5.0.0-7.1.1` Application does not log credentials, session tokens, or sensitive data.
- [ ] `v5.0.0-7.4.1` All security-relevant events are logged with timestamp + user + action.

## V8 Data protection

- [ ] `v5.0.0-8.1.1` Sensitive data is identified and classified per a documented schema.
- [ ] `v5.0.0-8.3.1` Sensitive data is not transmitted in URLs (use POST body).

## V9 Communications security

- [ ] `v5.0.0-9.1.1` All network connections use TLS 1.2 or higher.
- [ ] `v5.0.0-9.2.1` TLS configuration disables weak ciphers (per Mozilla SSL Config).

## V10 Malicious code

- [ ] `v5.0.0-10.1.1` Code analysis tools detect potential malicious code at build time.
- [ ] `v5.0.0-10.3.2` Application has integrity checks (hash, signature) on critical files.

## V11 Business logic

- [ ] `v5.0.0-11.1.1` Business logic flows are sequential, in order, and not skippable.
- [ ] `v5.0.0-11.1.4` Anti-automation defenses prevent excessive resource consumption.

## V12 Files and resources

- [ ] `v5.0.0-12.1.1` Untrusted file uploads validated for type, size, and content.
- [ ] `v5.0.0-12.3.1` Files served via a defined sandboxed path; no path-traversal.

## V13 API and web service

- [ ] `v5.0.0-13.1.1` All API endpoints require authentication unless explicitly public.
- [ ] `v5.0.0-13.2.1` REST endpoints validate Content-Type and Accept headers.
- [ ] `v5.0.0-13.3.1` GraphQL endpoints have query-depth and complexity limits.

## V14 Configuration

- [ ] `v5.0.0-14.1.1` Build pipeline performs SAST and dependency scanning.
- [ ] `v5.0.0-14.2.1` Dependencies are pinned and verified against a known-good source.
- [ ] `v5.0.0-14.3.1` Default credentials and debug endpoints are disabled in production.
- [ ] `v5.0.0-14.5.1` HTTP security headers (CSP, HSTS, X-Frame-Options) configured.
