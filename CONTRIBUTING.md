# Contributing to transdoc

Thanks for your interest — issues, ideas, and pull requests are welcome. transdoc is free software
under the **GNU AGPL-3.0** ([LICENSE](LICENSE)); contributions are accepted under the same license.

## Ways to contribute

- **Report a bug / request a feature** — open an issue (templates provided).
- **Send a pull request** — fork, branch, and open a PR against `main`.
- **Discuss** — use GitHub Issues/Discussions for questions and proposals.

## Before you open a PR

1. Read [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for setup, tests, and the eval harness.
2. Keep changes focused; match the surrounding code style.
3. Run the checks locally:
   ```bash
   cd backend && ruff check . && pytest          # backend
   cd frontend && npm run lint                    # frontend
   ```
4. New source files must carry the SPDX header:
   ```
   # SPDX-License-Identifier: AGPL-3.0-only
   # Copyright (C) <year> <your name>
   ```

## Sign-off & licensing (DCO + CLA)

Two lightweight requirements keep the project's provenance and ownership clean:

### 1. DCO — sign off every commit

This project uses the [Developer Certificate of Origin](DCO). By signing off you certify that you
wrote the contribution or otherwise have the right to submit it under the project's license. Add a
sign-off line to each commit:

```bash
git commit -s -m "your message"
```

which appends:

```
Signed-off-by: Your Name <your.email@example.com>
```

(Use your real name and an email that matches your commit author.)

### 2. CLA — one-time agreement

Before your first PR is merged, you agree to the [Contributor License Agreement](CLA.md). It lets
the maintainer keep stewardship of the project (including relicensing flexibility) while you retain
copyright to your own contributions. A maintainer will confirm this on your first PR.

## Conduct

Be respectful and constructive. The maintainer may decline contributions that don't fit the
project's scope (see the README "Scope & limits").

— Maintainer: Muhammad Mishbakhuz Zuhail <muhammadmishbakhuzzuhail@gmail.com>
