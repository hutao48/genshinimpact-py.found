package com.genshin.detector

import android.content.Context
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/**
 * GitHub Releases 更新检查/下载。
 *
 * 安全约束：固定仓库地址、HTTPS、响应体大小上限、下载包 SHA-256 校验；
 * 只下载 `-android.apk` 资产，不执行除系统安装器以外的任何内容。
 */
object UpdateChecker {
    const val APP_VERSION = "1.1.1"
    private const val API_URL =
        "https://api.github.com/repos/hutao48/genshinimpact-py.found/releases/latest"
    private const val MAX_JSON = 512 * 1024
    private const val MAX_APK = 64L * 1024 * 1024

    data class Release(val version: String, val url: String, val sha256: String, val size: Long)

    private fun open(url: String): HttpURLConnection {
        val c = URL(url).openConnection() as HttpURLConnection
        c.connectTimeout = 15000
        c.readTimeout = 45000
        c.instanceFollowRedirects = true
        c.setRequestProperty("User-Agent", "GenshinInstrumentDetector/$APP_VERSION")
        c.setRequestProperty("Accept", "application/vnd.github+json")
        return c
    }

    private fun readLimited(input: InputStream, limit: Int): String {
        val out = java.io.ByteArrayOutputStream()
        val buf = ByteArray(16 * 1024)
        while (true) {
            val n = input.read(buf)
            if (n < 0) break
            out.write(buf, 0, n)
            if (out.size() > limit) throw IOException("response too large")
        }
        return out.toString("UTF-8")
    }

    private fun parseVersion(text: String): List<Int>? {
        val m = Regex("(\\d+)\\.(\\d+)\\.(\\d+)").find(text) ?: return null
        return m.groupValues.drop(1).map { it.toInt() }
    }

    fun isNewer(latest: String, current: String): Boolean {
        val a = parseVersion(latest) ?: return false
        val b = parseVersion(current) ?: return false
        for (i in 0 until minOf(a.size, b.size)) {
            if (a[i] != b[i]) return a[i] > b[i]
        }
        return false
    }

    /** 返回最新版本 APK 信息；没有新版本或没有 APK 时返回 null。 */
    fun latest(): Release? {
        val conn = open(API_URL)
        try {
            if (conn.responseCode != 200) throw IOException("HTTP ${conn.responseCode}")
            val info = JSONObject(readLimited(conn.inputStream, MAX_JSON))
            val version = parseVersion(info.optString("tag_name"))?.joinToString(".") ?: return null
            if (!isNewer(version, APP_VERSION)) return null
            val assets = info.optJSONArray("assets") ?: return null
            for (i in 0 until assets.length()) {
                val a = assets.optJSONObject(i) ?: continue
                val name = a.optString("name")
                if (!name.endsWith("-android.apk")) continue
                val url = a.optString("browser_download_url")
                val u = URL(url)
                if (u.protocol != "https" || u.host != "github.com") continue
                if (!u.path.startsWith("/hutao48/genshinimpact-py.found/releases/download/")) continue
                val digest = a.optString("digest")
                val sha = if (digest.startsWith("sha256:")) digest.substringAfter(':').lowercase() else ""
                if (!Regex("[0-9a-f]{64}").matches(sha)) continue
                return Release(version, url, sha, a.optLong("size", 0L))
            }
            return null
        } finally {
            conn.disconnect()
        }
    }

    /** 下载并校验 APK；失败时删除临时文件。 */
    fun download(context: Context, release: Release): File {
        val target = File(context.cacheDir, "update-${release.version}.apk")
        if (target.exists()) target.delete()
        val conn = open(release.url)
        try {
            if (conn.responseCode != 200) throw IOException("HTTP ${conn.responseCode}")
            if (release.size > MAX_APK) throw IOException("APK too large")
            val digest = MessageDigest.getInstance("SHA-256")
            var total = 0L
            conn.inputStream.use { input ->
                target.outputStream().use { output ->
                    val buf = ByteArray(64 * 1024)
                    while (true) {
                        val n = input.read(buf)
                        if (n < 0) break
                        total += n
                        if (total > MAX_APK) throw IOException("APK too large")
                        digest.update(buf, 0, n)
                        output.write(buf, 0, n)
                    }
                }
            }
            if (release.size > 0 && total != release.size) throw IOException("APK size mismatch")
            val actual = digest.digest().joinToString("") { "%02x".format(it.toInt() and 0xff) }
            if (actual != release.sha256) throw IOException("APK checksum mismatch")
            return target
        } catch (e: Exception) {
            target.delete()
            throw e
        } finally {
            conn.disconnect()
        }
    }
}
