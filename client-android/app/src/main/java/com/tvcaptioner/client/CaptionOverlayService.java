package com.tvcaptioner.client;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.net.Uri;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.provider.Settings;
import android.text.TextUtils;
import android.util.DisplayMetrics;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.LinearLayout;
import android.widget.TextView;

public class CaptionOverlayService extends Service implements AudioCaptureLoop.Listener {
    static final String ACTION_STOP = "com.tvcaptioner.client.STOP";
    static final String EXTRA_PROJECTION_RESULT_CODE = "projection_result_code";
    static final String EXTRA_PROJECTION_DATA = "projection_data";

    private static final String CHANNEL_ID = "caption_overlay";
    private static final int NOTIFICATION_ID = 101;
    private static final long OVERLAY_REFRESH_MS = 1200L;

    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final Runnable overlayRefresh = new Runnable() {
        @Override
        public void run() {
            refreshOverlayWindow();
            mainHandler.postDelayed(this, OVERLAY_REFRESH_MS);
        }
    };

    private WindowManager windowManager;
    private WindowManager.LayoutParams overlayParams;
    private View overlayView;
    private TextView statusView;
    private TextView captionView;
    private AudioCaptureLoop captureLoop;
    private MediaProjection mediaProjection;
    private String lastCaption = "字幕会显示在这里";

    @Override
    public void onCreate() {
        super.onCreate();
        windowManager = (WindowManager) getSystemService(WINDOW_SERVICE);
        createNotificationChannel();
        startForeground(NOTIFICATION_ID, buildNotification("正在准备悬浮字幕"));
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            stopSelf();
            return START_NOT_STICKY;
        }

        if (!Settings.canDrawOverlays(this)) {
            openOverlaySettings();
            stopSelf();
            return START_NOT_STICKY;
        }

