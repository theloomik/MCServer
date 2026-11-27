# Contributing to MCServer

Thanks for helping! MCServer is a small project, so the process is light.

## Reporting bugs and ideas

Use [Issues](https://github.com/theloomik/MCServer/issues/new/choose) — the forms ask for what
helps most (MCServer version, Windows version, error details). Security problems go
[privately](SECURITY.md), not in public issues.

## Translations

Texts are translated on Crowdin; see [docs/translations.md](docs/translations.md). English
(`en.json`) is the source; other languages are not edited by hand in pull requests.

## Code

1. Set up the project and run the checks as described in [docs/building.md](docs/building.md).
2. Branch from `dev` and open the pull request against `dev`. `main` only receives releases.
3. Keep a pull request to one change, with tests for new behaviour.
4. Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):
   `fix(ui): …`, `feat(backups): …`, `docs: …`.
5. Before pushing, the same checks as CI must pass: `ruff format --check`, `ruff check`, `mypy`,
   `pytest`, `bandit` (commands in [docs/building.md](docs/building.md#tests-and-checks)).

Some ground rules the code follows, so a review goes smoothly:

- **Never delete user files permanently.** Server folders, worlds and backups go to the Recycle Bin.
- **Interface texts live in the locale files**, never in code; a test checks this.
- **Layers stay apart** (domain → application → infrastructure/presentation); see
  [docs/gui-architecture.md](docs/gui-architecture.md) and [docs/decisions](docs/decisions).

By contributing, you agree that your contribution is licensed under the [MIT License](LICENSE).
