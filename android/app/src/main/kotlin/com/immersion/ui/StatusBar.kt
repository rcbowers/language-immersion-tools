package com.immersion.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.immersion.ui.theme.AppType
import com.immersion.ui.theme.Layout
import com.immersion.ui.theme.LocalAppColors

@Composable
fun StatusBar(
    pageIndex: Int,
    pageCount: Int,
    ankiAvailable: Boolean,
    queueCount: Int,
    modifier: Modifier = Modifier,
) {
    val colors = LocalAppColors.current

    Row(
        modifier = modifier
            .fillMaxWidth()
            .height(Layout.STATUS_BAR_HEIGHT)
            .background(colors.surfaceAlt)
            .padding(horizontal = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        // Left: progress fraction
        val progressText = if (pageCount > 0) {
            val percent = ((pageIndex + 1).toFloat() / pageCount * 100).toInt()
            "$percent% through"
        } else {
            ""
        }
        Text(
            text = progressText,
            style = AppType.caption,
            color = colors.textMuted,
        )

        // Right: Anki status dot + label
        Row(verticalAlignment = Alignment.CenterVertically) {
            Spacer(
                Modifier
                    .size(6.dp)
                    .clip(CircleShape)
                    .background(if (ankiAvailable) Color(0xFF4ADE80) else colors.textMuted),
            )
            Spacer(Modifier.width(6.dp))
            val label = when {
                ankiAvailable -> "Anki"
                queueCount > 0 -> "queued: $queueCount"
                else -> "Anki offline"
            }
            Text(
                text = label,
                style = AppType.caption,
                color = colors.textMuted,
            )
        }
    }
}
