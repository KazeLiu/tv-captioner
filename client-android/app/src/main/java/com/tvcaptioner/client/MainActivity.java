package com.tvcaptioner.client;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.media.projection.MediaProjectionManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.text.InputType;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.View;
import android.widget.AdapterView;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;

import java.util.List;

public class MainActivity extends Activity {
    private static final int REQ_AUDIO = 11;
    private static final int REQ_NOTIFICATIONS = 12;
    private static final int REQ_MEDIA_PROJECTION = 13;

    private EditText hostInput;
    private EditText portInput;
    private Spinner audioSourceSpinner;
    private Spinner asrModelSpinner;
    private Spinner translationModelSpinner;
    private Spinner sourceSpinner;
    private Spinner targetSpinner;
    private Spinner colorSpinner;
    private TextView chunkLabel;
    private TextView fontLabel;
    private TextView opacityLabel;
    private TextView positionLabel;
    private TextView statusView;
    private TextView audioPermissionStatus;
    private TextView overlayPermissionStatus;
    private TextView notificationPermissionStatus;
    private TextView systemAudioPermissionStatus;
    private FrameLayout previewFrame;
    private TextView previewCaption;
    private SeekBar chunkSeek;
    private SeekBar fontSeek;
    private SeekBar opacitySeek;

