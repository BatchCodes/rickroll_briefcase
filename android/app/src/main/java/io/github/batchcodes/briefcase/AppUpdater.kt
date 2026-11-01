package io.github.batchcodes.briefcase

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/**
 * Download and install app updates from the GitHub releases.
 *
 * The app often binds its traffic to the briefcase Wi-Fi, which has no
 * internet. So every request here uses a network that has a validated
 * internet connection, normally mobile data or a home Wi-Fi.
 */
class AppUpdater(private val context: Context) {
    private val connectivity = context.getSystemService(ConnectivityManager::class.java)

    /** The GitHub releases list as JSON. Run on a background thread. */
    fun releasesJson(): String = download(Updates.RELEASES_URL).toString(Charsets.UTF_8)

    /** Find the newest release that is newer than this app. Run on a background thread. */
    fun findUpdate(includePreReleases: Boolean): AppRelease? {
        val installed = installedVersion()
        if (!Updates.canUpdate(installed)) return null
        val json = download(Updates.RELEASES_URL).toString(Charsets.UTF_8)
        return Updates.updateFor(installed, Updates.newestRelease(json, includePreReleases))
    }

    /** Download and check the APK, then start the Android installer. Run on a background thread. */
    fun downloadAndInstall(release: AppRelease) {
        val checksums = download(release.checksumsUrl).toString(Charsets.UTF_8)
        val expected = Updates.checksumFor(checksums, release.apkName)
            ?: throw IOException("SHA256SUMS has no line for ${release.apkName}.")
        val apk = download(release.apkUrl)
        val actual = MessageDigest.getInstance("SHA-256").digest(apk)
            .joinToString("") { "%02x".format(it) }
        if (actual != expected) {
            throw IOException("The downloaded APK has a wrong checksum.")
        }
        install(apk)
    }

    fun installedVersion(): String =
        context.packageManager.getPackageInfo(context.packageName, 0).versionName ?: ""

    private fun internetNetwork(): Network {
        val candidates = listOfNotNull(connectivity.activeNetwork) + connectivity.allNetworks.toList()
        return candidates.firstOrNull { network ->
            val capabilities = connectivity.getNetworkCapabilities(network) ?: return@firstOrNull false
            capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
                capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
        } ?: throw IOException("The phone has no internet connection.")
    }

    private fun download(url: String): ByteArray {
        val connection = internetNetwork().openConnection(URL(url)) as HttpURLConnection
        connection.connectTimeout = 15_000
        connection.readTimeout = 60_000
        connection.setRequestProperty("Accept", "application/vnd.github+json, */*")
        try {
            if (connection.responseCode != HttpURLConnection.HTTP_OK) {
                throw IOException("$url answered ${connection.responseCode}.")
            }
            return connection.inputStream.use { it.readBytes() }
        } finally {
            connection.disconnect()
        }
    }

    private fun install(apk: ByteArray) {
        val installer = context.packageManager.packageInstaller
        val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
        params.setAppPackageName(context.packageName)
        val sessionId = installer.createSession(params)
        installer.openSession(sessionId).use { session ->
            session.openWrite("briefcase.apk", 0, apk.size.toLong()).use { output ->
                output.write(apk)
                session.fsync(output)
            }
            val intent = Intent(context, InstallStatusReceiver::class.java)
            // The installer adds its status to this intent, so it must be mutable.
            val pending = PendingIntent.getBroadcast(
                context,
                sessionId,
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE,
            )
            session.commit(pending.intentSender)
        }
    }
}
