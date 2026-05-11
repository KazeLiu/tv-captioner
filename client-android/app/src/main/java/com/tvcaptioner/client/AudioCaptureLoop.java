package com.tvcaptioner.client;

import android.Manifest;
import android.content.Context;
import android.content.pm.PackageManager;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
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
    private volatile boolean running;
    private Thread thread;
    private AudioRecord recorder;

    AudioCaptureLoop(Context context, Listener listener) {
        this.context = context.getApplicationContext();
        this.listener = listener;
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
                listener.onError("还没有麦克风权限");
                return;
            }
            recorder = new AudioRecord(
                    MediaRecorder.AudioSource.VOICE_RECOGNITION,
                    SAMPLE_RATE,
                    AudioFormat.CHANNEL_IN_MONO,
                    AudioFormat.ENCODING_PCM_16BIT,
                    bufferSize
            );
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
            listener.onError("麦克风权限被系统拒绝");
        } finally {
            stop();
        }
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
