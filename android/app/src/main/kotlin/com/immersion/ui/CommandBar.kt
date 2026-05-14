package com.immersion.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.immersion.pdfreader.R
import com.immersion.ui.theme.AppType
import com.immersion.ui.theme.Layout
import com.immersion.ui.theme.LocalAppColors

@Composable
fun CommandBar(
    pageIndex: Int,
    pageCount: Int,
    darkMode: Boolean,
    onOpenFile: () -> Unit,
    onPageJump: (Int) -> Unit,
    onPrevPage: () -> Unit,
    onNextPage: () -> Unit,
    onToggleDark: () -> Unit,
    onToggleUi: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = LocalAppColors.current
    var pageInput by remember(pageIndex) { mutableStateOf((pageIndex + 1).toString()) }

    Row(
        modifier = modifier
            .fillMaxWidth()
            .height(Layout.COMMAND_BAR_HEIGHT)
            .background(colors.surface)
            .border(width = 0.5.dp, color = colors.border, shape = RoundedCornerShape(0.dp))
            .padding(horizontal = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        // Open file button
        IconButton(onClick = onOpenFile) {
            Icon(
                painter = painterResource(R.drawable.ic_folder_open),
                contentDescription = "Open PDF",
                tint = colors.textSoft,
            )
        }

        // Page navigation
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onPrevPage, enabled = pageIndex > 0) {
                Icon(
                    painter = painterResource(R.drawable.ic_chevron_left),
                    contentDescription = "Previous page",
                    tint = if (pageIndex > 0) colors.textSoft else colors.textMuted,
                )
            }
            Spacer(Modifier.width(2.dp))
            // Tappable page number field
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier
                        .clip(RoundedCornerShape(4.dp))
                        .background(colors.surfaceAlt)
                        .padding(horizontal = 6.dp, vertical = 2.dp)
                        .width(40.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    BasicTextField(
                        value = pageInput,
                        onValueChange = { pageInput = it.filter { c -> c.isDigit() } },
                        textStyle = AppType.label.copy(color = colors.text),
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(
                            keyboardType = KeyboardType.Number,
                            imeAction = ImeAction.Go,
                        ),
                        keyboardActions = KeyboardActions(
                            onGo = {
                                pageInput.toIntOrNull()?.let { onPageJump(it - 1) }
                            },
                        ),
                    )
                }
                Text(
                    text = " / $pageCount",
                    style = AppType.label,
                    color = colors.textMuted,
                )
            }
            Spacer(Modifier.width(2.dp))
            IconButton(onClick = onNextPage, enabled = pageIndex < pageCount - 1) {
                Icon(
                    painter = painterResource(R.drawable.ic_chevron_right),
                    contentDescription = "Next page",
                    tint = if (pageIndex < pageCount - 1) colors.textSoft else colors.textMuted,
                )
            }
        }

        // Right actions
        Row {
            IconButton(onClick = onToggleDark) {
                Icon(
                    painter = painterResource(
                        if (darkMode) R.drawable.ic_sun else R.drawable.ic_moon,
                    ),
                    contentDescription = "Toggle theme",
                    tint = colors.textSoft,
                )
            }
            IconButton(onClick = onToggleUi) {
                Icon(
                    painter = painterResource(R.drawable.ic_fullscreen),
                    contentDescription = "Hide UI",
                    tint = colors.textSoft,
                )
            }
        }
    }
}
