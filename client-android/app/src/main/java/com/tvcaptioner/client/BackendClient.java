package com.tvcaptioner.client;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

final class BackendClient {
    private static final String BOUNDARY = "----TVCaptionerAndroidBoundary";

    private final AppSettings settings;

    BackendClient(AppSettings settings) {
        this.settings = settings;
    }

    BackendModels fetchModels() throws Exception {
        URL url = new URL(settings.baseUrl() + "/api/status?asr_model=" + encode(settings.asrModel));
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        connection.setConnectTimeout(5000);
        connection.setReadTimeout(12000);
        connection.setRequestMethod("GET");
        try {
            int code = connection.getResponseCode();
            String body = readBody(code >= 400 ? connection.getErrorStream() : connection.getInputStream());
            if (code < 200 || code >= 300) {
                throw new IOException("HTTP " + code + ": " + body);
            }
            JSONObject json = new JSONObject(body);
            List<ModelOption> asrModels = new ArrayList<>();
            appendReadyModels(asrModels, json.optJSONArray("asrModels"));
            appendReadyModels(asrModels, json.optJSONArray("customAsrModels"));

            List<ModelOption> translationModels = new ArrayList<>();
            appendReadyModels(translationModels, json.optJSONArray("translationModels"));
            appendReadyModels(translationModels, json.optJSONArray("customTranslationModels"));
            return new BackendModels(asrModels, translationModels);
        } finally {
            connection.disconnect();
        }
    }

    CaptionResult translate(byte[] wavBytes) throws Exception {
        URL url = new URL(settings.baseUrl() + "/api/audio/translate");
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        connection.setConnectTimeout(5000);
        connection.setReadTimeout(180000);
        connection.setRequestMethod("POST");
        connection.setDoOutput(true);
        connection.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + BOUNDARY);

        try (OutputStream output = connection.getOutputStream()) {
            writeField(output, "source_language", settings.sourceLanguage);
            writeField(output, "target_language", settings.targetLanguage);
            writeField(output, "asr_model", settings.asrModel);
            writeField(output, "translation_model", settings.translationModel);
            writeFile(output, "file", "caption.wav", "audio/wav", wavBytes);
            write(output, "--" + BOUNDARY + "--\r\n");
        }

        int code = connection.getResponseCode();
        String body = readBody(code >= 400 ? connection.getErrorStream() : connection.getInputStream());
        connection.disconnect();
        if (code < 200 || code >= 300) {
            throw new IOException("HTTP " + code + ": " + body);
        }

        JSONObject json = new JSONObject(body);
        return new CaptionResult(
                json.optString("sourceText", ""),
                json.optString("translatedText", ""),
                json.optString("sourceLanguage", "")
        );
    }

    private static void writeField(OutputStream output, String name, String value) throws IOException {
        write(output, "--" + BOUNDARY + "\r\n");
        write(output, "Content-Disposition: form-data; name=\"" + name + "\"\r\n\r\n");
        write(output, value == null ? "" : value);
        write(output, "\r\n");
    }

    private static void writeFile(OutputStream output, String name, String filename, String contentType, byte[] bytes)
            throws IOException {
        write(output, "--" + BOUNDARY + "\r\n");
        write(output, "Content-Disposition: form-data; name=\"" + name + "\"; filename=\"" + filename + "\"\r\n");
        write(output, "Content-Type: " + contentType + "\r\n\r\n");
        output.write(bytes);
        write(output, "\r\n");
    }

    private static void write(OutputStream output, String value) throws IOException {
        output.write(value.getBytes(StandardCharsets.UTF_8));
    }

    private static void appendReadyModels(List<ModelOption> output, JSONArray items) {
        if (items == null) {
            return;
        }
        for (int i = 0; i < items.length(); i++) {
            JSONObject item = items.optJSONObject(i);
            if (item == null || !item.optBoolean("ready", false)) {
                continue;
            }
            String key = item.optString("key", "");
            if (key.trim().isEmpty()) {
                continue;
            }
            String label = item.optString("nameCn", item.optString("label", key));
            output.add(new ModelOption(key, label, true));
        }
    }

    private static String encode(String value) throws IOException {
        return URLEncoder.encode(value == null ? "" : value, "UTF-8");
    }

    private static String readBody(java.io.InputStream stream) throws IOException {
        if (stream == null) {
            return "";
        }
        try (BufferedInputStream input = new BufferedInputStream(stream);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[4096];
            int read;
            while ((read = input.read(buffer)) != -1) {
                output.write(buffer, 0, read);
            }
            return output.toString("UTF-8");
        }
    }
}
