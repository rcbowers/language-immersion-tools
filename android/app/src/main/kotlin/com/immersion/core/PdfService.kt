package com.immersion.core

import android.graphics.Bitmap
import android.graphics.RectF
import com.artifex.mupdf.fitz.ColorSpace
import com.artifex.mupdf.fitz.Document
import com.artifex.mupdf.fitz.Matrix
import com.artifex.mupdf.fitz.Page
import com.artifex.mupdf.fitz.Rect
import com.artifex.mupdf.fitz.StructuredText

data class Word(
    val x0: Float,
    val y0: Float,
    val x1: Float,
    val y1: Float,
    val text: String,
    val blockIndex: Int,
    val lineIndex: Int,
) {
    val rect: RectF get() = RectF(x0, y0, x1, y1)
    val key: Triple<Int, Int, String> get() = Triple(blockIndex, lineIndex, text)
}

data class PageRenderResult(
    val bitmap: Bitmap,
    val words: List<Word>,
    val wordOrder: List<Word>,
    val pageCount: Int,
)

class PdfService {

    private var doc: Document? = null

    fun loadDocument(path: String) {
        close()
        doc = Document.openDocument(path)
    }

    fun loadDocument(fd: Int) {
        close()
        doc = Document.openDocument(fd, "application/pdf")
    }

    val pageCount: Int get() = doc?.countPages() ?: 0

    fun renderPage(pageIndex: Int, zoom: Float): PageRenderResult? {
        val document = doc ?: return null
        val page = document.loadPage(pageIndex)
        val matrix = Matrix(zoom, zoom)
        val pixmap = page.toPixmap(matrix, ColorSpace.DeviceRGB, false)

        val width = pixmap.width
        val height = pixmap.height
        val samples = pixmap.samples
        val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        val argb = IntArray(width * height)
        var si = 0
        for (i in argb.indices) {
            val r = samples[si].toInt() and 0xFF
            val g = samples[si + 1].toInt() and 0xFF
            val b = samples[si + 2].toInt() and 0xFF
            argb[i] = (0xFF shl 24) or (r shl 16) or (g shl 8) or b
            si += 3
        }
        bitmap.setPixels(argb, 0, width, 0, 0, width, height)

        val words = extractWords(page)
        val wordOrder = words.sortedWith(compareBy({ it.y0 }, { it.x0 }))

        page.destroy()
        pixmap.destroy()

        return PageRenderResult(bitmap, words, wordOrder, document.countPages())
    }

    private fun extractWords(page: Page): List<Word> {
        val text = page.toStructuredText("words")
        val words = mutableListOf<Word>()
        var blockIdx = 0
        for (block in text.blocks ?: emptyArray()) {
            var lineIdx = 0
            for (line in block.lines ?: emptyArray()) {
                val sb = StringBuilder()
                var x0 = Float.MAX_VALUE
                var y0 = Float.MAX_VALUE
                var x1 = Float.MIN_VALUE
                var y1 = Float.MIN_VALUE
                for (ch in line.chars ?: emptyArray()) {
                    if (ch.c == ' '.code) {
                        if (sb.isNotEmpty()) {
                            words.add(Word(x0, y0, x1, y1, sb.toString(), blockIdx, lineIdx))
                            sb.clear()
                            x0 = Float.MAX_VALUE; y0 = Float.MAX_VALUE
                            x1 = Float.MIN_VALUE; y1 = Float.MIN_VALUE
                        }
                        continue
                    }
                    val r = ch.quad?.let {
                        RectF(
                            minOf(it.ul_x, it.ll_x),
                            minOf(it.ul_y, it.ur_y),
                            maxOf(it.ur_x, it.lr_x),
                            maxOf(it.ll_y, it.lr_y),
                        )
                    } ?: continue
                    sb.append(ch.c.toChar())
                    if (r.left < x0) x0 = r.left
                    if (r.top < y0) y0 = r.top
                    if (r.right > x1) x1 = r.right
                    if (r.bottom > y1) y1 = r.bottom
                }
                if (sb.isNotEmpty()) {
                    words.add(Word(x0, y0, x1, y1, sb.toString(), blockIdx, lineIdx))
                }
                lineIdx++
            }
            blockIdx++
        }
        text.destroy()
        return words
    }

    /** Returns the word whose bounding box (slightly expanded) contains (x, y) in PDF coordinates. */
    fun wordAtPoint(x: Float, y: Float, words: List<Word>): Word? {
        val expand = 2f
        return words.firstOrNull { w ->
            x >= w.x0 - expand && x <= w.x1 + expand &&
                y >= w.y0 - expand && y <= w.y1 + expand
        }
    }

    /**
     * Returns the list of selected words for a tap.
     * With [shift]=true and a valid [anchor], returns all words between anchor and hit
     * in reading order. Otherwise returns just [hit].
     */
    fun resolveSelectedWords(
        hit: Word,
        anchor: Word?,
        wordOrder: List<Word>,
        shift: Boolean,
    ): List<Word> {
        if (!shift || anchor == null) return listOf(hit)
        val anchorIdx = wordOrder.indexOfFirst { it.key == anchor.key }.takeIf { it >= 0 } ?: return listOf(hit)
        val hitIdx = wordOrder.indexOfFirst { it.key == hit.key }.takeIf { it >= 0 } ?: return listOf(hit)
        val from = minOf(anchorIdx, hitIdx)
        val to = maxOf(anchorIdx, hitIdx)
        return wordOrder.subList(from, to + 1)
    }

    /** Returns the full line text that contains the selected words. */
    fun extractContext(selected: List<Word>, allWords: List<Word>): String {
        if (selected.isEmpty()) return ""
        val firstSelected = selected.first()
        val lineWords = allWords.filter {
            it.blockIndex == firstSelected.blockIndex && it.lineIndex == firstSelected.lineIndex
        }.sortedBy { it.x0 }
        return lineWords.joinToString(" ") { it.text }
    }

    fun close() {
        doc?.destroy()
        doc = null
    }
}
