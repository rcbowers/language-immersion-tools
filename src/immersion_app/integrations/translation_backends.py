#!/usr/bin/env python3
"""
Translation Backend Abstraction
Provides online (Google Translate) and offline (MarianMT) translation backends.
"""

import asyncio
import gc
import inspect
import logging
import threading
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)

# Thread-local storage so each thread pool worker gets its own Translator/httpx.Client.
# httpx.Client is not safe for concurrent use from multiple threads.
_online_tls = threading.local()


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
        self._is_async = None

    # --- Sync path helpers ---

    def _get_translator(self):
        """Return a per-thread Translator instance (thread-local, not shared)."""
        if not hasattr(_online_tls, 'translator') or _online_tls.translator is None:
            from googletrans import Translator
            # 2-second read timeout — default is 5s, which means all concurrent
            # requests timeout simultaneously and flood the main-thread event queue.
            # Must pass httpx.Timeout (not a float) because googletrans 4.0.0rc1
            # sets client.timeout directly, bypassing httpx's own float→Timeout
            # conversion, causing AttributeError('float has no as_dict') on 0.13.x.
            try:
                import httpx as _httpx
                _online_tls.translator = Translator(timeout=_httpx.Timeout(2.0))
            except TypeError:
                _online_tls.translator = Translator()
        return _online_tls.translator

    def _reset_translator(self):
        """Discard this thread's sync Translator so the next call creates a fresh one."""
        _online_tls.translator = None

    # --- Async path helpers ---

    def _run_async(self, coro):
        """Run a coroutine on a persistent per-thread event loop.

        asyncio.run() creates AND tears down a full event loop on every call.
        The teardown (shutdown_asyncgens, shutdown_default_executor, loop.close)
        runs pure-Python async cleanup that holds the GIL for hundreds of ms,
        stalling the Qt main thread.  By keeping one loop alive per worker
        thread we pay that cost only once.
        """
        loop = getattr(_online_tls, 'async_loop', None)
        if loop is None or loop.is_closed():
            loop = asyncio.new_event_loop()
            _online_tls.async_loop = loop
        return loop.run_until_complete(coro)

    async def _get_tls_async_translator(self):
        """Return (or lazily create) the per-thread persistent async Translator.

        Creating a new Translator + httpx.AsyncClient on every call then
        immediately closing it via `async with` is the primary source of
        per-translation GIL-holding teardown.  We create it once per thread
        and keep the HTTP connection pool alive.
        """
        if getattr(_online_tls, 'async_translator', None) is None:
            from googletrans import Translator
            try:
                import httpx as _httpx
                t = Translator(timeout=_httpx.Timeout(2.0))
            except TypeError:
                t = Translator()
            # __aenter__ initialises the httpx.AsyncClient inside Translator
            if hasattr(t, '__aenter__'):
                await t.__aenter__()
            _online_tls.async_translator = t
        return _online_tls.async_translator

    def _reset_async_translator(self):
        """Close and discard the per-thread async Translator on error."""
        translator = getattr(_online_tls, 'async_translator', None)
        if translator is not None and hasattr(translator, '__aexit__'):
            loop = getattr(_online_tls, 'async_loop', None)
            if loop and not loop.is_closed():
                try:
                    loop.run_until_complete(translator.__aexit__(None, None, None))
                except Exception:
                    pass
        _online_tls.async_translator = None

    # --- Variant detection ---

    def _is_async_variant(self):
        """Detect if googletrans is using async variant."""
        if self._is_async is None:
            try:
                from googletrans import Translator
                self._is_async = inspect.iscoroutinefunction(Translator.translate)
            except Exception:
                self._is_async = False
        return self._is_async

    # --- Public translation methods ---

    def translate(self, text: str, src_lang: str, dest_lang: str) -> str:
        """Translate using Google Translate API."""
        logger.debug(f"OnlineTranslation request: '{text[:50]}...' [{src_lang} -> {dest_lang}]")
        try:
            from googletrans import Translator  # noqa: F401 — confirm installed
        except ImportError:
            logger.error("googletrans library not installed")
            raise RuntimeError("googletrans library not installed. Install with: pip install googletrans==4.0.0-rc1")

        if self._is_async_variant():
            try:
                result = self._run_async(self._translate_async(text, src_lang, dest_lang))
            except Exception:
                self._reset_async_translator()
                raise
            logger.info(f"Online translation completed: '{text[:30]}...' -> '{result[:30]}...'")
            return result

        # Sync variant — reuse per-thread httpx.Client
        try:
            result = self._get_translator().translate(text, src=src_lang, dest=dest_lang)
            translated = self._extract_translation_text(result)
            logger.info(f"Online translation completed: '{text[:30]}...' -> '{translated[:30]}...'")
            return translated
        except Exception as e:
            self._reset_translator()
            logger.debug(f"Online translation failed for '{text[:30]}...': {e}")
            raise

    async def _translate_async(self, text: str, src_lang: str, dest_lang: str) -> str:
        """Translate using the persistent per-thread Translator (no per-call create/destroy)."""
        trans = await self._get_tls_async_translator()
        result = await trans.translate(text, src=src_lang, dest=dest_lang)
        return self._extract_translation_text(result)

    def translate_batch(self, texts: list[str], src_lang: str, dest_lang: str) -> list[str]:
        """Translate multiple texts. For online mode individual tasks are used (batch API is unreliable)."""
        if not texts:
            return []

        logger.debug(f"Online batch translation: {len(texts)} texts [{src_lang} -> {dest_lang}]")
        try:
            from googletrans import Translator  # noqa: F401 — confirm installed
        except ImportError:
            logger.error("googletrans library not installed")
            raise RuntimeError("googletrans library not installed. Install with: pip install googletrans==4.0.0-rc1")

        if self._is_async_variant():
            try:
                result = self._run_async(self._translate_batch_async(texts, src_lang, dest_lang))
            except Exception:
                self._reset_async_translator()
                raise
            logger.debug(f"Online batch translation completed: {len(result)} translations")
            return result

        # Sync variant — reuse per-thread httpx.Client
        try:
            results = self._get_translator().translate(texts, src=src_lang, dest=dest_lang)
            if not isinstance(results, list):
                results = [results]
            translations = [self._extract_translation_text(r) for r in results]
            logger.debug(f"Online batch translation completed: {len(translations)} translations")
            return translations
        except Exception as e:
            self._reset_translator()
            raise

    async def _translate_batch_async(self, texts: list[str], src_lang: str, dest_lang: str) -> list[str]:
        """Batch translate using the persistent per-thread Translator."""
        trans = await self._get_tls_async_translator()
        results = await trans.translate(texts, src=src_lang, dest=dest_lang)
        if not isinstance(results, list):
            results = [results]
        return [self._extract_translation_text(r) for r in results]

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


