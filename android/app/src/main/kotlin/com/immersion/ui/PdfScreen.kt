package com.immersion.ui

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.view.GestureDetector
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.View
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.viewinterop.AndroidView
import com.immersion.PdfViewModel
import com.immersion.core.SelectionData
import com.immersion.core.Word
import com.immersion.ui.theme.DarkColors
import com.immersion.ui.theme.LightColors
import com.immersion.ui.theme.LocalAppColors

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PdfScreen(
    viewModel: PdfViewModel,
    onOpenFile: () -> Unit,
) {
    val ui by viewModel.ui.collectAsState()
    val selection by viewModel.selection.state.collectAsState()
    val colors = LocalAppColors.current
    val sheetState = rememberModalBottomSheetState(skipPartialExpansion = true)

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(colors.bg),
    ) {
        // PDF canvas — always full screen
        Column(modifier = Modifier.fillMaxSize()) {
            // Space for command bar when visible (pushed by AnimatedVisibility below)
            Box(modifier = Modifier.weight(1f)) {
                PdfCanvas(
                    bitmap = ui.currentPage?.bitmap,
                    words = ui.currentPage?.words ?: emptyList(),
                    selection = selection,
                    vocabularyWords = ui.vocabularyWords,
                    darkMode = ui.darkMode,
                    zoom = ui.zoom,
                    onWordTap = { x, y -> viewModel.onWordTap(x, y) },
                    onEmptyDoubleTap = { viewModel.toggleUiVisibility() },
                    onSwipeLeft = { viewModel.goToPage(ui.pageIndex + 1) },
                    onSwipeRight = { viewModel.goToPage(ui.pageIndex - 1) },
                    onZoomChange = { viewModel.setZoom(ui.zoom * it) },
                )
            }
        }

        // Command bar (top)
        AnimatedVisibility(
            visible = ui.uiVisible,
            modifier = Modifier.align(Alignment.TopCenter),
            enter = slideInVertically { -it },
            exit = slideOutVertically { -it },
        ) {
            CommandBar(
                pageIndex = ui.pageIndex,
                pageCount = ui.currentPage?.pageCount ?: 1,
                darkMode = ui.darkMode,
                onOpenFile = onOpenFile,
                onPageJump = { viewModel.goToPage(it) },
                onPrevPage = { viewModel.goToPage(ui.pageIndex - 1) },
                onNextPage = { viewModel.goToPage(ui.pageIndex + 1) },
                onToggleDark = { viewModel.toggleDarkMode() },
                onToggleUi = { viewModel.toggleUiVisibility() },
            )
        }

        // Status bar (bottom)
        AnimatedVisibility(
            visible = ui.uiVisible,
            modifier = Modifier.align(Alignment.BottomCenter),
            enter = slideInVertically { it },
            exit = slideOutVertically { it },
        ) {
            StatusBar(
                zoom = ui.zoom,
                ankiAvailable = ui.ankiAvailable,
                queueCount = ui.queueCount,
            )
        }

        // Translation sheet
        if (selection.hasSelection) {
            TranslationSheet(
                selection = selection,
                sheetState = sheetState,
                onAddToAnki = {
                    viewModel.addToAnki()
                    viewModel.clearSelection()
                },
                onQueue = {
                    viewModel.queueCard()
                    viewModel.clearSelection()
                },
                onDismiss = { viewModel.clearSelection() },
            )
        }
    }
}

// ── PDF Canvas View ───────────────────────────────────────────────────────────

@Composable
private fun PdfCanvas(
    bitmap: Bitmap?,
    words: List<Word>,
    selection: SelectionData,
    vocabularyWords: Set<String>,
    darkMode: Boolean,
    zoom: Float,
    onWordTap: (Float, Float) -> Unit,
    onEmptyDoubleTap: () -> Unit,
    onSwipeLeft: () -> Unit,
    onSwipeRight: () -> Unit,
    onZoomChange: (Float) -> Unit,
) {
    val hlSeen = if (darkMode) DarkColors.HL_SEEN.toArgb() else LightColors.HL_SEEN.toArgb()
    val hlSelected = if (darkMode) DarkColors.HL_SELECTED.toArgb() else LightColors.HL_SELECTED.toArgb()

    AndroidView(
        modifier = Modifier.fillMaxSize(),
        factory = { context ->
            PdfView(
                context = context,
                onWordTap = onWordTap,
                onEmptyDoubleTap = onEmptyDoubleTap,
                onSwipeLeft = onSwipeLeft,
                onSwipeRight = onSwipeRight,
                onZoomChange = onZoomChange,
            )
        },
        update = { view ->
            view.updateContent(
                bitmap = bitmap,
                words = words,
                selectionBboxes = selection.highlightBboxes,
                vocabularyWords = vocabularyWords,
                zoom = zoom,
                hlSeenColor = hlSeen,
                hlSelectedColor = hlSelected,
                darkMode = darkMode,
            )
        },
    )
}

