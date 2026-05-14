package com.immersion.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.SheetState
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.immersion.core.SelectionData
import com.immersion.ui.theme.AppType
import com.immersion.ui.theme.Layout
import com.immersion.ui.theme.LocalAppColors

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TranslationSheet(
    selection: SelectionData,
    sheetState: SheetState = rememberModalBottomSheetState(skipPartialExpansion = true),
    onAddToAnki: () -> Unit,
    onQueue: () -> Unit,
    onDismiss: () -> Unit,
) {
    val colors = LocalAppColors.current

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = colors.surface,
        tonalElevation = 0.dp,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = Layout.CONTENT_PADDING, vertical = 4.dp)
                .navigationBarsPadding(),
        ) {
            // Word title
            Text(
                text = selection.word,
                style = AppType.heading,
                color = colors.accent,
            )

            Spacer(Modifier.height(8.dp))

            // Translation or loading indicator
            if (selection.translationPending) {
                Text(
                    text = "Translating…",
                    style = AppType.body,
                    color = colors.textMuted,
                )
            } else {
                Text(
                    text = selection.translation.ifEmpty { "—" },
                    style = AppType.body,
                    color = colors.text,
                )
            }

            // Context sentence with target word highlighted
            if (selection.sentence.isNotEmpty() && selection.word.isNotEmpty()) {
                Spacer(Modifier.height(12.dp))
                val sentence = selection.sentence
                val word = selection.word
                val annotated = buildAnnotatedString {
                    val lower = sentence.lowercase()
                    val wordLower = word.lowercase()
                    var cursor = 0
                    var matchStart = lower.indexOf(wordLower, cursor)
                    while (matchStart >= 0) {
                        append(sentence.substring(cursor, matchStart))
                        withStyle(SpanStyle(color = colors.accent)) {
                            append(sentence.substring(matchStart, matchStart + word.length))
                        }
                        cursor = matchStart + word.length
                        matchStart = lower.indexOf(wordLower, cursor)
                    }
                    append(sentence.substring(cursor))
                }
                Text(
                    text = annotated,
                    style = AppType.body.copy(fontSize = 13.sp),
                    color = colors.textSoft,
                )
            }

            Spacer(Modifier.height(20.dp))

            // Action buttons
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Button(
                    onClick = onAddToAnki,
                    enabled = !selection.translationPending && selection.translation.isNotEmpty(),
                    colors = ButtonDefaults.buttonColors(containerColor = colors.accent),
                    modifier = Modifier.weight(1f),
                ) {
                    Text(
                        text = "Add to Anki",
                        style = AppType.label,
                        color = androidx.compose.ui.graphics.Color.White,
                    )
                }
                Spacer(Modifier.width(Layout.BUTTON_SPACING))
                OutlinedButton(
                    onClick = onQueue,
                    enabled = !selection.translationPending,
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = colors.accent),
                ) {
                    Text(text = "Queue", style = AppType.label)
                }
            }

            Spacer(Modifier.height(8.dp))
        }
    }
}
