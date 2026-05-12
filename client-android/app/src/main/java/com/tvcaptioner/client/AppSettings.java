package com.tvcaptioner.client;

import android.content.Context;
import android.content.SharedPreferences;

final class AppSettings {
    static final String PREFS = "tv_captioner_settings";
    static final String AUDIO_SOURCE_MICROPHONE = "microphone";
    static final String AUDIO_SOURCE_SYSTEM = "system";

    private static final String KEY_HOST = "host";
    private static final String KEY_PORT = "port";
    private static final String KEY_AUDIO_SOURCE = "audio_source";
    private static final String KEY_SOURCE_LANGUAGE = "source_language";
    private static final String KEY_TARGET_LANGUAGE = "target_language";
    private static final String KEY_ASR_MODEL = "asr_model";
    private static final String KEY_TRANSLATION_MODEL = "translation_model";
    private static final String KEY_CHUNK_SECONDS = "chunk_seconds";
    private static final String KEY_FONT_SIZE = "font_size";
    private static final String KEY_OPACITY = "opacity";
    private static final String KEY_BACKGROUND_COLOR = "background_color";
    private static final String KEY_POSITION_X = "position_x";
    private static final String KEY_POSITION_Y = "position_y";

    final String host;
    final int port;
    final String audioSource;
    final String sourceLanguage;
    final String targetLanguage;
    final String asrModel;
    final String translationModel;
    final int chunkSeconds;
    final int fontSizeSp;
    final int opacityPercent;
    final int backgroundColor;
    final int positionXPercent;
    final int positionYPercent;

    AppSettings(
            String host,
            int port,
            String audioSource,
            String sourceLanguage,
            String targetLanguage,
            String asrModel,
            String translationModel,
            int chunkSeconds,
            int fontSizeSp,
            int opacityPercent,
            int backgroundColor,
            int positionXPercent,
            int positionYPercent
    ) {
        this.host = host;
        this.port = port;
        this.audioSource = audioSource;
        this.sourceLanguage = sourceLanguage;
        this.targetLanguage = targetLanguage;
        this.asrModel = asrModel;
        this.translationModel = translationModel;
        this.chunkSeconds = chunkSeconds;
        this.fontSizeSp = fontSizeSp;
        this.opacityPercent = opacityPercent;
        this.backgroundColor = backgroundColor;
        this.positionXPercent = positionXPercent;
        this.positionYPercent = positionYPercent;
    }

    String baseUrl() {
        return "http://" + host + ":" + port;
    }

    static AppSettings load(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        return new AppSettings(
                prefs.getString(KEY_HOST, "192.168.1.100"),
                prefs.getInt(KEY_PORT, 8765),
                prefs.getString(KEY_AUDIO_SOURCE, AUDIO_SOURCE_MICROPHONE),
                prefs.getString(KEY_SOURCE_LANGUAGE, "auto"),
                prefs.getString(KEY_TARGET_LANGUAGE, "Chinese"),
                prefs.getString(KEY_ASR_MODEL, "large-v2"),
                prefs.getString(KEY_TRANSLATION_MODEL, "qwen2.5-1.5b-instruct-gguf"),
                prefs.getInt(KEY_CHUNK_SECONDS, 4),
                prefs.getInt(KEY_FONT_SIZE, 22),
                prefs.getInt(KEY_OPACITY, 82),
                prefs.getInt(KEY_BACKGROUND_COLOR, 0xFF0F172A),
                prefs.getInt(KEY_POSITION_X, 50),
                prefs.getInt(KEY_POSITION_Y, 82)
        );
    }

    void save(Context context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .edit()
                .putString(KEY_HOST, host.trim())
                .putInt(KEY_PORT, port)
                .putString(KEY_AUDIO_SOURCE, audioSource)
                .putString(KEY_SOURCE_LANGUAGE, sourceLanguage)
                .putString(KEY_TARGET_LANGUAGE, targetLanguage)
                .putString(KEY_ASR_MODEL, asrModel)
                .putString(KEY_TRANSLATION_MODEL, translationModel)
                .putInt(KEY_CHUNK_SECONDS, chunkSeconds)
                .putInt(KEY_FONT_SIZE, fontSizeSp)
                .putInt(KEY_OPACITY, opacityPercent)
                .putInt(KEY_BACKGROUND_COLOR, backgroundColor)
                .putInt(KEY_POSITION_X, clamp(positionXPercent, 0, 100))
                .putInt(KEY_POSITION_Y, clamp(positionYPercent, 0, 100))
                .apply();
    }

    boolean useSystemAudio() {
        return AUDIO_SOURCE_SYSTEM.equals(audioSource);
    }

    private static int clamp(int value, int min, int max) {
        return Math.max(min, Math.min(max, value));
    }
}
