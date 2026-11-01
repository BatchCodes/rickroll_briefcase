package io.github.batchcodes.briefcase

import java.net.HttpURLConnection
import java.net.URL

/** The addresses and settings of the briefcase, and the reachability check. */
object Briefcase {
    const val DEFAULT_NETWORK_NAME = "BRIEFCASE"
    const val HEALTH_PATH = "/healthz"
    const val TIMEOUT_MS = 2500

    /** The web app addresses, in the order of preference. */
    val ADDRESSES = listOf("http://briefcase.lan", "http://10.42.0.1")

    /**
     * Return the first address that answers the health check, or null.
     * [isHealthy] gets a health URL, for example "http://briefcase.lan/healthz".
     */
    fun firstReachable(isHealthy: (String) -> Boolean): String? =
        ADDRESSES.firstOrNull { address -> isHealthy(address + HEALTH_PATH) }

    /** WPA2 needs 8 to 63 characters. An empty password means an open network. */
    fun isValidPassword(password: String): Boolean =
        password.isEmpty() || password.length in 8..63

    /** A Wi-Fi network name has 1 to 32 bytes in UTF-8. */
    fun isValidNetworkName(name: String): Boolean =
        name.toByteArray(Charsets.UTF_8).size in 1..32

    /** A real HTTP health check. Run it on a background thread. */
    fun httpHealthy(url: String): Boolean =
        try {
            val connection = URL(url).openConnection() as HttpURLConnection
            connection.connectTimeout = TIMEOUT_MS
            connection.readTimeout = TIMEOUT_MS
            connection.useCaches = false
            try {
                connection.responseCode == HttpURLConnection.HTTP_OK
            } finally {
                connection.disconnect()
            }
        } catch (error: Exception) {
            false
        }
}
