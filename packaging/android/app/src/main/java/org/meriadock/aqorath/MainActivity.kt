package org.meriadock.aqorath

import android.app.Activity
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.ViewGroup
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.TextView
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.ByteArrayInputStream

class MainActivity : Activity() {
    private val mainHandler = Handler(Looper.getMainLooper())
    private lateinit var webView: WebView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        webView = WebView(this).apply {
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT,
            )
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.allowFileAccess = false
            settings.allowContentAccess = false
            settings.mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
                settings.safeBrowsingEnabled = false
            }
            webViewClient = LocalOnlyWebViewClient()
        }
        setContentView(webView)

        val appContext = applicationContext
        val privateFiles = filesDir.absolutePath
        Thread {
            try {
                if (!Python.isStarted()) {
                    Python.start(AndroidPlatform(appContext))
                }
                val runtime = Python.getInstance().getModule("aqorath.android_runtime")
                val url = runtime.callAttr("start", privateFiles).toString()
                Log.i(TAG, "AQORATH_ANDROID_NETWORK_GUARD=loopback-only")
                mainHandler.post { webView.loadUrl(url) }
            } catch (exc: Throwable) {
                Log.e(TAG, "AQORATH_ANDROID_ERROR", exc)
                mainHandler.post {
                    val message = TextView(this).apply {
                        text = "Aqorath no pudo iniciar. Revisa el registro técnico de la aplicación."
                        textSize = 18f
                        setPadding(48, 48, 48, 48)
                    }
                    setContentView(message)
                }
            }
        }.start()
    }

    override fun onDestroy() {
        if (isFinishing && Python.isStarted()) {
            Thread {
                try {
                    Python.getInstance()
                        .getModule("aqorath.android_runtime")
                        .callAttr("stop")
                } catch (exc: Throwable) {
                    Log.w(TAG, "Aqorath local server shutdown reported an error", exc)
                }
            }.start()
        }
        webView.destroy()
        super.onDestroy()
    }

    @Suppress("DEPRECATION")
    override fun onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack()
        } else {
            super.onBackPressed()
        }
    }

    private inner class LocalOnlyWebViewClient : WebViewClient() {
        override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
            val uri = request?.url ?: return true
            return !isAllowedLoopback(uri)
        }

        override fun shouldInterceptRequest(
            view: WebView?,
            request: WebResourceRequest?,
        ): WebResourceResponse? {
            val uri = request?.url ?: return blockedResponse()
            return if (isAllowedLoopback(uri)) null else blockedResponse()
        }

        override fun onPageFinished(view: WebView?, url: String?) {
            super.onPageFinished(view, url)
            val uri = url?.let(Uri::parse)
            if (uri != null && isAllowedLoopback(uri)) {
                Log.i(TAG, "AQORATH_ANDROID_READY=$url")
            }
        }
    }

    private fun isAllowedLoopback(uri: Uri): Boolean {
        if (uri.scheme != "http") return false
        val host = uri.host?.lowercase() ?: return false
        return host == "127.0.0.1" || host == "localhost" || host == "::1"
    }

    private fun blockedResponse(): WebResourceResponse {
        val body = "Blocked by Aqorath local-only policy".toByteArray(Charsets.UTF_8)
        return WebResourceResponse(
            "text/plain",
            "utf-8",
            403,
            "Blocked",
            mapOf("Cache-Control" to "no-store"),
            ByteArrayInputStream(body),
        )
    }

    companion object {
        private const val TAG = "Aqorath"
    }
}
