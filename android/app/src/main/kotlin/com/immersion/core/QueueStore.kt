package com.immersion.core

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.time.Instant
import java.time.format.DateTimeFormatter

data class QueueEntry(
    val sentence: String,
    val word: String,
    val translation: String,
    val sourceName: String = "android-pdf",
    val sourceType: String = "pdf",
    val location: String = "",
    val createdAt: String = DateTimeFormatter.ISO_INSTANT.format(Instant.now()).dropLast(4) + "",  // seconds precision
    val status: String = "queued",
)

object QueueStore {

    private fun queueFile(context: Context): File {
        val dir = File(context.filesDir, "queue")
        dir.mkdirs()
        return File(dir, "queued_cards.json")
    }

    fun load(context: Context): List<QueueEntry> {
        val file = queueFile(context)
        if (!file.exists()) return emptyList()
        return try {
            val array = JSONArray(file.readText())
            (0 until array.length()).mapNotNull { i ->
                val obj = array.getJSONObject(i)
                QueueEntry(
                    sentence = obj.optString("sentence"),
                    word = obj.optString("word"),
                    translation = obj.optString("translation"),
                    sourceName = obj.optString("source_name", "android-pdf"),
                    sourceType = obj.optString("source_type", "pdf"),
                    location = obj.optString("location", ""),
                    createdAt = obj.optString("created_at", ""),
                    status = obj.optString("status", "queued"),
                )
            }
        } catch (_: Exception) {
            emptyList()
        }
    }

    fun save(context: Context, entries: List<QueueEntry>) {
        val array = JSONArray()
        entries.forEach { e ->
            array.put(JSONObject().apply {
                put("sentence", e.sentence)
                put("word", e.word)
                put("translation", e.translation)
                put("source_name", e.sourceName)
                put("source_type", e.sourceType)
                put("location", e.location)
                put("created_at", e.createdAt)
                put("status", e.status)
            })
        }
        val file = queueFile(context)
        val tmp = File(file.parent, "queued_cards.tmp")
        tmp.writeText(array.toString(2))
        tmp.renameTo(file)
    }

    fun append(context: Context, entry: QueueEntry) {
        val entries = load(context).toMutableList()
        entries.add(entry)
        save(context, entries)
    }

    fun count(context: Context): Int = load(context).size
}
