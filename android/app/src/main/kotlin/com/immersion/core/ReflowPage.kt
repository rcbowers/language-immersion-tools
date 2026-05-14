package com.immersion.core

/**
 * A single word in the reflowed text layout.
 * [wordIndex] is the position of this word in [ReflowPage.pageWords], used to
 * look up the original bbox/coordinates for selection and context extraction.
 */
data class ReflowWord(
    val text: String,
    val wordIndex: Int,
    val charHeightPx: Float,
)

/**
 * A paragraph — all words from one StructuredText block, in reading order.
 * [isHeading] is true when the average character height of the block is
 * significantly larger than the page median (i.e. likely a chapter title).
 */
data class ReflowParagraph(
    val words: List<ReflowWord>,
    val isHeading: Boolean,
)

/**
 * The reflowed content of one PDF page.
 * [pageWords] is the canonical flat word list in reading order; it is the same
 * list that [SelectionState] and [PdfService.extractContext] operate on.
 */
data class ReflowPage(
    val paragraphs: List<ReflowParagraph>,
    val pageWords: List<Word>,
    val pageCount: Int,
)
