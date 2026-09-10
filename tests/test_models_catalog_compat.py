"""Compatibility tests for Hermes' decomposed model catalog modules."""

import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import hermes_cli

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from plugin.injector import patch_models_catalog


class ModelsCatalogCompatibilityTests(unittest.TestCase):
    def test_provider_entry_comes_from_decomposed_catalog_module(self):
        """Registration works after Hermes removes the legacy re-export."""
        models = ModuleType("hermes_cli.models")
        models.CANONICAL_PROVIDERS = []
        models._PROVIDER_MODELS = {}
        models.clear_provider_models_cache = lambda provider: None

        catalog = ModuleType("hermes_cli.models_catalog_static")

        class ProviderEntry:
            def __init__(self, slug, name, description):
                self.slug = slug
                self.name = name
                self.description = description

        catalog.ProviderEntry = ProviderEntry
        modules = {
            "hermes_cli.models": models,
            "hermes_cli.models_catalog_static": catalog,
        }

        with patch.dict(sys.modules, modules), patch.object(hermes_cli, "models", models):
            patch_models_catalog()

        self.assertEqual(
            [provider.slug for provider in models.CANONICAL_PROVIDERS],
            ["antigravity"],
        )


if __name__ == "__main__":
    unittest.main()
