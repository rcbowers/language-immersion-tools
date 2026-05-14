package com.immersion.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.text.ClickableText
import com.immersion.PdfViewModel
import com.immersion.core.ReflowPage
import com.immersion.core.ReflowParagraph
import com.immersion.core.SelectionData
import com.immersion.ui.theme.AppColors
import com.immersion.ui.theme.AppType
import com.immersion.ui.theme.Inter
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
        // Reflowed text — always full screen
        TextReflowView(
            reflowPage = ui.reflowPage,
            selection = selection,
            vocabularyWords = ui.vocabularyWords,
            onWordTap = { wordIndex -> viewModel.onWordTap(wordIndex) },
            onToggleUi = { viewModel.toggleUiVisibility() },
            modifier = Modifier.fillMaxSize(),
        )

        // Command bar (top) — slides in/out
        AnimatedVisibility(
            visible = ui.uiVisible,
            modifier = Modifier.align(Alignment.TopCenter),
            enter = slideInVertically { -it },
            exit = slideOutVertically { -it },
        ) {
            CommandBar(
                pageIndex = ui.pageIndex,
                pageCount = ui.reflowPage?.pageCount ?: 1,
                darkMode = ui.darkMode,
                onOpenFile = onOpenFile,
                onPageJump = { viewModel.goToPage(it) },
                onPrevPage = { viewModel.goToPage(ui.pageIndex - 1) },
                onNextPage = { viewModel.goToPage(ui.pageIndex + 1) },
                onToggleDark = { viewModel.toggleDarkMode() },
                onToggleUi = { viewModel.toggleUiVisibility() },
            )
        }

        // Status bar (bottom) — slides in/out
        AnimatedVisibility(
            visible = ui.uiVisible,
            modifier = Modifier.align(Alignment.BottomCenter),
            enter = slideInVertically { it },
            exit = slideOutVertically { it },
        ) {
            StatusBar(
                pageIndex = ui.pageIndex,
                pageCount = ui.reflowPage?.pageCount ?: 0,
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

// ── Reflow text view ──────────────────────────────────────────────────────────

@Composable
private fun TextReflowView(
    reflowPage: ReflowPage?,
    selection: SelectionData,
    vocabularyWords: Set<String>,
    onWordTap: (Int) -> Unit,
    onToggleUi: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = LocalAppColors.current

    LazyColumn(
        modifier = modifier,
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        if (reflowPage == null) {
            item {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 120.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        text = "Open a PDF to start reading",
                        style = AppType.body,
                        color = colors.textMuted,
                        textAlign = TextAlign.Center,
                    )
                }
            }
            return@LazyColumn
        }

        items(
            items = reflowPage.paragraphs,
            key = { paragraph -> reflowPage.paragraphs.indexOf(paragraph) },
        ) { paragraph ->
            val selectedWordIndices = selection.selectedWords
                .map { w -> reflowPage.pageWords.indexOf(w) }
                .toSet()

            ReflowParagraphView(
                paragraph = paragraph,
                selectedWordIndices = selectedWordIndices,
                vocabularyWords = vocabularyWords,
                colors = colors,
                onWordTap = onWordTap,
                onDoubleTap = onToggleUi,
            )
        }
    }
}

@Composable
private fun ReflowParagraphView(
    paragraph: ReflowParagraph,
    selectedWordIndices: Set<Int>,
    vocabularyWords: Set<String>,
    colors: AppColors,
    onWordTap: (Int) -> Unit,
    onDoubleTap: () -> Unit,
) {
    val isHeading = paragraph.isHeading
    val fontSize = if (isHeading) 19.sp else 17.sp
    val lineHeight = if (isHeading) 26.sp else 27.sp
    val fontWeight = if (isHeading) FontWeight.SemiBold else FontWeight.Normal

    val textStyle = TextStyle(
        fontFamily = Inter,
        fontWeight = fontWeight,
        fontSize = fontSize,
        lineHeight = lineHeight,
        color = colors.text,
    )

    val annotated = buildAnnotatedString {
        paragraph.words.forEachIndexed { i, word ->
            val clean = word.text.trim(',', '.', '!', '?', ':', ';', '"', '\'', '(', ')').lowercase()
            val isSelected = word.wordIndex in selectedWordIndices
            val isSeen = clean in vocabularyWords

            pushStringAnnotation(tag = "word_idx", annotation = word.wordIndex.toString())
            withStyle(
                SpanStyle(
                    background = when {
                        isSelected -> colors.hlSelected
                        isSeen -> colors.hlSeen
                        else -> Color.Transparent
                    },
                    color = colors.text,
                    fontFamily = Inter,
                    fontWeight = fontWeight,
                    fontSize = fontSize,
                ),
            ) {
                append(word.text)
            }
            pop()

            if (i < paragraph.words.lastIndex) append(" ")
        }
    }

    ClickableText(
        text = annotated,
        style = textStyle,
        onClick = { offset ->
            annotated
                .getStringAnnotations(tag = "word_idx", start = offset, end = offset)
                .firstOrNull()
                ?.item
                ?.toIntOrNull()
                ?.let { onWordTap(it) }
        },
        modifier = Modifier
            .fillMaxWidth()
            .pointerInput(onDoubleTap) {
                detectTapGestures(onDoubleTap = { onDoubleTap() })
            },
    )
}
