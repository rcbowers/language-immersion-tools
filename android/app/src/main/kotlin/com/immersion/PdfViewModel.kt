package com.immersion

import android.app.Application
import android.content.Context
import android.graphics.RectF
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.immersion.core.PageRenderResult
import com.immersion.core.PdfService
import com.immersion.core.QueueEntry
import com.immersion.core.QueueStore
import com.immersion.core.SelectionState
import com.immersion.core.TranslationService
import com.immersion.core.Word
import com.immersion.integrations.AnkiAdapter
import com.immersion.integrations.AnkiDroidAdapter
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.Instant
import java.time.format.DateTimeFormatter

data class UiState(
    val currentPage: PageRenderResult? = null,
    val pageIndex: Int = 0,
    val zoom: Float = 1f,
    val vocabularyWords: Set<String> = emptySet(),
    val queueCount: Int = 0,
    val ankiAvailable: Boolean = false,
    val darkMode: Boolean = true,
    val uiVisible: Boolean = true,
    val documentTitle: String = "",
    val error: String? = null,
)

class PdfViewModel(application: Application) : AndroidViewModel(application) {

    private val context: Context get() = getApplication()

    val pdfService = PdfService()
    val selection = SelectionState()
    private val translationService = TranslationService()
    val ankiAdapter: AnkiAdapter = AnkiDroidAdapter()

    private val _ui = MutableStateFlow(UiState())
    val ui: StateFlow<UiState> = _ui.asStateFlow()

    private var currentWordOrder: List<Word> = emptyList()

    // ── Document ──────────────────────────────────────────────────────────────

    fun openDocument(uri: Uri) {
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val fd = context.contentResolver.openFileDescriptor(uri, "r")?.detachFd()
                    ?: return@launch
                pdfService.loadDocument(fd)
                val title = uri.lastPathSegment ?: "Document"
                _ui.value = _ui.value.copy(documentTitle = title, pageIndex = 0, error = null)
                renderPage(0)
                refreshVocabulary()
                refreshQueueCount()
            } catch (e: Exception) {
                _ui.value = _ui.value.copy(error = "Could not open PDF: ${e.message}")
            }
        }
    }

    fun goToPage(index: Int) {
        val clamped = index.coerceIn(0, (pdfService.pageCount - 1).coerceAtLeast(0))
        if (clamped == _ui.value.pageIndex && _ui.value.currentPage != null) return
        viewModelScope.launch(Dispatchers.IO) {
            _ui.value = _ui.value.copy(pageIndex = clamped)
            renderPage(clamped)
            selection.clearAll()
        }
    }

    fun setZoom(zoom: Float) {
        val clamped = zoom.coerceIn(0.5f, 4.0f)
        viewModelScope.launch(Dispatchers.IO) {
            _ui.value = _ui.value.copy(zoom = clamped)
            renderPage(_ui.value.pageIndex)
        }
    }

    private suspend fun renderPage(index: Int) {
        val result = pdfService.renderPage(index, _ui.value.zoom) ?: return
        currentWordOrder = result.wordOrder
        _ui.value = _ui.value.copy(currentPage = result)
    }

    // ── Word tap / selection ──────────────────────────────────────────────────

    /** [x], [y] are in PDF coordinate space (screen coords divided by zoom). */
    fun onWordTap(x: Float, y: Float, shiftHeld: Boolean = false) {
        val words = _ui.value.currentPage?.words ?: return
        val hit = pdfService.wordAtPoint(x, y, words) ?: run {
            selection.clearAll()
            return
        }
        val anchor = if (shiftHeld) selection.current.anchorWord else null
        val selected = pdfService.resolveSelectedWords(hit, anchor, currentWordOrder, shiftHeld)
        val word = selected.joinToString(" ") { it.text.trim(',', '.', '!', '?', ':', ';', '"', '\'') }
        val sentence = pdfService.extractContext(selected, _ui.value.currentPage?.words ?: emptyList())
        val bboxes = selected.map { RectF(it.x0, it.y0, it.x1, it.y1) }

        selection.setPdfSelection(
            word = word,
            sentence = sentence,
            selectedWords = selected,
            bboxes = bboxes,
            anchor = if (shiftHeld) anchor ?: hit else hit,
        )
        requestTranslation(word)
    }

    private fun requestTranslation(word: String) {
        selection.setTranslationPending()
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val translation = translationService.translate(word)
                selection.setTranslation(translation)
            } catch (e: Exception) {
                selection.setTranslationError(e.message ?: "Network error")
            }
        }
    }

    fun clearSelection() = selection.clearAll()

    // ── Anki ──────────────────────────────────────────────────────────────────

    fun addToAnki() {
        val sel = selection.current
        if (sel.word.isEmpty()) return
        viewModelScope.launch(Dispatchers.IO) {
            val front = AnkiDroidAdapter.buildFront(sel.sentence.ifEmpty { sel.word }, sel.word)
            val deck = prefs().getString("anki_deck", "2025 Spanish Immersion")!!
            val noteId = ankiAdapter.addCard(context, front, sel.translation, deck)
            if (noteId != null) {
                refreshVocabulary()
            } else {
                // Anki unavailable — fall back to queue silently
                queueCard()
            }
        }
    }

    fun queueCard() {
        val sel = selection.current
        if (sel.word.isEmpty()) return
        val entry = QueueEntry(
            sentence = sel.sentence.ifEmpty { sel.word },
            word = sel.word,
            translation = sel.translation,
            location = "Page ${_ui.value.pageIndex + 1}",
            createdAt = DateTimeFormatter.ISO_INSTANT.format(Instant.now()),
        )
        viewModelScope.launch(Dispatchers.IO) {
            QueueStore.append(context, entry)
            refreshQueueCount()
        }
    }

    // ── Settings / UI ─────────────────────────────────────────────────────────

    fun toggleDarkMode() {
        _ui.value = _ui.value.copy(darkMode = !_ui.value.darkMode)
    }

    fun toggleUiVisibility() {
        _ui.value = _ui.value.copy(uiVisible = !_ui.value.uiVisible)
    }

    fun showUi() {
        _ui.value = _ui.value.copy(uiVisible = true)
    }

    // ── Private helpers ───────────────────────────────────────────────────────

    private fun refreshVocabulary() {
        viewModelScope.launch(Dispatchers.IO) {
            val deck = prefs().getString("anki_deck", "2025 Spanish Immersion")!!
            val words = ankiAdapter.fetchDeckWords(context, deck)
            _ui.value = _ui.value.copy(vocabularyWords = words, ankiAvailable = ankiAdapter.isAvailable(context))
        }
    }

    private fun refreshQueueCount() {
        _ui.value = _ui.value.copy(queueCount = QueueStore.count(context))
    }

    private fun prefs() = context.getSharedPreferences("immersion_prefs", Context.MODE_PRIVATE)

    override fun onCleared() {
        super.onCleared()
        pdfService.close()
    }
}
