package io.github.batchcodes.briefcase

import org.json.JSONArray

/** A version such as 0.1.0 or 0.2.0-rc.1, compared by the Semantic Versioning rules. */
data class Version(
    val numbers: List<Int>,
    val preRelease: List<String>,
) : Comparable<Version> {
    override fun compareTo(other: Version): Int {
        for (index in 0 until maxOf(numbers.size, other.numbers.size)) {
            val difference = numbers.getOrElse(index) { 0 } - other.numbers.getOrElse(index) { 0 }
            if (difference != 0) return difference
        }
        // A release is newer than its pre-releases.
        if (preRelease.isEmpty() || other.preRelease.isEmpty()) {
            return other.preRelease.size.coerceAtMost(1) - preRelease.size.coerceAtMost(1)
        }
        for (index in 0 until minOf(preRelease.size, other.preRelease.size)) {
            val difference = comparePart(preRelease[index], other.preRelease[index])
            if (difference != 0) return difference
        }
        return preRelease.size - other.preRelease.size
    }

    private fun comparePart(left: String, right: String): Int {
        val leftNumber = left.toIntOrNull()
        val rightNumber = right.toIntOrNull()
        return when {
            leftNumber != null && rightNumber != null -> leftNumber - rightNumber
            leftNumber != null -> -1
            rightNumber != null -> 1
            else -> left.compareTo(right)
        }
    }

    companion object {
        /** Parse "v0.1.0", "0.1.0" or "0.2.0-rc.1". Return null for any other text. */
        fun parse(text: String): Version? {
            val clean = text.trim().removePrefix("v").substringBefore('+')
            val main = clean.substringBefore('-')
            val numbers = main.split('.').map { it.toIntOrNull() ?: return null }
            if (numbers.isEmpty() || numbers.size > 3) return null
            val preRelease = if (clean.contains('-')) clean.substringAfter('-').split('.') else emptyList()
            if (preRelease.any { it.isEmpty() }) return null
            return Version(numbers, preRelease)
        }
    }
}

/** A release with an APK, from the GitHub releases API. */
data class AppRelease(
    val tag: String,
    val version: Version,
    val apkName: String,
    val apkUrl: String,
    val checksumsUrl: String,
)

object Updates {
    const val RELEASES_URL = "https://api.github.com/repos/BatchCodes/rickroll_briefcase/releases?per_page=30"

    fun apkName(tag: String): String = "briefcase-$tag.apk"

    /**
     * Select the newest release that has an APK and a SHA256SUMS file.
     * Skip drafts, and skip pre-releases unless [includePreReleases] is true.
     */
    fun newestRelease(releasesJson: String, includePreReleases: Boolean): AppRelease? {
        val releases = JSONArray(releasesJson)
        var newest: AppRelease? = null
        for (index in 0 until releases.length()) {
            val release = releases.getJSONObject(index)
            if (release.optBoolean("draft")) continue
            if (release.optBoolean("prerelease") && !includePreReleases) continue
            val tag = release.optString("tag_name")
            val version = Version.parse(tag) ?: continue
            val assets = release.optJSONArray("assets") ?: continue
            var apkUrl: String? = null
            var checksumsUrl: String? = null
            for (assetIndex in 0 until assets.length()) {
                val asset = assets.getJSONObject(assetIndex)
                when (asset.optString("name")) {
                    apkName(tag) -> apkUrl = asset.optString("browser_download_url")
                    "SHA256SUMS" -> checksumsUrl = asset.optString("browser_download_url")
                }
            }
            if (apkUrl.isNullOrEmpty() || checksumsUrl.isNullOrEmpty()) continue
            val candidate = AppRelease(tag, version, apkName(tag), apkUrl, checksumsUrl)
            if (newest == null || candidate.version > newest.version) newest = candidate
        }
        return newest
    }

    /** Return the release if it is newer than [installedVersion], else null. */
    fun updateFor(installedVersion: String, release: AppRelease?): AppRelease? {
        val installed = Version.parse(installedVersion) ?: return null
        if (release == null || release.version <= installed) return null
        return release
    }

    /** Find the SHA-256 checksum of [fileName] in a SHA256SUMS file. */
    fun checksumFor(checksums: String, fileName: String): String? =
        checksums.lineSequence()
            .map { it.trim().split(Regex("\\s+"), limit = 2) }
            .firstOrNull { parts -> parts.size == 2 && parts[1].trimStart('*', '.', '/') == fileName }
            ?.get(0)
            ?.lowercase()

    /** Debug and development builds cannot update to a release: the signing key differs. */
    fun canUpdate(installedVersion: String): Boolean =
        !installedVersion.endsWith("-dev") && Version.parse(installedVersion) != null
}
