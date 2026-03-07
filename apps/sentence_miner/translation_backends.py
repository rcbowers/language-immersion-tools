#!/usr/bin/env python3
"""
Translation Backend Abstraction
Provides online (Google Translate) and offline (argostranslate) translation backends.
"""

import asyncio
import inspect
from abc import ABC, abstractmethod
from typing import Optional


class TranslationBackend(ABC):
    """Abstract base class for translation backends."""

    @abstractmethod
    def translate(self, text: str, src_lang: str, dest_lang: str) -> str:
        """
        Translate text from source language to destination language.

        Args:
            text: Text to translate
            src_lang: Source language code (e.g., 'es')
            dest_lang: Destination language code (e.g., 'en')

        Returns:
            Translated text

        Raises:
            Exception: If translation fails
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if this backend is available for use.

        Returns:
            True if backend can be used, False otherwise
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """
        Get the name of this backend.

        Returns:
            Backend name (e.g., 'Online', 'Offline')
        """
        pass


class OnlineTranslationBackend(TranslationBackend):
    """Google Translate backend for online translation."""

    def __init__(self):
        self._translator = None

    def translate(self, text: str, src_lang: str, dest_lang: str) -> str:
        """Translate using Google Translate API."""
        try:
            from googletrans import Translator
        except ImportError:
            raise RuntimeError("googletrans library not installed. Install with: pip install googletrans==4.0.0-rc1")

        # Handle async/sync variants of googletrans
        if inspect.iscoroutinefunction(Translator.translate):
            return asyncio.run(self._translate_async(text, src_lang, dest_lang))

        result = Translator().translate(text, src=src_lang, dest=dest_lang)
        if inspect.isawaitable(result):
            result = asyncio.run(result)

        return self._extract_translation_text(result)

    async def _translate_async(self, text: str, src_lang: str, dest_lang: str) -> str:
        """Async translation for googletrans async variants."""
        from googletrans import Translator

        async with Translator() as translator:
            result = await translator.translate(text, src=src_lang, dest=dest_lang)
            return self._extract_translation_text(result)

    def _extract_translation_text(self, result):
        """Extract translated text from googletrans result object."""
        translated_text = getattr(result, "text", None)
        if translated_text is None:
            raise RuntimeError(f"Unexpected translation result type: {type(result).__name__}")
        return translated_text

    def is_available(self) -> bool:
        """Check if googletrans is installed."""
        try:
            import googletrans
            return True
        except ImportError:
            return False

    def get_name(self) -> str:
        return "Online"


class OfflineTranslationBackend(TranslationBackend):
    """Argostranslate backend for offline translation."""

    def __init__(self):
        self._initialized = False
        self._models_downloaded = False

    def translate(self, text: str, src_lang: str, dest_lang: str) -> str:
        """Translate using argostranslate offline models."""
        try:
            import argostranslate.package
            import argostranslate.translate
        except ImportError:
            raise RuntimeError(
                "argostranslate library not installed. Install with: pip install argostranslate"
            )

        # Lazy initialization - only load models on first use
        if not self._initialized:
            self._initialize_models(src_lang, dest_lang)

        # Perform translation
        try:
            translated = argostranslate.translate.translate(text, src_lang, dest_lang)
            if translated is None or translated == "":
                raise RuntimeError("Translation returned empty result")
            return translated
        except Exception as e:
            raise RuntimeError(f"Offline translation failed: {str(e)}")

    def _initialize_models(self, src_lang: str, dest_lang: str):
        """
        Initialize argostranslate and download models if needed.
        This is called lazily on first translation to avoid startup delay.
        """
        import argostranslate.package
        import argostranslate.translate

        # Update package index
        try:
            argostranslate.package.update_package_index()
        except Exception as e:
            raise RuntimeError(
                f"Failed to update package index. Check internet connection: {str(e)}"
            )

        # Get available packages
        available_packages = argostranslate.package.get_available_packages()

        # Find the package for our language pair
        package_to_install = None
        for pkg in available_packages:
            if pkg.from_code == src_lang and pkg.to_code == dest_lang:
                package_to_install = pkg
                break

        if package_to_install is None:
            raise RuntimeError(
                f"No translation model found for {src_lang} -> {dest_lang}. "
                f"Available language pairs may not include this combination."
            )

        # Check if package is already installed
        installed_packages = argostranslate.package.get_installed_packages()
        already_installed = any(
            p.from_code == src_lang and p.to_code == dest_lang
            for p in installed_packages
        )

        # Download and install if needed
        if not already_installed:
            try:
                download_path = package_to_install.download()
                argostranslate.package.install_from_path(download_path)
                self._models_downloaded = True
            except Exception as e:
                raise RuntimeError(
                    f"Failed to download translation models. Check internet connection: {str(e)}"
                )

        self._initialized = True

    def is_available(self) -> bool:
        """Check if argostranslate is installed."""
        try:
            import argostranslate.package
            import argostranslate.translate
            return True
        except ImportError:
            return False

    def get_name(self) -> str:
        return "Offline"

    def models_were_downloaded(self) -> bool:
        """Check if models were downloaded during initialization."""
        return self._models_downloaded
