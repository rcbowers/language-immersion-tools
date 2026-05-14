package com.immersion

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.core.view.WindowCompat
import com.immersion.ui.PdfScreen
import com.immersion.ui.theme.ImmersionTheme

class MainActivity : ComponentActivity() {

    private val viewModel: PdfViewModel by viewModels()

    private val openPdfLauncher = registerForActivityResult(
        ActivityResultContracts.OpenDocument(),
    ) { uri ->
        uri ?: return@registerForActivityResult
        // Persist read permission across reboots
        contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
        viewModel.openDocument(uri)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Edge-to-edge: let Compose handle insets
        WindowCompat.setDecorFitsSystemWindows(window, false)

        // Handle PDF opened via file manager / intent
        intent?.data?.let { viewModel.openDocument(it) }

        setContent {
            val ui by viewModel.ui.collectAsState()
            ImmersionTheme(darkMode = ui.darkMode) {
                PdfScreen(
                    viewModel = viewModel,
                    onOpenFile = { openPdfLauncher.launch(arrayOf("application/pdf")) },
                )
            }
        }
    }
}
