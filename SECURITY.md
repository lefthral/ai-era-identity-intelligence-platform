# Security policy

If you discover a security vulnerability, please follow **coordinated
disclosure**:

1. **Do not open a public issue.** Use the
   **"Report a vulnerability"** button on the repository's
   [Security tab](https://github.com/lefthral/ai-era-identity-intelligence-platform/security/advisories/new).
   This routes the report through GitHub's private vulnerability
   reporting channel — only the maintainers can see it.
2. Include in your report:
   - A clear description of the vulnerability.
   - Steps to reproduce (a small PoC is fine).
   - The impact you observed.
3. Expect an acknowledgment within **72 hours** and a triage within
   **7 days**.
4. We will work with you to agree on a fix-and-disclose timeline. We
   aim to credit reporters in the release notes (unless you prefer
   anonymity).

> **Why no public email?** Contact information in a public
> `SECURITY.md` is harvested by spammers. GitHub's private
> vulnerability reporting is the maintainer-recommended alternative
> and keeps the reporter's identity private until disclosure.

## Scope

In scope for this project's security policy:

- The Python code in `src/`, `lambdas/`, `app/`, `scripts/`, `examples/`.
- The Terraform modules in `terraform/`.
- The Docker images in `docker/`.
- The CI workflow in `.github/workflows/`.
- The audit-log model and the FS-AI RMF mapping in `docs/SECURITY.md`.

Out of scope:

- Vulnerabilities in upstream dependencies (report those to the
  upstream project).
- Theoretical issues without a working PoC.
- The synthetic data (it contains no real PII).

## Threat model summary

See `docs/SECURITY.md` for the full threat model. In short:

- An attacker is trying to commit wire fraud while evading detection.
- An attacker may have compromised an insider's credentials or used
  a deepfake of the CFO's voice/video.
- The platform's job is to BLOCK or REVIEW such transactions
  in real time, and to keep a tamper-evident audit log.
