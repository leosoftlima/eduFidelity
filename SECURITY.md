# Security

Report a vulnerability privately to the maintainers through GitHub's private
vulnerability reporting on this repository, not in a public issue.

The toolkit renders untrusted HTML in a headless browser with the network closed; a page
can only load local files and, when explicitly allowed, a local development server. Do not
expose `edufidelity measure` to untrusted users without process isolation. Credentials
never belong in the repository, in issues or in pull requests; the repository guard in CI
rejects common credential formats.