        if (overlayView != null) {
            removeOverlay();
        }
        showOverlay();
        startOverlayRefresh();
        if (captureLoop == null) {
            AppSettings settings = AppSettings.load(this);
            if (settings.useSystemAudio()) {
                mediaProjection = createMediaProjection(intent);
                if (mediaProjection == null) {
                    postState("需要授权", "请回到设置页获取系统声音权限");
                    stopSelf();
                    return START_NOT_STICKY;
                }
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    mediaProjection.registerCallback(new MediaProjection.Callback() {
                        @Override
                        public void onStop() {
                            postState("需要授权", "系统声音权限已取消");
                            stopSelf();
                        }
                    }, mainHandler);
                }
            }
            captureLoop = new AudioCaptureLoop(this, this, mediaProjection);
            captureLoop.start();
        }
        return AppSettings.load(this).useSystemAudio() ? START_NOT_STICKY : START_STICKY;
    }

    @Override
    public void onDestroy() {
        if (captureLoop != null) {
            captureLoop.stop();
            captureLoop = null;
        }
        if (mediaProjection != null) {
            mediaProjection.stop();
            mediaProjection = null;
        }
        removeOverlay();
        stopOverlayRefresh();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onListening() {
        postState("正在听...", lastCaption);
    }

    @Override
    public void onProcessing() {
        postState("正在翻译...", lastCaption);
    }

    @Override
    public void onCaption(CaptionResult result) {
        String text = result.translatedText.trim();
        if (text.isEmpty()) {
            text = result.sourceText.trim();
        }
        if (text.isEmpty()) {
            postState("未识别到字幕", lastCaption);
            return;
        }
        lastCaption = text;
        postState(languageStatus(result.detectedLanguage), text);
    }

    @Override
    public void onError(String message) {
        postState("需要处理", message);
    }

    private void showOverlay() {
        if (overlayView != null) {
            return;
        }

        AppSettings settings = AppSettings.load(this);
        int width = Math.min(getResources().getDisplayMetrics().widthPixels - dp(32), dp(640));

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(14), dp(10), dp(14), dp(12));
        root.setBackground(captionBackground(settings.backgroundColor, settings.opacityPercent));

        LinearLayout bar = new LinearLayout(this);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        bar.setOrientation(LinearLayout.HORIZONTAL);

        statusView = new TextView(this);
        statusView.setText("正在启动");
        statusView.setTextColor(Color.rgb(203, 213, 225));
        statusView.setTextSize(12);
        statusView.setSingleLine(true);
        statusView.setTypeface(Typeface.DEFAULT_BOLD);
        bar.addView(statusView, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1));

        TextView settingsButton = overlayButton("设置");
        settingsButton.setOnClickListener(v -> {
            Intent intent = new Intent(this, MainActivity.class);
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(intent);
        });
        bar.addView(settingsButton);

        TextView closeButton = overlayButton("停止");
        closeButton.setOnClickListener(v -> stopSelf());
        bar.addView(closeButton);

        captionView = new TextView(this);
        captionView.setText(lastCaption);
        captionView.setTextColor(Color.WHITE);
        captionView.setTextSize(settings.fontSizeSp);
        captionView.setGravity(Gravity.CENTER);
        captionView.setMaxLines(3);
        captionView.setEllipsize(TextUtils.TruncateAt.END);
        captionView.setLineSpacing(dp(2), 1.0f);
        captionView.setTypeface(Typeface.DEFAULT_BOLD);
        LinearLayout.LayoutParams captionLayout = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
        );
        captionLayout.topMargin = dp(6);

        root.addView(bar);
        root.addView(captionView, captionLayout);
        root.setOnTouchListener(new DragTouchListener());

        int type = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
                : WindowManager.LayoutParams.TYPE_PHONE;
        int flags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                | WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL
                | WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
                | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS;
        overlayParams = new WindowManager.LayoutParams(
                width,
                WindowManager.LayoutParams.WRAP_CONTENT,
                type,
                flags,
                PixelFormat.TRANSLUCENT
        );
        overlayParams.gravity = Gravity.TOP | Gravity.START;
        overlayParams.setTitle("TV Captioner Overlay");
        DisplayMetrics metrics = getResources().getDisplayMetrics();
        overlayParams.x = Math.max(0, (metrics.widthPixels - width) * settings.positionXPercent / 100);
        overlayParams.y = Math.max(dp(8), (metrics.heightPixels - dp(160)) * settings.positionYPercent / 100);
        overlayView = root;
        windowManager.addView(overlayView, overlayParams);
    }

    private void removeOverlay() {
        if (overlayView == null) {
            return;
        }
        try {
            windowManager.removeView(overlayView);
        } catch (IllegalArgumentException ignored) {
        }
        overlayView = null;
        overlayParams = null;
    }

    private void startOverlayRefresh() {
        mainHandler.removeCallbacks(overlayRefresh);
        mainHandler.postDelayed(overlayRefresh, OVERLAY_REFRESH_MS);
    }

    private void stopOverlayRefresh() {
        mainHandler.removeCallbacks(overlayRefresh);
    }

    private void refreshOverlayWindow() {
        if (overlayView == null || overlayParams == null) {
            if (Settings.canDrawOverlays(this)) {
                showOverlay();
            }
            return;
        }
        try {
            overlayView.setVisibility(View.VISIBLE);
            overlayView.bringToFront();
            windowManager.updateViewLayout(overlayView, overlayParams);
        } catch (IllegalArgumentException exc) {
            overlayView = null;
            overlayParams = null;
            if (Settings.canDrawOverlays(this)) {
                showOverlay();
            }
        }
    }

    private void postState(String status, String caption) {
        mainHandler.post(() -> {
            if (statusView != null) {
                statusView.setText(status);
            }
            if (captionView != null && caption != null && !caption.trim().isEmpty()) {
                captionView.setText(caption);
            }
            NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
            manager.notify(NOTIFICATION_ID, buildNotification(status));
        });
    }

    private String languageStatus(String detectedLanguage) {
        if (detectedLanguage == null || detectedLanguage.trim().isEmpty()) {
            return "已翻译";
        }
        return "已翻译 · " + detectedLanguage;
    }

    private TextView overlayButton(String text) {
        TextView button = new TextView(this);
        button.setText(text);
        button.setTextColor(Color.rgb(226, 232, 240));
        button.setTextSize(12);
        button.setGravity(Gravity.CENTER);
        button.setPadding(dp(8), dp(4), dp(8), dp(4));
        return button;
    }

    private GradientDrawable captionBackground(int color, int opacityPercent) {
        int alpha = Math.max(35, Math.min(95, opacityPercent)) * 255 / 100;
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(Color.argb(alpha, Color.red(color), Color.green(color), Color.blue(color)));
        drawable.setCornerRadius(dp(8));
        drawable.setStroke(dp(1), Color.argb(110, 148, 163, 184));
        return drawable;
    }

    private Notification buildNotification(String text) {
        Intent activityIntent = new Intent(this, MainActivity.class);
        PendingIntent activityPendingIntent = PendingIntent.getActivity(
                this,
                0,
                activityIntent,
                PendingIntent.FLAG_UPDATE_CURRENT | immutableFlag()
        );
        Intent stopIntent = new Intent(this, CaptionOverlayService.class);
        stopIntent.setAction(ACTION_STOP);
        PendingIntent stopPendingIntent = PendingIntent.getService(
                this,
                1,
                stopIntent,
                PendingIntent.FLAG_UPDATE_CURRENT | immutableFlag()
        );

        Notification.Builder builder = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? new Notification.Builder(this, CHANNEL_ID)
                : new Notification.Builder(this);
        return builder
                .setSmallIcon(R.drawable.ic_stat_caption)
                .setContentTitle("TV Captioner 悬浮字幕")
                .setContentText(text)
                .setContentIntent(activityPendingIntent)
                .setOngoing(true)
                .addAction(R.drawable.ic_stat_caption, "停止", stopPendingIntent)
                .build();
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return;
        }
        NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID,
                "悬浮字幕",
                NotificationManager.IMPORTANCE_LOW
        );
        channel.setDescription("TV Captioner 正在录音并显示悬浮字幕");
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        manager.createNotificationChannel(channel);
    }

    private MediaProjection createMediaProjection(Intent intent) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q || intent == null) {
            return null;
        }
        Intent data = intent.getParcelableExtra(EXTRA_PROJECTION_DATA);
        int resultCode = intent.getIntExtra(EXTRA_PROJECTION_RESULT_CODE, Activity.RESULT_CANCELED);
        if (data == null || resultCode != Activity.RESULT_OK) {
            return null;
        }
        MediaProjectionManager manager = (MediaProjectionManager) getSystemService(Context.MEDIA_PROJECTION_SERVICE);
        return manager == null ? null : manager.getMediaProjection(resultCode, data);
    }

    private void openOverlaySettings() {
        Intent intent = new Intent(
                Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                Uri.parse("package:" + getPackageName())
        );
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        startActivity(intent);
    }

    private int immutableFlag() {
        return Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0;
    }

    private int dp(int value) {
        return (int) (value * getResources().getDisplayMetrics().density + 0.5f);
    }

    private final class DragTouchListener implements View.OnTouchListener {
        private int startX;
        private int startY;
        private float touchStartX;
        private float touchStartY;

        @Override
        public boolean onTouch(View view, MotionEvent event) {
            switch (event.getAction()) {
                case MotionEvent.ACTION_DOWN:
                    startX = overlayParams.x;
                    startY = overlayParams.y;
                    touchStartX = event.getRawX();
                    touchStartY = event.getRawY();
                    return true;
                case MotionEvent.ACTION_MOVE:
                    overlayParams.x = startX + (int) (event.getRawX() - touchStartX);
                    overlayParams.y = Math.max(dp(8), startY + (int) (event.getRawY() - touchStartY));
                    windowManager.updateViewLayout(overlayView, overlayParams);
                    return true;
                default:
                    return false;
            }
        }
    }
}
