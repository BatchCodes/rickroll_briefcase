package io.github.batchcodes.briefcase

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.location.LocationManager
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.net.Uri
import android.net.wifi.WifiManager
import android.net.wifi.WifiNetworkSpecifier
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.text.InputType
import android.view.Gravity
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.view.ViewGroup
import android.webkit.JavascriptInterface
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import org.json.JSONObject

/**
 * One screen: the briefcase web app in a web view.
 *
 * At start, the app checks that the briefcase answers. If it does not, the
 * app offers to connect to the briefcase Wi-Fi with a network request. The
 * app then binds its own traffic to that network. The rest of the phone
 * keeps its normal internet connection.
 */
class MainActivity : Activity() {
    private lateinit var webView: WebView
    private lateinit var panel: LinearLayout
    private lateinit var message: TextView
    private lateinit var connectButton: Button
    private lateinit var retryButton: Button
    private lateinit var rangeText: TextView

    private val connectivity by lazy { getSystemService(ConnectivityManager::class.java) }
    private val preferences by lazy { getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE) }
    private var networkCallback: ConnectivityManager.NetworkCallback? = null
    private var fileCallback: ValueCallback<Array<Uri>>? = null
    private val updater by lazy { AppUpdater(this) }
    private val wifi by lazy { getSystemService(WifiManager::class.java) }
    private val handler = Handler(Looper.getMainLooper())
    private var askedForScanPermission = false
    private val rangeRefresh = object : Runnable {
        override fun run() {
            if (isPanelOffering()) {
                @Suppress("DEPRECATION")
                wifi.startScan()
                showRange()
                handler.postDelayed(this, RANGE_REFRESH_MS)
            }
        }
    }
    private val scanReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            showRange()
        }
    }

    private val networkName: String
        get() = preferences.getString(KEY_NETWORK_NAME, null) ?: Briefcase.DEFAULT_NETWORK_NAME

    private val password: String
        get() = preferences.getString(KEY_PASSWORD, null) ?: ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        buildViews()
        showVersions(briefcaseVersion = null)
        checkAndLoad()
        val dayMs = 24L * 60 * 60 * 1000
        if (System.currentTimeMillis() - preferences.getLong(KEY_LAST_UPDATE_CHECK, 0) > dayMs) {
            checkForUpdates(manual = false)
        }
    }

    private fun checkForUpdates(manual: Boolean) {
        val installed = updater.installedVersion()
        if (!Updates.canUpdate(installed)) {
            if (manual) toast(getString(R.string.update_not_possible, installed))
            return
        }
        val includePreReleases = preferences.getBoolean(KEY_INCLUDE_PRERELEASES, false)
        Thread {
            val result = runCatching { updater.findUpdate(includePreReleases) }
            runOnUiThread {
                if (isDestroyed) return@runOnUiThread
                result.onSuccess { release ->
                    preferences.edit().putLong(KEY_LAST_UPDATE_CHECK, System.currentTimeMillis()).apply()
                    if (release != null) {
                        offerUpdate(release, installed)
                    } else if (manual) {
                        toast(getString(R.string.up_to_date, installed))
                    }
                }
                result.onFailure { error ->
                    if (manual) toast(getString(R.string.update_failed, error.message ?: error.toString()))
                }
            }
        }.start()
    }

    private fun offerUpdate(release: AppRelease, installed: String) {
        AlertDialog.Builder(this)
            .setTitle(R.string.update_title)
            .setMessage(getString(R.string.update_message, release.tag.removePrefix("v"), installed))
            .setPositiveButton(R.string.update_install) { _, _ -> installUpdate(release) }
            .setNegativeButton(R.string.update_later, null)
            .show()
    }

    private fun installUpdate(release: AppRelease) {
        if (!packageManager.canRequestPackageInstalls()) {
            AlertDialog.Builder(this)
                .setTitle(R.string.allow_installs_title)
                .setMessage(R.string.allow_installs_message)
                .setPositiveButton(R.string.open_settings) { _, _ ->
                    startActivity(
                        Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:$packageName")),
                    )
                }
                .setNegativeButton(R.string.cancel, null)
                .show()
            return
        }
        toast(getString(R.string.update_downloading))
        Thread {
            val result = runCatching { updater.downloadAndInstall(release) }
            result.onFailure { error ->
                runOnUiThread { toast(getString(R.string.update_failed, error.message ?: error.toString())) }
            }
        }.start()
    }

    private fun toast(text: String) {
        Toast.makeText(this, text, Toast.LENGTH_LONG).show()
    }

    override fun onResume() {
        super.onResume()
        registerReceiver(scanReceiver, IntentFilter(WifiManager.SCAN_RESULTS_AVAILABLE_ACTION))
        if (isPanelOffering()) startRangeRefresh()
    }

    override fun onPause() {
        handler.removeCallbacks(rangeRefresh)
        unregisterReceiver(scanReceiver)
        super.onPause()
    }

    override fun onDestroy() {
        releaseNetwork()
        webView.destroy()
        super.onDestroy()
    }

    private fun buildViews() {
        webView = WebView(this).apply {
            visibility = View.GONE
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            addJavascriptInterface(AppBridge(), BRIDGE_NAME)
            webViewClient = object : WebViewClient() {
                override fun onReceivedError(
                    view: WebView,
                    request: WebResourceRequest,
                    error: WebResourceError,
                ) {
                    if (request.isForMainFrame) {
                        showPanel(getString(R.string.connection_lost), showConnect = true)
                    }
                }
            }
            webChromeClient = object : WebChromeClient() {
                override fun onShowFileChooser(
                    view: WebView,
                    callback: ValueCallback<Array<Uri>>,
                    params: FileChooserParams,
                ): Boolean {
                    fileCallback?.onReceiveValue(null)
                    fileCallback = callback
                    val intent = params.createIntent().putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                    return try {
                        @Suppress("DEPRECATION")
                        startActivityForResult(intent, REQUEST_FILES)
                        true
                    } catch (error: Exception) {
                        fileCallback = null
                        false
                    }
                }
            }
        }

        message = TextView(this).apply {
            textSize = 18f
            gravity = Gravity.CENTER
        }
        rangeText = TextView(this).apply {
            textSize = 15f
            gravity = Gravity.CENTER
            val padding = (12 * resources.displayMetrics.density).toInt()
            setPadding(0, padding, 0, padding)
        }
        connectButton = Button(this).apply { setOnClickListener { connect() } }
        retryButton = Button(this).apply {
            text = getString(R.string.try_again)
            setOnClickListener { checkAndLoad() }
        }
        panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            val padding = (24 * resources.displayMetrics.density).toInt()
            setPadding(padding, padding, padding, padding)
            addView(message)
            addView(rangeText)
            addView(connectButton)
            addView(retryButton)
        }

        val root = FrameLayout(this)
        val full = FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.MATCH_PARENT,
        )
        root.addView(webView, full)
        root.addView(panel, full)
        setContentView(root)
    }

    private fun showPanel(text: String, showConnect: Boolean) {
        webView.visibility = View.GONE
        panel.visibility = View.VISIBLE
        message.text = text
        connectButton.text = getString(R.string.connect, networkName)
        connectButton.visibility = if (showConnect) View.VISIBLE else View.GONE
        retryButton.visibility = if (showConnect) View.VISIBLE else View.GONE
        rangeText.visibility = if (showConnect) View.VISIBLE else View.GONE
        if (showConnect) {
            askForScanPermissionOnce()
            startRangeRefresh()
        } else {
            handler.removeCallbacks(rangeRefresh)
        }
    }

    private fun isPanelOffering(): Boolean =
        panel.visibility == View.VISIBLE && connectButton.visibility == View.VISIBLE

    private fun startRangeRefresh() {
        handler.removeCallbacks(rangeRefresh)
        handler.post(rangeRefresh)
    }

    private fun scanPermission(): String =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            Manifest.permission.NEARBY_WIFI_DEVICES
        } else {
            Manifest.permission.ACCESS_FINE_LOCATION
        }

    private fun askForScanPermissionOnce() {
        if (askedForScanPermission) return
        askedForScanPermission = true
        if (checkSelfPermission(scanPermission()) != PackageManager.PERMISSION_GRANTED) {
            val permissions = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                arrayOf(Manifest.permission.NEARBY_WIFI_DEVICES)
            } else {
                // Android 12 asks for coarse and fine location together.
                arrayOf(
                    Manifest.permission.ACCESS_COARSE_LOCATION,
                    Manifest.permission.ACCESS_FINE_LOCATION,
                )
            }
            requestPermissions(permissions, REQUEST_SCAN_PERMISSION)
        }
    }

    /** Show whether the briefcase Wi-Fi is in range, from the newest scan results. */
    private fun showRange() {
        if (!isPanelOffering()) return
        rangeText.text = when {
            !wifi.isWifiEnabled -> getString(R.string.network_wifi_off, networkName)
            checkSelfPermission(scanPermission()) != PackageManager.PERMISSION_GRANTED ->
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    getString(R.string.network_scan_permission, networkName)
                } else {
                    getString(R.string.network_scan_location, networkName)
                }
            Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU &&
                !getSystemService(LocationManager::class.java).isLocationEnabled ->
                getString(R.string.network_scan_location, networkName)
            else -> rangeMessage()
        }
    }

    private fun rangeMessage(): String {
        val results = try {
            wifi.scanResults.map { result -> scanResultName(result) to result.level }
        } catch (error: SecurityException) {
            emptyList()
        }
        val rssi = Briefcase.strongestRssi(results, networkName)
            ?: return getString(R.string.network_not_in_range, networkName)
        val signal = when (Briefcase.signalFor(rssi)) {
            Briefcase.Signal.STRONG -> getString(R.string.signal_strong)
            Briefcase.Signal.MEDIUM -> getString(R.string.signal_medium)
            Briefcase.Signal.WEAK -> getString(R.string.signal_weak)
        }
        return getString(R.string.network_in_range, networkName, signal)
    }

    private fun scanResultName(result: android.net.wifi.ScanResult): String =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            result.wifiSsid?.toString()?.removeSurrounding("\"") ?: ""
        } else {
            @Suppress("DEPRECATION")
            result.SSID ?: ""
        }

    private fun showWebApp(address: String) {
        panel.visibility = View.GONE
        webView.visibility = View.VISIBLE
        if (webView.url?.startsWith(address) != true) {
            webView.loadUrl(address)
        }
    }

    /** Find the briefcase on a background thread, then show the web app. */
    private fun checkAndLoad() {
        showPanel(getString(R.string.searching), showConnect = false)
        Thread {
            val address = Briefcase.firstReachable(Briefcase::httpHealthy)
            runOnUiThread {
                if (isDestroyed) return@runOnUiThread
                if (address != null) {
                    showWebApp(address)
                } else {
                    showPanel(getString(R.string.not_reachable, networkName), showConnect = true)
                }
            }
        }.start()
    }

    private fun connect() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            checkSelfPermission(Manifest.permission.NEARBY_WIFI_DEVICES) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.NEARBY_WIFI_DEVICES), REQUEST_PERMISSION)
            return
        }
        if (password.isEmpty() && !preferences.contains(KEY_PASSWORD)) {
            showSettings(afterSave = { connect() }, hint = getString(R.string.password_missing))
            return
        }
        requestBriefcaseNetwork()
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_SCAN_PERMISSION) {
            startRangeRefresh()
            return
        }
        if (requestCode == REQUEST_PERMISSION) {
            // Android 13 and later can ask for this permission. Try the
            // connection in any case: the network request also works without it
            // on many devices.
            if (password.isEmpty() && !preferences.contains(KEY_PASSWORD)) {
                showSettings(afterSave = { requestBriefcaseNetwork() }, hint = getString(R.string.password_missing))
            } else {
                requestBriefcaseNetwork()
            }
        }
    }

    private fun requestBriefcaseNetwork() {
        releaseNetwork()
        showPanel(getString(R.string.connecting, networkName), showConnect = false)

        val specifier = WifiNetworkSpecifier.Builder().setSsid(networkName).apply {
            if (password.isNotEmpty()) setWpa2Passphrase(password)
        }.build()
        val request = NetworkRequest.Builder()
            .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
            .removeCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            .setNetworkSpecifier(specifier)
            .build()

        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                connectivity.bindProcessToNetwork(network)
                runOnUiThread { checkAndLoad() }
            }

            override fun onUnavailable() {
                runOnUiThread {
                    showPanel(getString(R.string.connect_failed, networkName), showConnect = true)
                }
            }

            override fun onLost(network: Network) {
                connectivity.bindProcessToNetwork(null)
                runOnUiThread {
                    showPanel(getString(R.string.connection_lost), showConnect = true)
                }
            }
        }
        networkCallback = callback
        connectivity.requestNetwork(request, callback)
    }

    private fun releaseNetwork() {
        networkCallback?.let {
            try {
                connectivity.unregisterNetworkCallback(it)
            } catch (error: IllegalArgumentException) {
                // The callback was not registered.
            }
        }
        networkCallback = null
        connectivity.bindProcessToNetwork(null)
    }

    /**
     * The web app calls these methods as `window.BriefcaseApp`. The web view
     * loads only the briefcase web app, and the methods change nothing
     * without a confirmation from the user.
     */
    private inner class AppBridge {
        @JavascriptInterface
        fun version(): String = updater.installedVersion()

        @JavascriptInterface
        fun checkForUpdates() {
            runOnUiThread { checkForUpdates(manual = true) }
        }

        /**
         * Ask GitHub for the releases over the phone's internet, then give
         * the JSON (or null without internet) to window.briefcaseReleases.
         */
        @JavascriptInterface
        fun checkReleases() {
            Thread {
                val json = runCatching { updater.releasesJson() }.getOrNull()
                val argument = if (json != null) JSONObject.quote(json) else "null"
                runOnUiThread {
                    if (!isDestroyed) {
                        webView.evaluateJavascript("window.briefcaseReleases($argument)", null)
                    }
                }
            }.start()
        }

        /** The web app gives the briefcase version, for example "0.1.0". */
        @JavascriptInterface
        fun setBriefcaseVersion(version: String) {
            val clean = version.trim().removePrefix("v").take(MAX_VERSION_LENGTH)
            runOnUiThread { showVersions(briefcaseVersion = clean.ifEmpty { null }) }
        }
    }

    /** The title bar shows the briefcase version and, below it, the app version. */
    private fun showVersions(briefcaseVersion: String?) {
        val bar = actionBar ?: return
        bar.title = if (briefcaseVersion != null) {
            getString(R.string.title_with_version, briefcaseVersion)
        } else {
            getString(R.string.app_name)
        }
        bar.subtitle = getString(R.string.app_version, updater.installedVersion())
    }

    private fun showSettings(afterSave: (() -> Unit)? = null, hint: String? = null) {
        val density = resources.displayMetrics.density
        val nameField = EditText(this).apply {
            setText(networkName)
            setHint(R.string.network_name)
            inputType = InputType.TYPE_CLASS_TEXT
        }
        val passwordField = EditText(this).apply {
            setText(password)
            setHint(R.string.password)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val padding = (20 * density).toInt()
            setPadding(padding, padding / 2, padding, 0)
            if (hint != null) addView(TextView(context).apply { text = hint })
            addView(nameField)
            addView(passwordField)
        }
        val dialog = AlertDialog.Builder(this)
            .setTitle(R.string.settings)
            .setView(layout)
            .setPositiveButton(R.string.save, null)
            .setNegativeButton(R.string.cancel, null)
            .create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val name = nameField.text.toString().trim()
                val newPassword = passwordField.text.toString()
                when {
                    !Briefcase.isValidNetworkName(name) -> nameField.error = getString(R.string.network_name)
                    !Briefcase.isValidPassword(newPassword) -> passwordField.error = getString(R.string.password)
                    else -> {
                        preferences.edit()
                            .putString(KEY_NETWORK_NAME, name)
                            .putString(KEY_PASSWORD, newPassword)
                            .apply()
                        dialog.dismiss()
                        afterSave?.invoke()
                    }
                }
            }
        }
        dialog.show()
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menu.add(Menu.NONE, MENU_RELOAD, Menu.NONE, R.string.reload)
        menu.add(Menu.NONE, MENU_SETTINGS, Menu.NONE, R.string.settings)
        menu.add(Menu.NONE, MENU_CHECK_UPDATES, Menu.NONE, R.string.check_updates)
        menu.add(Menu.NONE, MENU_PRERELEASES, Menu.NONE, R.string.include_prereleases)
            .setCheckable(true)
            .setChecked(preferences.getBoolean(KEY_INCLUDE_PRERELEASES, false))
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean =
        when (item.itemId) {
            MENU_RELOAD -> {
                if (webView.visibility == View.VISIBLE) webView.reload() else checkAndLoad()
                true
            }
            MENU_SETTINGS -> {
                showSettings()
                true
            }
            MENU_CHECK_UPDATES -> {
                checkForUpdates(manual = true)
                true
            }
            MENU_PRERELEASES -> {
                val include = !item.isChecked
                item.isChecked = include
                preferences.edit().putBoolean(KEY_INCLUDE_PRERELEASES, include).apply()
                true
            }
            else -> super.onOptionsItemSelected(item)
        }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        @Suppress("DEPRECATION")
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != REQUEST_FILES) return
        val callback = fileCallback ?: return
        fileCallback = null
        if (resultCode != RESULT_OK || data == null) {
            callback.onReceiveValue(null)
            return
        }
        val clip = data.clipData
        val uris = if (clip != null) {
            Array(clip.itemCount) { index -> clip.getItemAt(index).uri }
        } else {
            WebChromeClient.FileChooserParams.parseResult(resultCode, data) ?: emptyArray()
        }
        callback.onReceiveValue(uris)
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (webView.visibility == View.VISIBLE && webView.canGoBack()) {
            webView.goBack()
        } else {
            @Suppress("DEPRECATION")
            super.onBackPressed()
        }
    }

    private companion object {
        const val PREFERENCES = "briefcase"
        const val BRIDGE_NAME = "BriefcaseApp"
        const val MAX_VERSION_LENGTH = 32
        const val KEY_NETWORK_NAME = "network_name"
        const val KEY_PASSWORD = "password"
        const val REQUEST_FILES = 1
        const val REQUEST_PERMISSION = 2
        const val REQUEST_SCAN_PERMISSION = 3
        const val RANGE_REFRESH_MS = 10_000L
        const val MENU_RELOAD = 1
        const val MENU_SETTINGS = 2
        const val MENU_CHECK_UPDATES = 3
        const val MENU_PRERELEASES = 4
        const val KEY_INCLUDE_PRERELEASES = "include_prereleases"
        const val KEY_LAST_UPDATE_CHECK = "last_update_check"
    }
}
