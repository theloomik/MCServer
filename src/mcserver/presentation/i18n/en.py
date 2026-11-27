"""English catalog, the source language for Crowdin: ``locales/en.json`` (every key must exist here)."""

from mcserver.presentation.i18n.catalog import Catalog, load_catalog

MESSAGES: Catalog = load_catalog("en")
