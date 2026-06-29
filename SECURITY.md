# Security Policy

SnackOS uses a persistent Chromium profile for manual Blinkit login. That
profile contains authentication data and must be treated as sensitive.

## Do Not Commit

Never commit:

- `server/blinkit-profile/`
- `blinkit-profile/`
- Browser cookies
- Session storage
- Local storage
- API keys
- Wi-Fi credentials
- Payment information
- `.env` files
- Debug HTML dumps containing account data
- Screenshots containing personal information

The repository `.gitignore` is configured to exclude these files, but you should
still review `git status` before every commit.

## Local Credentials

Firmware credentials belong in local `config.h`, which is ignored by Git. Public
defaults live in `config.example.h`.

## Responsible Disclosure

If you discover a security issue, do not open a public issue with exploit
details or secrets. Contact the project maintainer privately and include:

- A concise description of the issue
- Affected files or flows
- Reproduction steps
- Suggested mitigation, if known

## Automation Safety

The Playwright flow is designed to stop before payment or final order placement.
Changes that touch checkout, payment, or order submission must be reviewed with
extra care and validated manually.

