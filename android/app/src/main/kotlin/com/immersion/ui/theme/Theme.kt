package com.immersion.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.immersion.pdfreader.R

// ── Inter font family (assets copied from src/immersion_app/gui/fonts/) ───────
val Inter = FontFamily(
    Font(R.font.inter_regular, FontWeight.Normal),
    Font(R.font.inter_medium, FontWeight.Medium),
    Font(R.font.inter_semibold, FontWeight.SemiBold),
    Font(R.font.inter_bold, FontWeight.Bold),
)

// ── Color tokens — direct port of theme.py palettes ──────────────────────────

object DarkColors {
    val BG           = Color(0xFF111318)
    val SURFACE      = Color(0xFF181B22)
    val SURFACE_ALT  = Color(0xFF222733)
    val BORDER       = Color(0x1AFFFFFF)   // rgba(255,255,255,0.10)
    val TEXT         = Color(0xFFF3F4F6)
    val TEXT_SOFT    = Color(0xFFC3CAD5)
    val TEXT_MUTED   = Color(0xFF8D97A8)
    val ACCENT       = Color(0xFF7C8CFF)
    val ACCENT_DARK  = Color(0xFFB5C0FF)
    val ACCENT_SOFT  = Color(0xFF7C8CFF).copy(alpha = 0.18f)
    val HL_SEEN      = Color(0xFF7C8CFF).copy(alpha = 0.18f)
    val HL_SELECTED  = Color(0xFF7C8CFF).copy(alpha = 0.38f)
}

object LightColors {
    val BG           = Color(0xFFFAFAFA)
    val SURFACE      = Color(0xFFFFFFFF)
    val SURFACE_ALT  = Color(0xFFF4F4F5)
    val BORDER       = Color(0x12000000)   // rgba(0,0,0,0.07)
    val TEXT         = Color(0xFF18181B)
    val TEXT_SOFT    = Color(0xFF52525B)
    val TEXT_MUTED   = Color(0xFFA1A1AA)
    val ACCENT       = Color(0xFF5B6CFF)
    val ACCENT_DARK  = Color(0xFF2F3FD9)
    val ACCENT_SOFT  = Color(0xFF5B6CFF).copy(alpha = 0.10f)
    val HL_SEEN      = Color(0xFF5B6CFF).copy(alpha = 0.10f)
    val HL_SELECTED  = Color(0xFF5B6CFF).copy(alpha = 0.35f)
}

private val MaterialDarkScheme = darkColorScheme(
    background = DarkColors.BG,
    surface = DarkColors.SURFACE,
    surfaceVariant = DarkColors.SURFACE_ALT,
    onBackground = DarkColors.TEXT,
    onSurface = DarkColors.TEXT,
    primary = DarkColors.ACCENT,
    onPrimary = Color.White,
    outline = DarkColors.BORDER,
)

private val MaterialLightScheme = lightColorScheme(
    background = LightColors.BG,
    surface = LightColors.SURFACE,
    surfaceVariant = LightColors.SURFACE_ALT,
    onBackground = LightColors.TEXT,
    onSurface = LightColors.TEXT,
    primary = LightColors.ACCENT,
    onPrimary = Color.White,
    outline = LightColors.BORDER,
)

// ── Layout constants — matching desktop theme.py ──────────────────────────────

object Layout {
    val COMMAND_BAR_HEIGHT: Dp = 44.dp
    val STATUS_BAR_HEIGHT: Dp = 28.dp
    val SHEET_PEEK_HEIGHT: Dp = 0.dp       // full dismiss when not shown
    val POPOVER_WIDTH: Dp = 320.dp
    val CONTENT_PADDING: Dp = 20.dp
    val BUTTON_SPACING: Dp = 8.dp
}

// ── Typography shortcuts ──────────────────────────────────────────────────────

object AppType {
    val heading = TextStyle(fontFamily = Inter, fontWeight = FontWeight.SemiBold, fontSize = 19.sp)
    val body    = TextStyle(fontFamily = Inter, fontWeight = FontWeight.Normal, fontSize = 14.5.sp)
    val caption = TextStyle(fontFamily = Inter, fontWeight = FontWeight.Normal, fontSize = 11.sp)
    val micro   = TextStyle(fontFamily = Inter, fontWeight = FontWeight.Normal, fontSize = 9.sp)
    val label   = TextStyle(fontFamily = Inter, fontWeight = FontWeight.Medium, fontSize = 12.5.sp)
}

// ── Composition local for current color set ───────────────────────────────────

@Immutable
data class AppColors(
    val bg: Color,
    val surface: Color,
    val surfaceAlt: Color,
    val border: Color,
    val text: Color,
    val textSoft: Color,
    val textMuted: Color,
    val accent: Color,
    val accentDark: Color,
    val accentSoft: Color,
    val hlSeen: Color,
    val hlSelected: Color,
    val isDark: Boolean,
)

val darkAppColors = AppColors(
    bg = DarkColors.BG, surface = DarkColors.SURFACE, surfaceAlt = DarkColors.SURFACE_ALT,
    border = DarkColors.BORDER, text = DarkColors.TEXT, textSoft = DarkColors.TEXT_SOFT,
    textMuted = DarkColors.TEXT_MUTED, accent = DarkColors.ACCENT, accentDark = DarkColors.ACCENT_DARK,
    accentSoft = DarkColors.ACCENT_SOFT, hlSeen = DarkColors.HL_SEEN, hlSelected = DarkColors.HL_SELECTED,
    isDark = true,
)

val lightAppColors = AppColors(
    bg = LightColors.BG, surface = LightColors.SURFACE, surfaceAlt = LightColors.SURFACE_ALT,
    border = LightColors.BORDER, text = LightColors.TEXT, textSoft = LightColors.TEXT_SOFT,
    textMuted = LightColors.TEXT_MUTED, accent = LightColors.ACCENT, accentDark = LightColors.ACCENT_DARK,
    accentSoft = LightColors.ACCENT_SOFT, hlSeen = LightColors.HL_SEEN, hlSelected = LightColors.HL_SELECTED,
    isDark = false,
)

val LocalAppColors = staticCompositionLocalOf { darkAppColors }

@Composable
fun ImmersionTheme(darkMode: Boolean = true, content: @Composable () -> Unit) {
    val colors = if (darkMode) darkAppColors else lightAppColors
    val materialScheme = if (darkMode) MaterialDarkScheme else MaterialLightScheme
    CompositionLocalProvider(LocalAppColors provides colors) {
        MaterialTheme(colorScheme = materialScheme, content = content)
    }
}
