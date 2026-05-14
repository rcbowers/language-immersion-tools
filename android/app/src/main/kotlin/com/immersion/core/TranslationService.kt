package com.immersion.core

import android.util.LruCache
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONArray
import java.net.URLEncoder
import java.util.concurrent.TimeUnit

class TranslationService {

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()

    private val cache = LruCache<String, String>(500)

    /**
     * Translates [text] using the Google Translate unofficial endpoint.
     * Mirrors the desktop googletrans backend.
     * Throws on network failure; caller handles errors.
     */
    suspend fun translate(
        text: String,
        sourceLang: String = "auto",
        targetLang: String = "en",
    ): String {
        val cacheKey = "$sourceLang:$targetLang:$text"
        cache.get(cacheKey)?.let { return it }

        val encoded = URLEncoder.encode(text, "UTF-8")
        val url = "https://translate.googleapis.com/translate_a/single" +
            "?client=gtx&sl=$sourceLang&tl=$targetLang&dt=t&q=$encoded"

        val request = Request.Builder().url(url).build()
        val response = client.newCall(request).execute()
        val body = response.body?.string() ?: throw RuntimeException("Empty response")

        val result = parseTranslation(body)
        cache.put(cacheKey, result)
        return result
    }

    private fun parseTranslation(json: String): String {
        // Response structure: [[["translated","original",null,null,1],...],...]
        val outer = JSONArray(json)
        val sentences = outer.getJSONArray(0)
        val sb = StringBuilder()
        for (i in 0 until sentences.length()) {
            val sentence = sentences.optJSONArray(i) ?: continue
            sb.append(sentence.optString(0))
        }
        return sb.toString().trim()
    }
}
