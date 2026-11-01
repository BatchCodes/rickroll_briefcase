package io.github.batchcodes.briefcase

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.net.Uri
import android.net.wifi.WifiNetworkSpecifier
import android.os.Build
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.view.ViewGroup
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

    private val connectivity by lazy { getSystemService(ConnectivityManager::class.java) }
    private val preferences by lazy { getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE) }
    private var networkCallback: ConnectivityManager.NetworkCallback? = null
    private var fileCallback: ValueCallback<Array<Uri>>? = null

    private val networkName: String
        get() = preferences.getString(KEY_NETWORK_NAME, null) ?: Briefcase.DEFAULT_NETWORK_NAME

    private val password: String
        get() = preferences.getString(KEY_PASSWORD, null) ?: ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        buildViews()
        checkAndLoad()
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
        const val KEY_NETWORK_NAME = "network_name"
        const val KEY_PASSWORD = "password"
        const val REQUEST_FILES = 1
        const val REQUEST_PERMISSION = 2
        const val MENU_RELOAD = 1
        const val MENU_SETTINGS = 2
    }
}
