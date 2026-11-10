# Contributing

Thanks for considering a contribution to phonescan.

## Development setup

1. Fork the repository and clone your fork.
2. Create and activate a virtual environment.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Running locally

Run the scanner with a test number:

```bash
python phonescan.py +15555550123
```

Optional environment variables are documented in README.md and can be set in a local .env file.

## Code style

- Keep changes focused and minimal.
- Preserve existing CLI behavior unless the change explicitly targets behavior.
- Avoid adding new dependencies unless clearly necessary.
- Do not commit secrets, API keys, or personal data.

## Pull requests

1. Create a branch from main.
2. Add a clear commit message.
3. Update documentation when behavior changes.
4. Open a pull request with:
   - What changed
   - Why it changed
   - How it was tested

## Reporting issues

When filing a bug report, include:

- Operating system and Python version
- Command used
- Error output
- Steps to reproduce

For security-sensitive issues, please follow SECURITY.md.
