"""Ukrainian catalog: ``locales/uk.json``, translated in Crowdin; missing keys fall back to English."""

from mcserver.presentation.i18n.catalog import Catalog, load_catalog

MESSAGES: Catalog = load_catalog("uk")
