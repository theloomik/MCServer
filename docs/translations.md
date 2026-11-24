# Translations

MCServer's texts live in JSON files that [Crowdin](https://crowdin.com) can sync:

```
src/mcserver/presentation/i18n/locales/
  en.json   source language (developers edit this file)
  uk.json   Ukrainian (translated in Crowdin, or by hand)
```

`crowdin.yml` in the repository root tells Crowdin where they are. The file type is **i18next JSON**: a flat object of `"key": "text"` pairs.

## Rules for texts

- **Keys never change meaning.** If a text changes meaning, give it a new key.
- **Placeholders stay as written**: `{server_id}`, `{count}`, `{minutes:02d}`. Translators may move them but must not translate or drop them. A test checks that every translation uses exactly the placeholders of the English text.
- **Plurals** use suffixed keys: `properties.unsaved_one` and `properties.unsaved_other` in English. Crowdin asks for the forms each language needs. Ukrainian, for example, has `_one`, `_few` and `_many` (1 зміна · 3 зміни · 7 змін).
- `&` in menu texts marks the Alt shortcut letter (`&File` → Alt+F).

## Adding a text

1. Add the key to `en.json` and use it with `messages.text("the.key", name=...)`. Visible text is never hard-coded in Python; a test enforces this.
2. Add the Ukrainian text to `uk.json` too (the tests require every key in Ukrainian), or ask a translator to add it in Crowdin before the release.
3. Run the tests: `test_i18n_uk.py` reports missing keys and placeholder mismatches, and `python tools/crowdin_sync.py check` checks every language file.
4. After the change reaches `dev`, the **Crowdin** workflow uploads the new English texts automatically.

## Crowdin

English is the source and is only edited here. Translators work in Crowdin. Translations come back through **`tools/crowdin_sync.py`**, never by copying files over: it merges Crowdin's files with the committed ones so nothing that works is lost.

- **Kept from the repository:** a key Crowdin did not deliver, a delivered text that is only the English source, and a delivered text whose placeholders differ from English.
- **Dropped:** keys English no longer has.
- **Untranslated keys:** MCServer shows English for them at runtime.

### Credentials

| Name | What it is | Where |
| --- | --- | --- |
| `CROWDIN_PROJECT_ID` | The numeric project ID (Crowdin › project › Tools › API) | Environment variable locally, repository secret in GitHub |
| `CROWDIN_PERSONAL_TOKEN` | A personal access token with the **Projects** scope (Crowdin › Account Settings › API) | Same |

GitHub: *Settings › Secrets and variables › Actions › New repository secret*, once for each name. To let the workflow open pull requests, also enable *Settings › Actions › General › Allow GitHub Actions to create and approve pull requests*. Never put either value in `crowdin.yml`, code or a commit.

### Locally

Install the [Crowdin CLI](https://crowdin.github.io/crowdin-cli/installation) (for example `npm install -g @crowdin/cli`), then:

```powershell
$env:CROWDIN_PROJECT_ID = "<project id>"
$env:CROWDIN_PERSONAL_TOKEN = "<token>"
python tools/crowdin_sync.py check                        # no network: validate crowdin.yml and the files
python tools/crowdin_sync.py upload                       # send en.json
python tools/crowdin_sync.py upload --translations        # once: seed Crowdin with uk.json from the repository
python tools/crowdin_sync.py download                     # fetch, merge and check; review with git diff
```

`download` refuses to run while the locale files have uncommitted changes, so it never mixes your edits with Crowdin's.

### In GitHub Actions (`.github/workflows/crowdin.yml`)

| When | What it does |
| --- | --- |
| A push to `dev` that changes `en.json` or `crowdin.yml` | Checks the files, uploads the English texts |
| Every Monday 05:17 UTC, or *Run workflow › download* | Downloads translations, merges and checks them. If anything changed, it opens a pull request `l10n/crowdin-<run>` into `dev` |
| *Run workflow › upload-sources / upload-translations* | Uploads English, or English and the repository's translations |

The workflow never pushes to `dev` or `main`. Pull requests opened with the workflow's token do not start the Quality workflow on their own (a GitHub rule). Run it from the Actions tab, or push a commit to the branch, before merging.

### First connection

1. Add the two secrets.
2. Run *upload-translations* once, so Crowdin starts with the Ukrainian texts that already exist and the first download does not undo them.
3. Afterwards, uploads happen on every change to `en.json`, and downloads arrive weekly as pull requests.

### Troubleshooting

| Message | Fix |
| --- | --- |
| `Set CROWDIN_PROJECT_ID and CROWDIN_PERSONAL_TOKEN …` | Set the variables in this terminal, or add the secrets in GitHub |
| `The Crowdin CLI was not found` | Install the CLI and open a new terminal |
| `'crowdin download' failed (exit code …)` | Wrong project ID, an expired token or one without access to the project, or no network. The CLI's own message above says which |
| `… has uncommitted changes` | Commit or stash `src/mcserver/presentation/i18n/locales` first |
| `rejected <key>: placeholders …` | A translator changed `{name}` placeholders. The repository's text was kept; fix the translation in Crowdin |
| `<key> is not an English key` | A translation file has a key `en.json` no longer has. Run `merge`, or delete the key |
| A new `xx.json` appears after a download | Crowdin has another target language. See *Adding a language* below. The app ignores the file until then |

## Adding a language

A new `xx.json` from Crowdin is not shown automatically. Do these three things too:

1. Register it in `src/mcserver/presentation/i18n/__init__.py` (`_LANGUAGES`) with its plural rule.
2. Add the code to `SUPPORTED_LANGUAGES` in `src/mcserver/application/settings.py`.
3. Add a `settings.language.xx` text so it appears in Settings.
