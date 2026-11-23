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
2. Add the Ukrainian text to `uk.json`, or let Crowdin fill it in. Until it exists, the English text is shown.
3. Run the tests: `test_i18n_uk.py` reports missing keys and placeholder mismatches.

## Syncing with Crowdin

With the [Crowdin CLI](https://crowdin.github.io/crowdin-cli/) and the two environment variables set:

```powershell
$env:CROWDIN_PROJECT_ID = "<project id>"
$env:CROWDIN_PERSONAL_TOKEN = "<token>"
crowdin upload sources    # send en.json
crowdin download          # fetch uk.json and other languages
```

Keep the token out of the repository; `crowdin.yml` only names the variables.

## Adding a language

A new `xx.json` from Crowdin is not shown automatically. Do these three things too:

1. Register it in `src/mcserver/presentation/i18n/__init__.py` (`_LANGUAGES`) with its plural rule.
2. Add the code to `SUPPORTED_LANGUAGES` in `src/mcserver/application/settings.py`.
3. Add a `settings.language.xx` text so it appears in Settings.
