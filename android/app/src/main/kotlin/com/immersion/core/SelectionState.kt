package com.immersion.core

import android.graphics.RectF
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

data class SelectionData(
    val word: String = "",
    val sentence: String = "",
    val translation: String = "",
    val selectedWords: List<Word> = emptyList(),
    val highlightBboxes: List<RectF> = emptyList(),
    val anchorWord: Word? = null,
    val translationPending: Boolean = false,
) {
    val hasSelection: Boolean get() = word.isNotEmpty()
}

class SelectionState {

    private val _state = MutableStateFlow(SelectionData())
    val state: StateFlow<SelectionData> = _state.asStateFlow()

    val current: SelectionData get() = _state.value

    fun setPdfSelection(
        word: String,
        sentence: String,
        selectedWords: List<Word>,
        bboxes: List<RectF>,
        anchor: Word?,
    ) {
        _state.value = SelectionData(
            word = word,
            sentence = sentence,
            selectedWords = selectedWords,
            highlightBboxes = bboxes,
            anchorWord = anchor,
            translationPending = true,
        )
    }

    fun setTranslationPending() {
        _state.value = _state.value.copy(translationPending = true, translation = "")
    }

    fun setTranslation(translation: String) {
        _state.value = _state.value.copy(translation = translation, translationPending = false)
    }

    fun setTranslationError(message: String) {
        _state.value = _state.value.copy(translation = "Error: $message", translationPending = false)
    }

    fun clearAll() {
        _state.value = SelectionData()
    }
}