    private LanguageOption[] sourceOptions;
    private LanguageOption[] targetOptions;
    private CaptionColorOption[] colorOptions;
    private AudioSourceOption[] audioSourceOptions;
    private Intent projectionData;
    private int projectionResultCode = RESULT_CANCELED;
    private boolean startAfterProjectionGrant;
    private int previewXPercent = 50;
    private int previewYPercent = 82;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        sourceOptions = LanguageOption.sourceOptions();
        targetOptions = LanguageOption.targetOptions();
        colorOptions = CaptionColorOption.options();
        audioSourceOptions = AudioSourceOption.options();
        buildUi();
        loadSettingsIntoUi();
        refreshPermissionStatus();
        refreshBackendModels();
    }

    @Override
    protected void onResume() {
        super.onResume();
        refreshPermissionStatus();
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        refreshPermissionStatus();
        if ((requestCode == REQ_AUDIO || requestCode == REQ_NOTIFICATIONS)
                && grantResults.length > 0
                && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
            startCaptions();
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQ_MEDIA_PROJECTION) {
            return;
        }
        if (resultCode == RESULT_OK && data != null) {
            projectionResultCode = resultCode;
            projectionData = data;
            statusView.setText("系统声音权限已授权");
            if (startAfterProjectionGrant) {
                startAfterProjectionGrant = false;
                startCaptions();
            }
        } else {
            startAfterProjectionGrant = false;
            projectionResultCode = RESULT_CANCELED;
            projectionData = null;
            statusView.setText("系统声音权限未授权");
        }
        refreshPermissionStatus();
    }

    private void buildUi() {
        ScrollView scrollView = new ScrollView(this);
        scrollView.setFillViewport(true);
        scrollView.setBackgroundColor(Color.rgb(248, 250, 252));

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(20), dp(28), dp(20), dp(24));
        scrollView.addView(root);

        TextView title = new TextView(this);
        title.setText("TV Captioner");
        title.setTextColor(Color.rgb(15, 23, 42));
        title.setTextSize(28);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        root.addView(title);

        TextView subtitle = new TextView(this);
        subtitle.setText("悬浮字幕客户端");
        subtitle.setTextColor(Color.rgb(71, 85, 105));
        subtitle.setTextSize(14);
        LinearLayout.LayoutParams subtitleParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
        );
        subtitleParams.bottomMargin = dp(18);
        root.addView(subtitle, subtitleParams);

        root.addView(permissionPanel());

        LinearLayout audioPanel = panel();
        audioPanel.addView(sectionTitle("音频来源"));
        audioSourceSpinner = audioSourceSpinner(audioSourceOptions);
        audioPanel.addView(field("采集声音", audioSourceSpinner));
        root.addView(audioPanel);

        LinearLayout serverPanel = panel();
        serverPanel.addView(sectionTitle("后端"));
        hostInput = input("电脑局域网 IP，例如 192.168.1.8");
        serverPanel.addView(field("地址", hostInput));
        portInput = input("8765");
        portInput.setInputType(InputType.TYPE_CLASS_NUMBER);
        serverPanel.addView(field("端口", portInput));
        asrModelSpinner = modelSpinner("正在获取转写模型...");
        serverPanel.addView(field("转写模型", asrModelSpinner));
        translationModelSpinner = modelSpinner("正在获取翻译模型...");
        serverPanel.addView(field("翻译模型", translationModelSpinner));

        Button refreshModelsButton = secondaryButton("刷新模型列表");
        refreshModelsButton.setOnClickListener(v -> refreshBackendModels());
        serverPanel.addView(refreshModelsButton, fullWidthButtonParams());
        root.addView(serverPanel);

        LinearLayout languagePanel = panel();
        languagePanel.addView(sectionTitle("语言"));
        sourceSpinner = spinner(sourceOptions);
        languagePanel.addView(field("源语言", sourceSpinner));
        targetSpinner = spinner(targetOptions);
        languagePanel.addView(field("翻译为", targetSpinner));
        root.addView(languagePanel);

        LinearLayout captionPanel = panel();
        captionPanel.addView(sectionTitle("悬浮窗"));
        chunkLabel = valueLabel("");
        chunkSeek = seek(2, 8);
        captionPanel.addView(sliderField("分片秒数", chunkLabel, chunkSeek));
        fontLabel = valueLabel("");
        fontSeek = seek(16, 30);
        captionPanel.addView(sliderField("字幕字号", fontLabel, fontSeek));
        colorSpinner = colorSpinner(colorOptions);
        captionPanel.addView(field("文字背景颜色", colorSpinner));
        opacityLabel = valueLabel("");
        opacitySeek = seek(45, 92);
        captionPanel.addView(sliderField("背景透明度", opacityLabel, opacitySeek));
        positionLabel = valueLabel("");
        captionPanel.addView(previewField());
        root.addView(captionPanel);

        Button saveButton = primaryButton("保存设置");
        saveButton.setOnClickListener(v -> saveSettingsFromUi());
        root.addView(saveButton, fullWidthButtonParams());

        Button startButton = primaryButton("开始悬浮字幕");
        startButton.setOnClickListener(v -> startCaptions());
        root.addView(startButton, fullWidthButtonParams());

        Button stopButton = secondaryButton("停止悬浮字幕");
        stopButton.setOnClickListener(v -> stopService(new Intent(this, CaptionOverlayService.class)));
        root.addView(stopButton, fullWidthButtonParams());

        statusView = new TextView(this);
        statusView.setTextColor(Color.rgb(71, 85, 105));
        statusView.setTextSize(13);
        statusView.setPadding(0, dp(12), 0, 0);
        root.addView(statusView);

        setContentView(scrollView);
    }

    private void loadSettingsIntoUi() {
        AppSettings settings = AppSettings.load(this);
        hostInput.setText(settings.host);
        portInput.setText(String.valueOf(settings.port));
        audioSourceSpinner.setSelection(AudioSourceOption.indexOf(audioSourceOptions, settings.audioSource));
        sourceSpinner.setSelection(LanguageOption.indexOf(sourceOptions, settings.sourceLanguage));
        targetSpinner.setSelection(LanguageOption.indexOf(targetOptions, settings.targetLanguage));
        colorSpinner.setSelection(CaptionColorOption.indexOf(colorOptions, settings.backgroundColor));
        chunkSeek.setProgress(settings.chunkSeconds - 2);
        fontSeek.setProgress(settings.fontSizeSp - 16);
        opacitySeek.setProgress(settings.opacityPercent - 45);
        previewXPercent = settings.positionXPercent;
        previewYPercent = settings.positionYPercent;
        bindSeekLabels();
    }

    private void bindSeekLabels() {
        updateSeekLabels();
        chunkSeek.setOnSeekBarChangeListener(simpleSeekListener(this::updateSeekLabels));
        fontSeek.setOnSeekBarChangeListener(simpleSeekListener(this::updateSeekLabels));
        opacitySeek.setOnSeekBarChangeListener(simpleSeekListener(this::updateSeekLabels));
    }

    private SeekBar.OnSeekBarChangeListener simpleSeekListener(Runnable changed) {
        return new SeekBar.OnSeekBarChangeListener() {
            @Override
            public void onProgressChanged(SeekBar seekBar, int progress, boolean fromUser) {
                changed.run();
            }

            @Override
            public void onStartTrackingTouch(SeekBar seekBar) {
            }

            @Override
            public void onStopTrackingTouch(SeekBar seekBar) {
            }
        };
    }

    private void updateSeekLabels() {
        chunkLabel.setText((chunkSeek.getProgress() + 2) + " 秒");
        fontLabel.setText((fontSeek.getProgress() + 16) + " sp");
        opacityLabel.setText((opacitySeek.getProgress() + 45) + "%");
        positionLabel.setText("位置 " + previewXPercent + "%, " + previewYPercent + "%");
        updatePreview();
    }

    private void saveSettingsFromUi() {
        AppSettings settings = readSettings(false);
        if (settings == null) {
            return;
        }
        settings.save(this);
        Toast.makeText(this, "已保存", Toast.LENGTH_SHORT).show();
        refreshBackendModels();
    }

    private AppSettings readSettings(boolean requireModels) {
        String host = hostInput.getText().toString().trim();
        if (host.isEmpty()) {
            toast("请填写后端地址");
            return null;
        }

        int port;
        try {
            port = Integer.parseInt(portInput.getText().toString().trim());
        } catch (NumberFormatException exc) {
            toast("端口格式不对");
            return null;
        }
        if (port < 1 || port > 65535) {
            toast("端口范围应为 1-65535");
            return null;
        }

        AudioSourceOption audioSource = (AudioSourceOption) audioSourceSpinner.getSelectedItem();
        LanguageOption source = (LanguageOption) sourceSpinner.getSelectedItem();
        LanguageOption target = (LanguageOption) targetSpinner.getSelectedItem();
        AppSettings saved = AppSettings.load(this);
        String asrModel = selectedModelKey(asrModelSpinner, saved.asrModel, requireModels);
        String translationModel = selectedModelKey(translationModelSpinner, saved.translationModel, requireModels);
        if (requireModels && (asrModel.trim().isEmpty() || translationModel.trim().isEmpty())) {
            toast("请先获取并选择可用模型");
            statusView.setText("没有可用模型，请确认后端已经下载转写模型和翻译模型");
            return null;
        }
        return new AppSettings(
                host,
                port,
                audioSource.value,
                source.value,
                target.value,
                asrModel,
                translationModel,
                chunkSeek.getProgress() + 2,
                fontSeek.getProgress() + 16,
                opacitySeek.getProgress() + 45,
                ((CaptionColorOption) colorSpinner.getSelectedItem()).color,
                previewXPercent,
                previewYPercent
        );
    }

    private void startCaptions() {
        AppSettings settings = readSettings(true);
        if (settings == null) {
            return;
        }
        settings.save(this);

        if (!hasAudioPermission()) {
            requestPermissions(new String[] {Manifest.permission.RECORD_AUDIO}, REQ_AUDIO);
            statusView.setText("请允许音频录制权限");
            return;
        }
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[] {Manifest.permission.POST_NOTIFICATIONS}, REQ_NOTIFICATIONS);
            statusView.setText("请允许通知权限");
            return;
        }
        if (!Settings.canDrawOverlays(this)) {
            openOverlaySettings();
            return;
        }
        if (settings.useSystemAudio()) {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
                statusView.setText("系统播放声音采集需要 Android 10 或更高版本");
                return;
            }
            if (projectionData == null || projectionResultCode != RESULT_OK) {
                requestSystemAudioPermission(true);
                return;
            }
        }

        Intent intent = new Intent(this, CaptionOverlayService.class);
        if (settings.useSystemAudio()) {
            intent.putExtra(CaptionOverlayService.EXTRA_PROJECTION_RESULT_CODE, projectionResultCode);
            intent.putExtra(CaptionOverlayService.EXTRA_PROJECTION_DATA, projectionData);
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent);
        } else {
            startService(intent);
        }
        statusView.setText("悬浮字幕已启动");
    }

    private void refreshBackendModels() {
        AppSettings settings = readSettings(false);
        if (settings == null) {
            return;
        }
        settings.save(this);
        statusView.setText("正在获取后端模型列表...");
        new Thread(() -> {
            String message;
            BackendModels models = null;
            try {
                models = new BackendClient(settings).fetchModels();
                message = "已获取模型：转写 " + models.asrModels.size() + " 个，翻译 " + models.translationModels.size() + " 个";
            } catch (Exception exc) {
                message = "获取模型失败：" + cleanError(exc.getMessage());
            }
            BackendModels finalModels = models;
            String finalMessage = message;
            runOnUiThread(() -> {
                if (finalModels != null) {
                    applyModelOptions(asrModelSpinner, finalModels.asrModels, settings.asrModel, "未发现可用转写模型");
                    applyModelOptions(
                            translationModelSpinner,
                            finalModels.translationModels,
                            settings.translationModel,
                            "未发现可用翻译模型"
                    );
                    AppSettings updated = readSettings(false);
                    if (updated != null) {
                        updated.save(this);
                    }
                }
                statusView.setText(finalMessage);
            });
        }, "BackendModelFetch").start();
    }

    private void refreshPermissionStatus() {
        String audio = hasAudioPermission() ? "已授权" : "未授权";
        String overlay = Settings.canDrawOverlays(this) ? "已授权" : "未授权";
        String notification = hasNotificationPermission() ? "已授权" : "未授权";
        String systemAudio = projectionData != null && projectionResultCode == RESULT_OK ? "已授权（本次运行）" : "未授权";

        if (audioPermissionStatus != null) {
            audioPermissionStatus.setText(audio);
        }
        if (overlayPermissionStatus != null) {
            overlayPermissionStatus.setText(overlay);
        }
        if (notificationPermissionStatus != null) {
            notificationPermissionStatus.setText(notification);
        }
        if (systemAudioPermissionStatus != null) {
            systemAudioPermissionStatus.setText(systemAudio);
        }
        if (statusView != null) {
            statusView.setText("悬浮窗" + overlay + " · 音频录制" + audio);
        }
    }

    private boolean hasAudioPermission() {
        return checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED;
    }

    private boolean hasNotificationPermission() {
        return Build.VERSION.SDK_INT < 33
                || checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED;
    }

    private void openOverlaySettings() {
        Intent intent = new Intent(
                Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                Uri.parse("package:" + getPackageName())
        );
        startActivity(intent);
        statusView.setText("请允许 TV Captioner 显示在其他应用上层");
    }

    private void requestSystemAudioPermission(boolean startAfterGrant) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
            statusView.setText("系统播放声音采集需要 Android 10 或更高版本");
            return;
        }
        startAfterProjectionGrant = startAfterGrant;
        MediaProjectionManager manager = (MediaProjectionManager) getSystemService(MEDIA_PROJECTION_SERVICE);
        if (manager == null) {
            statusView.setText("当前系统不支持系统声音授权");
            return;
        }
        statusView.setText("请在系统弹窗中允许采集播放声音");
        startActivityForResult(manager.createScreenCaptureIntent(), REQ_MEDIA_PROJECTION);
    }

    private void clearSystemAudioPermission() {
        startAfterProjectionGrant = false;
        projectionResultCode = RESULT_CANCELED;
        projectionData = null;
        stopService(new Intent(this, CaptionOverlayService.class));
        statusView.setText("已取消本次系统声音授权");
        refreshPermissionStatus();
    }

    private void openAppSettings() {
        Intent intent = new Intent(
                Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                Uri.parse("package:" + getPackageName())
        );
        startActivity(intent);
    }

    private LinearLayout panel() {
        LinearLayout panel = new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setPadding(dp(16), dp(14), dp(16), dp(12));
        panel.setBackground(roundRect(Color.WHITE, dp(8), Color.rgb(226, 232, 240)));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
        );
        params.bottomMargin = dp(12);
        panel.setLayoutParams(params);
        return panel;
    }

    private LinearLayout permissionPanel() {
        LinearLayout panel = panel();
        panel.addView(sectionTitle("权限"));

        audioPermissionStatus = valueLabel("");
        panel.addView(permissionRow(
                "音频录制",
                "用于读取麦克风，系统声音模式也需要它来创建音频采集器。",
                audioPermissionStatus,
                v -> requestPermissions(new String[] {Manifest.permission.RECORD_AUDIO}, REQ_AUDIO),
                v -> openAppSettings()
        ));

        overlayPermissionStatus = valueLabel("");
        panel.addView(permissionRow(
                "悬浮窗",
                "用于把实时字幕显示在其他应用或视频画面上层。",
                overlayPermissionStatus,
                v -> openOverlaySettings(),
                v -> openOverlaySettings()
        ));

        notificationPermissionStatus = valueLabel("");
        panel.addView(permissionRow(
                "通知",
                "用于前台服务运行时展示状态，并提供停止入口。",
                notificationPermissionStatus,
                v -> {
                    if (Build.VERSION.SDK_INT >= 33) {
                        requestPermissions(new String[] {Manifest.permission.POST_NOTIFICATIONS}, REQ_NOTIFICATIONS);
                    } else {
                        statusView.setText("当前系统不需要单独获取通知权限");
                    }
                },
                v -> openAppSettings()
        ));

        systemAudioPermissionStatus = valueLabel("");
        panel.addView(permissionRow(
                "系统播放声音",
                "用于采集其他 App 播放的媒体声音；受系统和播放 App 保护策略限制。",
                systemAudioPermissionStatus,
                v -> requestSystemAudioPermission(false),
                v -> clearSystemAudioPermission()
        ));
        return panel;
    }

    private View permissionRow(
            String title,
            String purpose,
            TextView status,
            View.OnClickListener grant,
            View.OnClickListener cancel
    ) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.VERTICAL);
        row.setPadding(0, dp(6), 0, dp(8));

        LinearLayout head = new LinearLayout(this);
        head.setGravity(Gravity.CENTER_VERTICAL);

        TextView titleView = new TextView(this);
        titleView.setText(title);
        titleView.setTextColor(Color.rgb(15, 23, 42));
        titleView.setTextSize(14);
        titleView.setTypeface(Typeface.DEFAULT_BOLD);
        head.addView(titleView, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1));
        head.addView(status);
        row.addView(head);

        TextView purposeView = new TextView(this);
        purposeView.setText(purpose);
        purposeView.setTextColor(Color.rgb(71, 85, 105));
        purposeView.setTextSize(12);
        purposeView.setPadding(0, dp(3), 0, dp(6));
        row.addView(purposeView);

        LinearLayout actions = new LinearLayout(this);
        actions.setOrientation(LinearLayout.HORIZONTAL);
        Button grantButton = secondaryButton("获取");
        grantButton.setOnClickListener(grant);
        Button cancelButton = secondaryButton("取消/管理");
        cancelButton.setOnClickListener(cancel);
        LinearLayout.LayoutParams grantParams = new LinearLayout.LayoutParams(0, dp(42), 1);
        grantParams.rightMargin = dp(8);
        actions.addView(grantButton, grantParams);
        actions.addView(cancelButton, new LinearLayout.LayoutParams(0, dp(42), 1));
        row.addView(actions);
        return row;
    }

    private TextView sectionTitle(String text) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextColor(Color.rgb(15, 23, 42));
        view.setTextSize(16);
        view.setTypeface(Typeface.DEFAULT_BOLD);
        view.setPadding(0, 0, 0, dp(8));
        return view;
    }

    private View field(String label, View input) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.VERTICAL);
        row.setPadding(0, dp(4), 0, dp(8));

        TextView labelView = new TextView(this);
        labelView.setText(label);
        labelView.setTextColor(Color.rgb(71, 85, 105));
        labelView.setTextSize(13);
        row.addView(labelView);

        LinearLayout.LayoutParams inputParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(44)
        );
        inputParams.topMargin = dp(4);
        row.addView(input, inputParams);
        return row;
    }

    private View sliderField(String label, TextView value, SeekBar seekBar) {
        LinearLayout column = new LinearLayout(this);
        column.setOrientation(LinearLayout.VERTICAL);
        column.setPadding(0, dp(4), 0, dp(8));

        LinearLayout head = new LinearLayout(this);
        head.setGravity(Gravity.CENTER_VERTICAL);
        TextView labelView = new TextView(this);
        labelView.setText(label);
        labelView.setTextColor(Color.rgb(71, 85, 105));
        labelView.setTextSize(13);
        head.addView(labelView, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1));
        head.addView(value);

        column.addView(head);
        column.addView(seekBar);
        return column;
    }

    private EditText input(String hint) {
        EditText editText = new EditText(this);
        editText.setSingleLine(true);
        editText.setTextSize(15);
        editText.setHint(hint);
        editText.setPadding(dp(12), 0, dp(12), 0);
        editText.setBackground(roundRect(Color.rgb(248, 250, 252), dp(8), Color.rgb(203, 213, 225)));
        return editText;
    }

    private Spinner spinner(LanguageOption[] options) {
        Spinner spinner = new Spinner(this);
        ArrayAdapter<LanguageOption> adapter = new ArrayAdapter<>(
                this,
                android.R.layout.simple_spinner_item,
                options
        );
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        spinner.setAdapter(adapter);
        spinner.setBackground(roundRect(Color.rgb(248, 250, 252), dp(8), Color.rgb(203, 213, 225)));
        spinner.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override
            public void onItemSelected(AdapterView<?> parent, View view, int position, long id) {
            }

            @Override
            public void onNothingSelected(AdapterView<?> parent) {
            }
        });
        return spinner;
    }

    private Spinner audioSourceSpinner(AudioSourceOption[] options) {
        Spinner spinner = new Spinner(this);
        ArrayAdapter<AudioSourceOption> adapter = new ArrayAdapter<>(
                this,
                android.R.layout.simple_spinner_item,
                options
        );
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        spinner.setAdapter(adapter);
        spinner.setBackground(roundRect(Color.rgb(248, 250, 252), dp(8), Color.rgb(203, 213, 225)));
        spinner.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override
            public void onItemSelected(AdapterView<?> parent, View view, int position, long id) {
                refreshPermissionStatus();
            }

            @Override
            public void onNothingSelected(AdapterView<?> parent) {
            }
        });
        return spinner;
    }

    private Spinner modelSpinner(String placeholder) {
        Spinner spinner = new Spinner(this);
        ArrayAdapter<ModelOption> adapter = new ArrayAdapter<>(
                this,
                android.R.layout.simple_spinner_item,
                new ModelOption[] {ModelOption.loading(placeholder)}
        );
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        spinner.setAdapter(adapter);
        spinner.setBackground(roundRect(Color.rgb(248, 250, 252), dp(8), Color.rgb(203, 213, 225)));
        return spinner;
    }

    private void applyModelOptions(Spinner spinner, List<ModelOption> models, String preferredKey, String emptyLabel) {
        ArrayAdapter<ModelOption> adapter = new ArrayAdapter<>(
                this,
                android.R.layout.simple_spinner_item,
                models.isEmpty() ? java.util.Collections.singletonList(ModelOption.loading(emptyLabel)) : models
        );
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        spinner.setAdapter(adapter);

        if (models.isEmpty()) {
            return;
        }
        int selectedIndex = 0;
        for (int i = 0; i < models.size(); i++) {
            if (models.get(i).key.equals(preferredKey)) {
                selectedIndex = i;
                break;
            }
        }
        spinner.setSelection(selectedIndex);
    }

    private String selectedModelKey(Spinner spinner, String fallback, boolean requireReadySelection) {
        Object selected = spinner.getSelectedItem();
        if (selected instanceof ModelOption) {
            ModelOption option = (ModelOption) selected;
            if (option.canUse()) {
                return option.key;
            }
        }
        return requireReadySelection ? "" : (fallback == null ? "" : fallback);
    }

    private Spinner colorSpinner(CaptionColorOption[] options) {
        Spinner spinner = new Spinner(this);
        ArrayAdapter<CaptionColorOption> adapter = new ArrayAdapter<>(
                this,
                android.R.layout.simple_spinner_item,
                options
        );
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        spinner.setAdapter(adapter);
        spinner.setBackground(roundRect(Color.rgb(248, 250, 252), dp(8), Color.rgb(203, 213, 225)));
        spinner.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override
            public void onItemSelected(AdapterView<?> parent, View view, int position, long id) {
                updatePreview();
            }

            @Override
            public void onNothingSelected(AdapterView<?> parent) {
            }
        });
        return spinner;
    }

    private View previewField() {
        LinearLayout column = new LinearLayout(this);
        column.setOrientation(LinearLayout.VERTICAL);
        column.setPadding(0, dp(4), 0, dp(8));

        LinearLayout head = new LinearLayout(this);
        head.setGravity(Gravity.CENTER_VERTICAL);
        TextView labelView = new TextView(this);
        labelView.setText("字幕显示区域");
        labelView.setTextColor(Color.rgb(71, 85, 105));
        labelView.setTextSize(13);
        head.addView(labelView, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1));
        head.addView(positionLabel);
        column.addView(head);

        previewFrame = new FrameLayout(this);
        previewFrame.setFocusable(true);
        previewFrame.setFocusableInTouchMode(true);
        previewFrame.setClickable(true);
        previewFrame.setPadding(dp(8), dp(8), dp(8), dp(8));
        previewFrame.setBackground(previewBackground(false));
        previewFrame.setOnFocusChangeListener((view, hasFocus) -> previewFrame.setBackground(previewBackground(hasFocus)));
        previewFrame.setOnClickListener(view -> previewFrame.requestFocus());
        previewFrame.setOnTouchListener((view, event) -> {
            if (event.getAction() == MotionEvent.ACTION_DOWN || event.getAction() == MotionEvent.ACTION_MOVE) {
                previewFrame.requestFocus();
                movePreviewToTouch(event.getX(), event.getY());
                return true;
            }
            return true;
        });
        previewFrame.setOnKeyListener((view, keyCode, event) -> {
            if (event.getAction() != KeyEvent.ACTION_DOWN) {
                return false;
            }
            int step = event.isLongPress() ? 10 : 4;
            if (keyCode == KeyEvent.KEYCODE_DPAD_LEFT) {
                movePreview(-step, 0);
                return true;
            }
            if (keyCode == KeyEvent.KEYCODE_DPAD_RIGHT) {
                movePreview(step, 0);
                return true;
            }
            if (keyCode == KeyEvent.KEYCODE_DPAD_UP) {
                movePreview(0, -step);
                return true;
            }
            if (keyCode == KeyEvent.KEYCODE_DPAD_DOWN) {
                movePreview(0, step);
                return true;
            }
            return false;
        });

        previewCaption = new TextView(this);
        previewCaption.setText("示例字幕第一行\n第二行会跟随你的设置\n第三行最多显示到这里");
        previewCaption.setTextColor(Color.WHITE);
        previewCaption.setGravity(Gravity.CENTER);
        previewCaption.setMaxLines(3);
        previewCaption.setTypeface(Typeface.DEFAULT_BOLD);
        previewCaption.setPadding(dp(12), dp(8), dp(12), dp(8));
        previewFrame.addView(previewCaption, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.WRAP_CONTENT
        ));

        LinearLayout.LayoutParams previewParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(220)
        );
        previewParams.topMargin = dp(6);
        column.addView(previewFrame, previewParams);
        return column;
    }

    private void movePreviewToTouch(float touchX, float touchY) {
        if (previewFrame == null || previewCaption == null) {
            return;
        }
        int frameWidth = previewFrame.getWidth() - previewFrame.getPaddingLeft() - previewFrame.getPaddingRight();
        int frameHeight = previewFrame.getHeight() - previewFrame.getPaddingTop() - previewFrame.getPaddingBottom();
        int captionWidth = previewCaption.getWidth();
        int captionHeight = previewCaption.getHeight();
        if (frameWidth <= 0 || frameHeight <= 0 || captionWidth <= 0 || captionHeight <= 0) {
            return;
        }

        int maxX = Math.max(0, frameWidth - captionWidth);
        int maxY = Math.max(0, frameHeight - captionHeight);
        float desiredX = touchX - previewFrame.getPaddingLeft() - captionWidth / 2f;
        float desiredY = touchY - previewFrame.getPaddingTop() - captionHeight / 2f;
        previewXPercent = maxX == 0 ? 50 : Math.round(clampFloat(desiredX, 0, maxX) * 100f / maxX);
        previewYPercent = maxY == 0 ? 50 : Math.round(clampFloat(desiredY, 0, maxY) * 100f / maxY);
        updateSeekLabels();
    }

    private void movePreview(int deltaX, int deltaY) {
        previewXPercent = clamp(previewXPercent + deltaX, 0, 100);
        previewYPercent = clamp(previewYPercent + deltaY, 0, 100);
        updateSeekLabels();
    }

    private void updatePreview() {
        if (previewCaption == null || previewFrame == null || colorSpinner == null) {
            return;
        }
        CaptionColorOption color = (CaptionColorOption) colorSpinner.getSelectedItem();
        int fontSize = fontSeek == null ? 22 : fontSeek.getProgress() + 16;
        int opacity = opacitySeek == null ? 82 : opacitySeek.getProgress() + 45;
        previewCaption.setTextSize(fontSize);
        previewCaption.setBackground(captionBackground(color.color, opacity));
        previewFrame.post(() -> {
            int frameWidth = previewFrame.getWidth() - previewFrame.getPaddingLeft() - previewFrame.getPaddingRight();
            int frameHeight = previewFrame.getHeight() - previewFrame.getPaddingTop() - previewFrame.getPaddingBottom();
            if (frameWidth <= 0 || frameHeight <= 0) {
                return;
            }
            previewCaption.setMaxWidth(Math.max(dp(180), frameWidth - dp(24)));
            previewCaption.measure(
                    View.MeasureSpec.makeMeasureSpec(frameWidth, View.MeasureSpec.AT_MOST),
                    View.MeasureSpec.makeMeasureSpec(frameHeight, View.MeasureSpec.AT_MOST)
            );
            int maxX = Math.max(0, frameWidth - previewCaption.getMeasuredWidth());
            int maxY = Math.max(0, frameHeight - previewCaption.getMeasuredHeight());
            previewCaption.setX(previewFrame.getPaddingLeft() + maxX * previewXPercent / 100f);
            previewCaption.setY(previewFrame.getPaddingTop() + maxY * previewYPercent / 100f);
        });
    }

    private SeekBar seek(int min, int max) {
        SeekBar seekBar = new SeekBar(this);
        seekBar.setMax(max - min);
        return seekBar;
    }

    private TextView valueLabel(String text) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextColor(Color.rgb(15, 23, 42));
        view.setTextSize(13);
        view.setTypeface(Typeface.DEFAULT_BOLD);
        return view;
    }

    private Button primaryButton(String text) {
        Button button = new Button(this);
        button.setText(text);
        button.setTextColor(Color.WHITE);
        button.setTextSize(15);
        button.setAllCaps(false);
        button.setBackground(roundRect(Color.rgb(37, 99, 235), dp(8), Color.rgb(37, 99, 235)));
        return button;
    }

    private Button secondaryButton(String text) {
        Button button = new Button(this);
        button.setText(text);
        button.setTextColor(Color.rgb(15, 23, 42));
        button.setTextSize(15);
        button.setAllCaps(false);
        button.setBackground(roundRect(Color.WHITE, dp(8), Color.rgb(203, 213, 225)));
        return button;
    }

    private LinearLayout.LayoutParams fullWidthButtonParams() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(48)
        );
        params.topMargin = dp(8);
        return params;
    }

    private GradientDrawable roundRect(int fill, int radius, int stroke) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(fill);
        drawable.setCornerRadius(radius);
        drawable.setStroke(dp(1), stroke);
        return drawable;
    }

    private GradientDrawable previewBackground(boolean focused) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(Color.rgb(15, 23, 42));
        drawable.setCornerRadius(dp(8));
        drawable.setStroke(dp(focused ? 3 : 1), focused ? Color.rgb(37, 99, 235) : Color.rgb(71, 85, 105));
        return drawable;
    }

    private GradientDrawable captionBackground(int color, int opacityPercent) {
        int alpha = Math.max(20, Math.min(100, opacityPercent)) * 255 / 100;
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(Color.argb(alpha, Color.red(color), Color.green(color), Color.blue(color)));
        drawable.setCornerRadius(dp(8));
        drawable.setStroke(dp(1), Color.argb(110, 226, 232, 240));
        return drawable;
    }

    private static int clamp(int value, int min, int max) {
        return Math.max(min, Math.min(max, value));
    }

    private static float clampFloat(float value, float min, float max) {
        return Math.max(min, Math.min(max, value));
    }

    private void toast(String message) {
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show();
    }

    private static String cleanError(String message) {
        if (message == null || message.trim().isEmpty()) {
            return "未知错误";
        }
        String compact = message.replace('\n', ' ').replace('\r', ' ').trim();
        return compact.length() > 120 ? compact.substring(0, 120) + "..." : compact;
    }

    private int dp(int value) {
        return (int) (value * getResources().getDisplayMetrics().density + 0.5f);
    }
}
