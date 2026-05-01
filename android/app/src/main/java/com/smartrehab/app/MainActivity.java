package com.smartrehab.app;

import android.Manifest;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.PermissionRequest;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebChromeClient.FileChooserParams;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.List;

public class MainActivity extends Activity {
    private static final String PREFS_NAME = "smartrehab_android";
    private static final String PREF_SERVER_URL = "server_url";
    private static final int FILE_CHOOSER_REQUEST = 2101;
    private static final int MEDIA_PERMISSION_REQUEST = 2102;

    private static final int COLOR_PRIMARY = Color.rgb(0, 122, 255);
    private static final int COLOR_BACKGROUND = Color.rgb(247, 250, 252);
    private static final int COLOR_TEXT = Color.rgb(31, 41, 55);
    private static final int COLOR_MUTED = Color.rgb(99, 110, 114);

    private SharedPreferences prefs;
    private WebView webView;
    private ValueCallback<Uri[]> filePathCallback;
    private String currentServerUrl;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);

        if (BuildConfig.DEBUG) {
            WebView.setWebContentsDebuggingEnabled(true);
        }

        String savedUrl = prefs.getString(PREF_SERVER_URL, "");
        if (savedUrl == null || savedUrl.trim().isEmpty()) {
            showSetup("http://192.168.1.100:8501", null);
        } else {
            openWebApp(savedUrl);
        }
    }

    private void showSetup(String initialUrl, String errorText) {
        webView = null;

        ScrollView scrollView = new ScrollView(this);
        scrollView.setFillViewport(true);
        scrollView.setBackgroundColor(COLOR_BACKGROUND);

        LinearLayout screen = new LinearLayout(this);
        screen.setOrientation(LinearLayout.VERTICAL);
        screen.setGravity(Gravity.CENTER_HORIZONTAL);
        screen.setPadding(dp(24), dp(32), dp(24), dp(24));
        scrollView.addView(screen, new ScrollView.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        ));

        TextView title = new TextView(this);
        title.setText("SmartRehab");
        title.setTextColor(COLOR_TEXT);
        title.setTextSize(28);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        screen.addView(title);

        TextView subtitle = new TextView(this);
        subtitle.setText("Android 連線設定");
        subtitle.setTextColor(COLOR_MUTED);
        subtitle.setTextSize(16);
        subtitle.setPadding(0, dp(4), 0, dp(24));
        screen.addView(subtitle);

        if (errorText != null && !errorText.trim().isEmpty()) {
            TextView error = new TextView(this);
            error.setText(errorText);
            error.setTextColor(Color.rgb(185, 28, 28));
            error.setTextSize(14);
            error.setPadding(0, 0, 0, dp(16));
            screen.addView(error, matchWrap());
        }

        TextView label = new TextView(this);
        label.setText("伺服器網址");
        label.setTextColor(COLOR_TEXT);
        label.setTextSize(14);
        label.setTypeface(Typeface.DEFAULT_BOLD);
        screen.addView(label, matchWrap());

        EditText urlInput = new EditText(this);
        urlInput.setSingleLine(true);
        urlInput.setInputType(InputType.TYPE_TEXT_VARIATION_URI);
        urlInput.setText(initialUrl);
        urlInput.setSelectAllOnFocus(false);
        urlInput.setTextSize(16);
        urlInput.setPadding(dp(14), dp(10), dp(14), dp(10));
        LinearLayout.LayoutParams inputParams = matchWrap();
        inputParams.topMargin = dp(8);
        screen.addView(urlInput, inputParams);

        Button openButton = primaryButton("開啟 SmartRehab");
        LinearLayout.LayoutParams buttonParams = matchWrap();
        buttonParams.topMargin = dp(16);
        screen.addView(openButton, buttonParams);

        TextView help = new TextView(this);
        help.setText("Wi-Fi 使用 start_android_server.bat，網址通常是 http://電腦IP:8501。USB 測試可使用 start_android_usb_server.bat，網址是 http://127.0.0.1:8501。");
        help.setTextColor(COLOR_MUTED);
        help.setTextSize(14);
        help.setLineSpacing(0, 1.15f);
        LinearLayout.LayoutParams helpParams = matchWrap();
        helpParams.topMargin = dp(18);
        screen.addView(help, helpParams);

        openButton.setOnClickListener((View view) -> {
            String normalizedUrl = normalizeServerUrl(urlInput.getText().toString());
            if (normalizedUrl.isEmpty()) {
                Toast.makeText(this, "請輸入伺服器網址", Toast.LENGTH_SHORT).show();
                return;
            }
            prefs.edit().putString(PREF_SERVER_URL, normalizedUrl).apply();
            openWebApp(normalizedUrl);
        });

        setContentView(scrollView);
    }

    private void openWebApp(String serverUrl) {
        currentServerUrl = normalizeServerUrl(serverUrl);
        requestMediaPermissions();

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.WHITE);

        LinearLayout toolbar = new LinearLayout(this);
        toolbar.setOrientation(LinearLayout.HORIZONTAL);
        toolbar.setGravity(Gravity.CENTER_VERTICAL);
        toolbar.setPadding(dp(12), dp(6), dp(8), dp(6));
        toolbar.setBackgroundColor(Color.WHITE);

        TextView title = new TextView(this);
        title.setText("SmartRehab");
        title.setTextColor(COLOR_TEXT);
        title.setTextSize(18);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        LinearLayout.LayoutParams titleParams = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        toolbar.addView(title, titleParams);

        Button refreshButton = toolbarButton("重整");
        toolbar.addView(refreshButton);

        Button settingsButton = toolbarButton("設定");
        toolbar.addView(settingsButton);

        root.addView(toolbar, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(52)
        ));

        FrameLayout webFrame = new FrameLayout(this);
        webView = new WebView(this);
        configureWebView(webView);
        webFrame.addView(webView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
        ));
        root.addView(webFrame, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                0,
                1f
        ));

        refreshButton.setOnClickListener((View view) -> webView.reload());
        settingsButton.setOnClickListener((View view) -> showSetup(currentServerUrl, null));

        setContentView(root);
        webView.loadUrl(currentServerUrl);
    }

    private void configureWebView(WebView view) {
        WebSettings settings = view.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setMediaPlaybackRequiresUserGesture(false);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            settings.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);
            CookieManager.getInstance().setAcceptThirdPartyCookies(view, true);
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            settings.setSafeBrowsingEnabled(true);
        }
        CookieManager.getInstance().setAcceptCookie(true);

        view.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if (isAppUrl(uri) || isInternalScheme(uri)) {
                    return false;
                }
                openExternal(uri);
                return true;
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && request.isForMainFrame()) {
                    String detail = error == null ? "無法連到 Streamlit 伺服器。" : error.getDescription().toString();
                    showSetup(currentServerUrl, "連線失敗：" + detail);
                }
            }
        });

        view.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(PermissionRequest request) {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                    runOnUiThread(() -> request.grant(request.getResources()));
                }
            }

            @Override
            public boolean onShowFileChooser(
                    WebView webView,
                    ValueCallback<Uri[]> filePathCallback,
                    FileChooserParams fileChooserParams
            ) {
                if (MainActivity.this.filePathCallback != null) {
                    MainActivity.this.filePathCallback.onReceiveValue(null);
                }
                MainActivity.this.filePathCallback = filePathCallback;

                Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType("*/*");
                intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
                intent.putExtra(Intent.EXTRA_MIME_TYPES, new String[]{"image/*", "video/*", "application/pdf"});

                try {
                    startActivityForResult(Intent.createChooser(intent, "選擇檔案"), FILE_CHOOSER_REQUEST);
                    return true;
                } catch (ActivityNotFoundException ex) {
                    MainActivity.this.filePathCallback = null;
                    Toast.makeText(MainActivity.this, "找不到可用的檔案選擇器", Toast.LENGTH_SHORT).show();
                    return false;
                }
            }
        });
    }

    private void requestMediaPermissions() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) {
            return;
        }

        List<String> permissions = new ArrayList<>();
        if (checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            permissions.add(Manifest.permission.CAMERA);
        }
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            permissions.add(Manifest.permission.RECORD_AUDIO);
        }

        if (!permissions.isEmpty()) {
            requestPermissions(permissions.toArray(new String[0]), MEDIA_PERMISSION_REQUEST);
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == FILE_CHOOSER_REQUEST) {
            Uri[] results = null;
            if (resultCode == RESULT_OK && data != null) {
                ClipData clipData = data.getClipData();
                if (clipData != null) {
                    results = new Uri[clipData.getItemCount()];
                    for (int i = 0; i < clipData.getItemCount(); i++) {
                        results[i] = clipData.getItemAt(i).getUri();
                    }
                } else if (data.getData() != null) {
                    results = new Uri[]{data.getData()};
                }
            }

            if (filePathCallback != null) {
                filePathCallback.onReceiveValue(results);
                filePathCallback = null;
            }
            return;
        }

        super.onActivityResult(requestCode, resultCode, data);
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
            return;
        }
        super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            webView.stopLoading();
            webView.destroy();
            webView = null;
        }
        super.onDestroy();
    }

    private boolean isAppUrl(Uri uri) {
        if (uri == null || currentServerUrl == null) {
            return false;
        }
        Uri base = Uri.parse(currentServerUrl);
        return safeEquals(uri.getScheme(), base.getScheme())
                && safeEquals(uri.getHost(), base.getHost())
                && effectivePort(uri) == effectivePort(base);
    }

    private boolean isInternalScheme(Uri uri) {
        if (uri == null || uri.getScheme() == null) {
            return true;
        }
        String scheme = uri.getScheme();
        return "about".equalsIgnoreCase(scheme)
                || "data".equalsIgnoreCase(scheme)
                || "blob".equalsIgnoreCase(scheme);
    }

    private void openExternal(Uri uri) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, uri));
        } catch (ActivityNotFoundException ignored) {
            Toast.makeText(this, "無法開啟外部連結", Toast.LENGTH_SHORT).show();
        }
    }

    private int effectivePort(Uri uri) {
        if (uri.getPort() > 0) {
            return uri.getPort();
        }
        if ("https".equalsIgnoreCase(uri.getScheme())) {
            return 443;
        }
        return 80;
    }

    private boolean safeEquals(String a, String b) {
        if (a == null) {
            return b == null;
        }
        return a.equalsIgnoreCase(b);
    }

    private String normalizeServerUrl(String raw) {
        String url = raw == null ? "" : raw.trim();
        if (url.isEmpty()) {
            return "";
        }
        if (!url.startsWith("http://") && !url.startsWith("https://")) {
            url = "http://" + url;
        }
        while (url.endsWith("/")) {
            url = url.substring(0, url.length() - 1);
        }
        return url;
    }

    private Button primaryButton(String text) {
        Button button = new Button(this);
        button.setText(text);
        button.setTextColor(Color.WHITE);
        button.setTextSize(16);
        button.setAllCaps(false);
        button.setBackgroundColor(COLOR_PRIMARY);
        button.setMinHeight(dp(48));
        return button;
    }

    private Button toolbarButton(String text) {
        Button button = new Button(this);
        button.setText(text);
        button.setTextSize(14);
        button.setAllCaps(false);
        button.setMinWidth(dp(64));
        return button;
    }

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
