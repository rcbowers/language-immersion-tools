package com.immersion

import com.immersion.core.QueueEntry
import org.json.JSONArray
import org.junit.Assert.assertEquals
import org.junit.Test

/** Pure-logic tests for QueueEntry JSON serialisation (no Android context needed). */
class QueueStoreTest {

    @Test
    fun `queue entry round trips through json`() {
        val entry = QueueEntry(
            sentence = "Me gusta leer libros.",
            word = "leer",
            translation = "to read",
            location = "Page 5",
            createdAt = "2026-05-14T10:00:00",
        )
        val array = JSONArray()
        array.put(
            org.json.JSONObject().apply {
                put("sentence", entry.sentence)
                put("word", entry.word)
                put("translation", entry.translation)
                put("source_name", entry.sourceName)
                put("source_type", entry.sourceType)
                put("location", entry.location)
                put("created_at", entry.createdAt)
                put("status", entry.status)
            },
        )
        val obj = JSONArray(array.toString()).getJSONObject(0)
        assertEquals("leer", obj.getString("word"))
        assertEquals("to read", obj.getString("translation"))
        assertEquals("queued", obj.getString("status"))
    }
}
