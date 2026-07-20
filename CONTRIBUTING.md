# Contributing

This repository is security-sensitive. Prefer small changes with explicit tests and avoid weakening privacy controls for convenience.

## Development principles

- Keep HTTP, persistence, model-provider and AWS concerns behind typed interfaces.
- Put business rules in application or domain services, not route handlers or React components.
- Use Pydantic models at input, output and configuration boundaries. Do not pass unvalidated dictionaries through the application.
- Never log prompts, model responses, decrypted data keys, conversation plaintext or authorisation headers.
- A privacy control must fail closed. If an approved provider cannot be selected, return an error rather than silently changing policy.
- Explain security decisions and non-obvious trade-offs in comments. Avoid comments that merely repeat the code.
- Add or update tests with every behaviour change.

## Expected checks

Run the checks relevant to the area you changed before opening a pull request:

```bash
cd backend
python -m pytest
python -m ruff check .
python -m mypy src

cd ../frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm test
pnpm build

cd ../terraform/environments/dev
terraform init -backend=false
terraform fmt -check -recursive ../..
terraform validate
```

Do not commit real `.env` files, Terraform state, model-provider credentials or generated conversation data.
