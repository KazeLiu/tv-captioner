package com.tvcaptioner.client;

import android.Manifest;
import android.content.Context;
import android.content.pm.PackageManager;
import android.media.AudioAttributes;
import android.media.AudioFormat;
import android.media.AudioPlaybackCaptureConfiguration;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.media.projection.MediaProjection;
import android.os.Build;
import android.os.Process;

import java.io.ByteArrayOutputStream;

final class AudioCaptureLoop {
    interface Listener {
        void onListening();

        void onProcessing();

        void onCaption(CaptionResult result);

        void onError(String message);
    }

    private static final int SAMPLE_RATE = 16000;
    private static final int CHANNELS = 1;

    private final Context context;
    private final Listener listener;
    private final MediaProjection mediaProjection;
    private volatile boolean running;
    private Thread thread;
    private AudioRecord recorder;

    AudioCaptureLoop(Context context, Listener listener, MediaProjection mediaProjection) {
        this.context = context.getApplicationContext();
        this.listener = listener;
        this.mediaProjection = mediaProjection;
    }

    void start() {
        if (running) {
            return;
        }
        running = true;
        thread = new Thread(this::runLoop, "CaptionAudioCapture");
        thread.start();
    }

    void stop() {
        running = false;
        AudioRecord current = recorder;
        if (current != null) {
            try {
                current.stop();
            } catch (IllegalStateException ignored) {
            }
            current.release();
            recorder = null;
        }
    }

    private void runLoop() {
        Process.setThreadPriority(Process.THREAD_PRIORITY_AUDIO);
        AppSettings settings = AppSettings.load(context);
        int minBuffer = AudioRecord.getMinBufferSize(
                SAMPLE_RATE,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT
        );
        if (minBuffer <= 0) {
            listener.onError("录音设备不可用");
            return;
        }
        int chunkBytes = settings.chunkSeconds * SAMPLE_RATE * CHANNELS * 2;
        int bufferSize = Math.max(minBuffer * 2, chunkBytes / 2);

        try {
            if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                listener.onError("还没有音频录制权限");
                return;
            }
            recorder = createRecorder(settings, bufferSize);
            if (recorder.getState() != AudioRecord.STATE_INITIALIZED) {
                listener.onError("录音初始化失败");
                return;
            }

            BackendClient client = new BackendClient(settings);
            recorder.startRecording();
            byte[] buffer = new byte[Math.max(4096, minBuffer)];
            while (running) {
                listener.onListening();
                ByteArrayOutputStream pcm = new ByteArrayOutputStream(chunkBytes);
                while (running && pcm.size() < chunkBytes) {
                    int read = recorder.read(buffer, 0, Math.min(buffer.length, chunkBytes - pcm.size()));
                    if (read > 0) {
                        pcm.write(buffer, 0, read);
                    }
                }
                if (!running || pcm.size() == 0) {
                    break;
                }

                listener.onProcessing();
                try {
                    byte[] wav = WavEncoder.pcm16ToWav(pcm.toByteArray(), SAMPLE_RATE, CHANNELS);
                    CaptionResult result = client.translate(wav);
                    listener.onCaption(result);
                } catch (Exception exc) {
                    listener.onError(cleanError(exc.getMessage()));
                    sleepQuietly(1200);
                }
            }
        } catch (SecurityException exc) {
            listener.onError("音频录制权限被系统拒绝");
        } catch (IllegalStateException exc) {
            if (exc.getMessage() != null && !exc.getMessage().trim().isEmpty()) {
                listener.onError(cleanError(exc.getMessage()));
            }
        } finally {
            stop();
        }
    }

    private AudioRecord createRecorder(AppSettings settings, int bufferSize) {
        if (!settings.useSystemAudio()) {
            return new AudioRecord(
                    MediaRecorder.AudioSource.VOICE_RECOGNITION,
                    SAMPLE_RATE,
                    AudioFormat.CHANNEL_IN_MONO,
                    AudioFormat.ENCODING_PCM_16BIT,
                    bufferSize
            );
        }
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
            listener.onError("系统声音采集需要 Android 10 或更高版本");
            throw new IllegalStateException("系统声音采集需要 Android 10 或更高版本");
        }
        if (mediaProjection == null) {
            listener.onError("还没有系统声音采集授权");
            throw new IllegalStateException("还没有系统声音采集授权");
        }

        AudioFormat format = new AudioFormat.Builder()
                .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                .setSampleRate(SAMPLE_RATE)
                .setChannelMask(AudioFormat.CHANNEL_IN_MONO)
                .build();
        AudioPlaybackCaptureConfiguration config = new AudioPlaybackCaptureConfiguration.Builder(mediaProjection)
                .addMatchingUsage(AudioAttributes.USAGE_MEDIA)
                .addMatchingUsage(AudioAttributes.USAGE_GAME)
                .build();
        return new AudioRecord.Builder()
                .setAudioFormat(format)
                .setBufferSizeInBytes(bufferSize)
                .setAudioPlaybackCaptureConfig(config)
                .build();
    }

    private static String cleanError(String message) {
        if (message == null || message.trim().isEmpty()) {
            return "连接后端失败";
        }
        String compact = message.replace('\n', ' ').replace('\r', ' ').trim();
        return compact.length() > 80 ? compact.substring(0, 80) + "..." : compact;
    }

    private static void sleepQuietly(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException ignored) {
            Thread.currentThread().interrupt();
        }
    }
}
