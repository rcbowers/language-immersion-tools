package com.immersion.integrations

import android.content.Context

interface AnkiAdapter {
    /** Returns true if AnkiDroid is installed and the permission is granted. */
    fun isAvailable(context: Context): Boolean

    /**
     * Adds a card to Anki.
     * [front] should be the sentence with the target word highlighted.
     * [back] is the translation.
     * Returns the new note ID, or null on failure.
     */
    suspend fun addCard(
        context: Context,
        front: String,
        back: String,
        deck: String,
        tags: List<String> = listOf("sentence-mining", "auto-generated"),
    ): Long?

    /**
     * Returns all words already in the deck (for vocabulary highlighting).
     * Parses the bracketed word from the front field, same as desktop.
     */
    suspend fun fetchDeckWords(context: Context, deck: String): Set<String>
}