private class PdfView(
    context: Context,
    private val onWordTap: (Float, Float) -> Unit,
    private val onEmptyDoubleTap: () -> Unit,
    private val onSwipeLeft: () -> Unit,
    private val onSwipeRight: () -> Unit,
    private val onZoomChange: (Float) -> Unit,
) : View(context) {

    private var bitmap: Bitmap? = null
    private var words: List<Word> = emptyList()
    private var selectionBboxes: List<RectF> = emptyList()
    private var vocabularyWords: Set<String> = emptySet()
    private var zoom: Float = 1f
    private var hlSeenColor: Int = 0
    private var hlSelectedColor: Int = 0
    private var darkMode: Boolean = true

    private val bitmapPaint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
    private val highlightPaint = Paint()

    private val gestureDetector = GestureDetector(context, object : GestureDetector.SimpleOnGestureListener() {
        override fun onSingleTapConfirmed(e: MotionEvent): Boolean {
            val bm = bitmap ?: return false
            val scale = computeScale(bm)
            val offsetX = (width - bm.width * scale) / 2f
            val offsetY = 0f
            val pdfX = (e.x - offsetX) / scale / zoom
            val pdfY = (e.y - offsetY) / scale / zoom
            onWordTap(pdfX, pdfY)
            return true
        }

        override fun onDoubleTap(e: MotionEvent): Boolean {
            onEmptyDoubleTap()
            return true
        }

        override fun onFling(e1: MotionEvent?, e2: MotionEvent, vx: Float, vy: Float): Boolean {
            if (e1 == null) return false
            val dx = e2.x - e1.x
            if (Math.abs(dx) > 80 && Math.abs(dx) > Math.abs(e2.y - e1.y)) {
                if (dx < 0) onSwipeLeft() else onSwipeRight()
                return true
            }
            return false
        }
    })

    private val scaleDetector = ScaleGestureDetector(context, object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
        override fun onScale(detector: ScaleGestureDetector): Boolean {
            onZoomChange(detector.scaleFactor)
            return true
        }
    })

    fun updateContent(
        bitmap: Bitmap?,
        words: List<Word>,
        selectionBboxes: List<RectF>,
        vocabularyWords: Set<String>,
        zoom: Float,
        hlSeenColor: Int,
        hlSelectedColor: Int,
        darkMode: Boolean,
    ) {
        this.bitmap = bitmap
        this.words = words
        this.selectionBboxes = selectionBboxes
        this.vocabularyWords = vocabularyWords
        this.zoom = zoom
        this.hlSeenColor = hlSeenColor
        this.hlSelectedColor = hlSelectedColor
        this.darkMode = darkMode
        invalidate()
    }

    private fun computeScale(bm: Bitmap): Float = width.toFloat() / bm.width

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val bm = bitmap ?: return
        val scale = computeScale(bm)
        val drawWidth = bm.width * scale
        val drawHeight = bm.height * scale
        val offsetX = (width - drawWidth) / 2f

        // Draw PDF bitmap (with dark mode inversion via color matrix if needed)
        if (darkMode) {
            val cm = android.graphics.ColorMatrix(floatArrayOf(
                -1f, 0f, 0f, 0f, 255f,
                 0f,-1f, 0f, 0f, 255f,
                 0f, 0f,-1f, 0f, 255f,
                 0f, 0f, 0f, 1f,   0f,
            ))
            bitmapPaint.colorFilter = android.graphics.ColorMatrixColorFilter(cm)
        } else {
            bitmapPaint.colorFilter = null
        }
        canvas.drawBitmap(bm, null, RectF(offsetX, 0f, offsetX + drawWidth, drawHeight), bitmapPaint)

        // Draw vocabulary highlights (seen words)
        highlightPaint.color = hlSeenColor
        words.forEach { w ->
            val clean = w.text.trim(',', '.', '!', '?', ':', ';', '"', '\'').lowercase()
            if (clean in vocabularyWords) {
                canvas.drawRect(
                    offsetX + w.x0 * zoom * scale,
                    w.y0 * zoom * scale,
                    offsetX + w.x1 * zoom * scale,
                    w.y1 * zoom * scale,
                    highlightPaint,
                )
            }
        }

        // Draw selection highlights
        highlightPaint.color = hlSelectedColor
        selectionBboxes.forEach { bbox ->
            canvas.drawRect(
                offsetX + bbox.left * zoom * scale,
                bbox.top * zoom * scale,
                offsetX + bbox.right * zoom * scale,
                bbox.bottom * zoom * scale,
                highlightPaint,
            )
        }
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        scaleDetector.onTouchEvent(event)
        if (!scaleDetector.isInProgress) {
            gestureDetector.onTouchEvent(event)
        }
        return true
    }
}