class MarianMTTranslationBackend(TranslationBackend):
    """MarianMT backend for offline translation using HuggingFace transformers."""

    def __init__(self):
        self._models = {}  # Cache: {"{src}-{tgt}": (tokenizer, model)}
        self._model_locks = {}  # Thread safety: {"{src}-{tgt}": Lock}
        self._global_lock = threading.Lock()
        self._device = self._determine_device()

    def _determine_device(self) -> str:
        """Detect the best available device for inference."""
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
            else:
                return "cpu"
        except ImportError:
            return "cpu"

    def _get_model_name(self, src_lang: str, dest_lang: str) -> str:
        """Generate MarianMT model name for language pair."""
        # Special case: Japanese uses "jap" not "ja"
        src_code = "jap" if src_lang == "jap" else src_lang
        dest_code = "jap" if dest_lang == "jap" else dest_lang

        return f"Helsinki-NLP/opus-mt-{src_code}-{dest_code}"

    def _get_or_load_model(self, src_lang: str, dest_lang: str):
        """
        Load or retrieve cached model for language pair.
        Thread-safe lazy loading with per-model locks.

        Returns:
            tuple: (tokenizer, model)
        """
        pair_key = f"{src_lang}-{dest_lang}"

        # Fast path: model already loaded
        if pair_key in self._models:
            logger.debug(f"MarianMT model cache HIT: {pair_key}")
            return self._models[pair_key]

        # Acquire global lock for model loading
        with self._global_lock:
            # Double-check after acquiring lock
            if pair_key in self._models:
                logger.debug(f"MarianMT model cache HIT (after lock): {pair_key}")
                return self._models[pair_key]

            try:
                from transformers import MarianMTModel, MarianTokenizer
                import torch
            except ImportError:
                logger.error("transformers or torch not installed")
                raise RuntimeError(
                    "transformers or torch not installed. Install with: "
                    "pip install transformers torch sentencepiece sacremoses"
                )

            model_name = self._get_model_name(src_lang, dest_lang)

            try:
                # Download and load model (auto-downloads to ~/.cache/huggingface/hub/)
                logger.info(f"Loading MarianMT model: {model_name} (device: {self._device})")
                tokenizer = MarianTokenizer.from_pretrained(model_name)
                model = MarianMTModel.from_pretrained(model_name)

                # Move model to appropriate device
                model = model.to(self._device)
                model.eval()  # Set to evaluation mode

                # Cache the model
                self._models[pair_key] = (tokenizer, model)

                # Create per-model lock for inference
                self._model_locks[pair_key] = threading.Lock()

                logger.info(f"MarianMT model loaded successfully: {model_name} on {self._device}")
                return (tokenizer, model)

            except Exception as e:
                logger.error(f"Failed to load MarianMT model {model_name}: {e}", exc_info=True)
                raise RuntimeError(
                    f"Failed to load model {model_name}. "
                    f"Ensure internet connection for first download or try online mode. "
                    f"Error: {str(e)}"
                )

    def _translate_with_model(self, texts: list[str], src_lang: str, dest_lang: str) -> list[str]:
        """
        Translate a batch of texts using the model.

        Args:
            texts: List of texts to translate
            src_lang: Source language code
            dest_lang: Destination language code

        Returns:
            List of translated texts
        """
        if not texts:
            return []

        try:
            import torch
        except ImportError:
            raise RuntimeError("torch not installed")

        # Get or load model
        tokenizer, model = self._get_or_load_model(src_lang, dest_lang)

        # Get per-model lock to ensure thread safety
        pair_key = f"{src_lang}-{dest_lang}"
        model_lock = self._model_locks[pair_key]

        # Perform translation with model lock
        with model_lock:
            # Tokenize all texts at once with padding
            encoded = tokenizer(
                texts,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=512
            )

            # Move inputs to device
            encoded = {k: v.to(self._device) for k, v in encoded.items()}

            # Generate translations (no gradient computation needed)
            with torch.no_grad():
                translated_tokens = model.generate(**encoded)

            # Decode all translations
            translations = tokenizer.batch_decode(translated_tokens, skip_special_tokens=True)

            return translations

    def translate(self, text: str, src_lang: str, dest_lang: str) -> str:
        """
        Translate text from source language to destination language.

        Args:
            text: Text to translate
            src_lang: Source language code (e.g., 'es', 'jap')
            dest_lang: Destination language code (e.g., 'en')

        Returns:
            Translated text
        """
        if not text or not text.strip():
            return ""

        logger.debug(f"MarianMT translation: '{text[:50]}...' [{src_lang} -> {dest_lang}]")
        try:
            # Use batch translation with single item
            translations = self._translate_with_model([text], src_lang, dest_lang)
            result = translations[0] if translations else ""
            logger.info(f"MarianMT translation completed: '{text[:30]}...' -> '{result[:30]}...'")
            return result
        except Exception as e:
            logger.error(f"MarianMT translation failed for '{text[:30]}...': {e}", exc_info=True)
            raise RuntimeError(f"MarianMT translation failed: {str(e)}")

    def translate_batch(self, texts: list[str], src_lang: str, dest_lang: str) -> list[str]:
        """
        Translate multiple texts in a single batch request.
        This is 3-5x faster than individual translations.

        Args:
            texts: List of texts to translate
            src_lang: Source language code
            dest_lang: Destination language code

        Returns:
            List of translated texts in the same order as input
        """
        if not texts:
            return []

        logger.info(f"MarianMT batch translation: {len(texts)} texts [{src_lang} -> {dest_lang}]")
        try:
            result = self._translate_with_model(texts, src_lang, dest_lang)
            logger.info(f"MarianMT batch translation completed: {len(result)} translations")
            return result
        except Exception as e:
            # Fallback: if batch fails, translate one by one
            logger.warning(f"MarianMT batch translation failed, falling back to individual requests: {e}")
            return [self.translate(text, src_lang, dest_lang) for text in texts]

    def clear_model_cache(self):
        """
        Clear all cached models from memory.
        Call this when changing languages to free up memory.
        """
        try:
            import torch
        except ImportError:
            return

        logger.info(f"Clearing MarianMT model cache ({len(self._models)} models)")
        # Clear model references
        self._models.clear()
        self._model_locks.clear()

        # Force garbage collection
        gc.collect()

        # Clear CUDA cache if using GPU
        if self._device == "cuda" and torch.cuda.is_available():
            torch.cuda.empty_cache()

        logger.info("MarianMT model cache cleared")

    def is_available(self) -> bool:
        """Check if transformers and torch are installed."""
        try:
            import transformers
            import torch
            import sentencepiece
            import sacremoses
            return True
        except ImportError:
            return False

    def get_name(self) -> str:
        return "MarianMT"
