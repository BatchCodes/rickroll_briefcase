package io.github.batchcodes.briefcase

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class UpdatesTest {
    private fun v(text: String) = Version.parse(text)!!

    @Test
    fun comparesVersions() {
        assertTrue(v("0.2.0") > v("0.1.9"))
        assertTrue(v("1.0.0") > v("0.99.99"))
        assertTrue(v("0.1.0") > v("0.1.0-rc.2"))
        assertTrue(v("0.1.0-rc.10") > v("0.1.0-rc.2"))
        assertTrue(v("0.1.0-rc.1") > v("0.1.0-beta.5"))
        assertEquals(0, v("v0.1.0").compareTo(v("0.1.0")))
    }

    @Test
    fun rejectsTextThatIsNotAVersion() {
        assertNull(Version.parse("main"))
        assertNull(Version.parse("1.2.3.4"))
        assertNull(Version.parse("1.x"))
    }

    private val releasesJson = """
        [
          {"tag_name": "v0.3.0", "draft": true, "prerelease": false, "assets": [
            {"name": "briefcase-v0.3.0.apk", "browser_download_url": "https://x/v0.3.0.apk"},
            {"name": "SHA256SUMS", "browser_download_url": "https://x/v0.3.0/SHA256SUMS"}]},
          {"tag_name": "v0.2.0-rc.1", "draft": false, "prerelease": true, "assets": [
            {"name": "briefcase-v0.2.0-rc.1.apk", "browser_download_url": "https://x/rc.apk"},
            {"name": "SHA256SUMS", "browser_download_url": "https://x/rc/SHA256SUMS"}]},
          {"tag_name": "v0.1.1", "draft": false, "prerelease": false, "assets": [
            {"name": "SHA256SUMS", "browser_download_url": "https://x/v0.1.1/SHA256SUMS"}]},
          {"tag_name": "v0.1.0", "draft": false, "prerelease": false, "assets": [
            {"name": "briefcase-v0.1.0.apk", "browser_download_url": "https://x/v0.1.0.apk"},
            {"name": "SHA256SUMS", "browser_download_url": "https://x/v0.1.0/SHA256SUMS"}]}
        ]
    """.trimIndent()

    @Test
    fun selectsTheNewestReleaseWithAnApk() {
        val release = Updates.newestRelease(releasesJson, includePreReleases = false)!!
        assertEquals("v0.1.0", release.tag)
        assertEquals("https://x/v0.1.0.apk", release.apkUrl)
    }

    @Test
    fun selectsAPreReleaseOnlyWhenAllowed() {
        val release = Updates.newestRelease(releasesJson, includePreReleases = true)!!
        assertEquals("v0.2.0-rc.1", release.tag)
    }

    @Test
    fun offersOnlyNewerVersions() {
        val release = Updates.newestRelease(releasesJson, includePreReleases = false)
        assertEquals(release, Updates.updateFor("0.0.9", release))
        assertNull(Updates.updateFor("0.1.0", release))
        assertNull(Updates.updateFor("0.2.0", release))
    }

    @Test
    fun readsTheChecksumFile() {
        val sums = """
            0123abcd  rickroll_briefcase-runtime-v0.1.0.tar.gz
            ABCDEF99  briefcase-v0.1.0.apk
        """.trimIndent()
        assertEquals("abcdef99", Updates.checksumFor(sums, "briefcase-v0.1.0.apk"))
        assertNull(Updates.checksumFor(sums, "missing.apk"))
    }

    @Test
    fun debugBuildsDoNotUpdate() {
        assertFalse(Updates.canUpdate("0.1.0-dev"))
        assertTrue(Updates.canUpdate("0.1.0"))
        assertTrue(Updates.canUpdate("0.2.0-rc.1"))
    }
}
