package com.immersion.integrations

import android.content.ContentValues
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri

/**
 * Integrates with AnkiDroid via its ContentProvider API (FlashCardsContract).
 *
 * Card format matches the desktop AnkiConnect implementation exactly:
 *   Front: sentence with target word wrapped in <font color="red">[word]</font>
 *   Back:  plain translation string
 *   Tags:  sentence-mining, auto-generated
 */
class AnkiDroidAdapter : AnkiAdapter {

    // AnkiDroid ContentProvider URIs — mirrors com.ichi2.anki.FlashCardsContract
    private object Contract {
        const val AUTHORITY = "com.ichi2.anki.flashcards"
        val NOTE_URI: Uri = Uri.parse("content://$AUTHORITY/notes")
        val MODEL_URI: Uri = Uri.parse("content://$AUTHORITY/models")
        val DECK_URI: Uri = Uri.parse("content://$AUTHORITY/decks")

        const val NOTE_MID = "mid"
        const val NOTE_FLDS = "flds"
        const val NOTE_TAGS = "tags"
        const val NOTE_DECK_ID = "did"

        // AnkiDroid field separator (Unit Separator, ASCII 0x1F)
        const val FIELD_SEP = ""
    }

    override fun isAvailable(context: Context): Boolean {
        val pm = context.packageManager
        return try {
            pm.getPackageInfo("com.ichi2.anki", 0)
            context.checkCallingOrSelfPermission("com.ichi2.anki.permission.READ_WRITE_DATABASE") ==
                PackageManager.PERMISSION_GRANTED
        } catch (_: PackageManager.NameNotFoundException) {
            false
        }
    }

    override suspend fun addCard(
        context: Context,
        front: String,
        back: String,
        deck: String,
        tags: List<String>,
    ): Long? {
        if (!isAvailable(context)) return null

        val deckId = getDeckId(context, deck) ?: return null
        val modelId = getModelId(context, "Basic") ?: return null

        val values = ContentValues().apply {
            put(Contract.NOTE_MID, modelId)
            put(Contract.NOTE_FLDS, front + Contract.FIELD_SEP + back)
            put(Contract.NOTE_TAGS, tags.joinToString(" "))
            put(Contract.NOTE_DECK_ID, deckId)
        }

        return try {
            val uri = context.contentResolver.insert(Contract.NOTE_URI, values)
            uri?.lastPathSegment?.toLongOrNull()
        } catch (_: Exception) {
            null
        }
    }

    override suspend fun fetchDeckWords(context: Context, deck: String): Set<String> {
        if (!isAvailable(context)) return emptySet()

        val deckId = getDeckId(context, deck) ?: return emptySet()
        val wordRegex = Regex("""\[(.+?)]""")
        val words = mutableSetOf<String>()

        try {
            val cursor = context.contentResolver.query(
                Contract.NOTE_URI,
                arrayOf(Contract.NOTE_FLDS),
                "did = ?",
                arrayOf(deckId.toString()),
                null,
            ) ?: return emptySet()

            cursor.use {
                val fldsIdx = it.getColumnIndexOrThrow(Contract.NOTE_FLDS)
                while (it.moveToNext()) {
                    val flds = it.getString(fldsIdx) ?: continue
                    val front = flds.substringBefore(Contract.FIELD_SEP)
                    wordRegex.find(front)?.groupValues?.getOrNull(1)?.let { w ->
                        words.add(w.lowercase())
                    }
                }
            }
        } catch (_: Exception) {
            // AnkiDroid not accessible — return empty set, no vocab highlighting
        }

        return words
    }

    private fun getDeckId(context: Context, deckName: String): Long? {
        return try {
            val cursor = context.contentResolver.query(
                Contract.DECK_URI,
                arrayOf("_id", "name"),
                null, null, null,
            ) ?: return null
            cursor.use {
                val idIdx = it.getColumnIndexOrThrow("_id")
                val nameIdx = it.getColumnIndexOrThrow("name")
                while (it.moveToNext()) {
                    if (it.getString(nameIdx) == deckName) return it.getLong(idIdx)
                }
            }
            null
        } catch (_: Exception) {
            null
        }
    }

    private fun getModelId(context: Context, modelName: String): Long? {
        return try {
            val cursor = context.contentResolver.query(
                Contract.MODEL_URI,
                arrayOf("_id", "name"),
                null, null, null,
            ) ?: return null
            cursor.use {
                val idIdx = it.getColumnIndexOrThrow("_id")
                val nameIdx = it.getColumnIndexOrThrow("name")
                while (it.moveToNext()) {
                    if (it.getString(nameIdx) == modelName) return it.getLong(idIdx)
                }
            }
            null
        } catch (_: Exception) {
            null
        }
    }

    companion object {
        /** Builds the card front matching the desktop format exactly. */
        fun buildFront(sentence: String, word: String): String {
            val replacement = """<font color="red">[${Regex.escapeReplacement(word)}]</font>"""
            return sentence.replace(Regex("(?i)${Regex.escape(word)}"), replacement)
        }
    }
}
