# Security policy

MTG Top 8 Metagame Analyzer is a hobby project run by one maintainer. This page says how to report a security problem and what to expect.

## Reporting a problem

**Please do not open a public issue for a security problem.** Use GitHub's private reporting instead: on the repository page go to **Security → Report a vulnerability**. If that option is not available to you, send a message through the site's feedback form that says only "Security report" and includes your email address in the email field; the form's title and description are public, so leave the details out and the maintainer will contact you.

Include, if you can: what you found, the URL or endpoint involved, the steps to reproduce it, and what an attacker could do with it.

You should get a reply within a week. This is a spare-time project, so fixes are made on a best-effort basis; serious problems are handled first.

## In scope

- The deployed site and its API.
- The code in this repository.
- Anything that exposes player email addresses, lets someone change tournament data without a valid link or the admin password, or takes the site down with little effort.

## Out of scope

- Findings that need the admin password or a valid, unexpired one-time link, and only do what that credential is meant to allow.
- Volume-based denial of service, and automated scanner output without a demonstrated impact.
- Problems in third-party services the site depends on (Railway, GitHub, Scryfall, MTGTop8, Brevo). Report those to the service itself.
- Tournament results that are wrong. That is a data correction, not a security problem: use the feedback form.

## Testing rules

- Test against your own local copy when you can; setup is in the README.
- Do not read, change or delete other people's data, and do not send email through the site.
- Stop and report as soon as you have shown the problem exists.

## More

- How the site is operated (sessions, links, limits, dependencies): [docs/SECURITY_OPERATIONS.md](docs/SECURITY_OPERATIONS.md)
- Known risks and how each is treated: [docs/RISK_REGISTER.md](docs/RISK_REGISTER.md)
- Privacy requests: the Privacy page on the site, and [docs/PRIVACY_REQUESTS.md](docs/PRIVACY_REQUESTS.md)
