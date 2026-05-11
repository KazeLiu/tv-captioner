package com.tvcaptioner.client;

import java.io.ByteArrayOutputStream;
import java.io.IOException;

final class WavEncoder {
    private WavEncoder() {
    }

    static byte[] pcm16ToWav(byte[] pcm, int sampleRate, int channels) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream(44 + pcm.length);
        int byteRate = sampleRate * channels * 2;
        int dataSize = pcm.length;
        int riffSize = dataSize + 36;

        writeAscii(output, "RIFF");
        writeInt(output, riffSize);
        writeAscii(output, "WAVE");
        writeAscii(output, "fmt ");
        writeInt(output, 16);
        writeShort(output, 1);
        writeShort(output, channels);
        writeInt(output, sampleRate);
        writeInt(output, byteRate);
        writeShort(output, channels * 2);
        writeShort(output, 16);
        writeAscii(output, "data");
        writeInt(output, dataSize);
        output.write(pcm);
        return output.toByteArray();
    }

    private static void writeAscii(ByteArrayOutputStream output, String value) {
        for (int i = 0; i < value.length(); i++) {
            output.write(value.charAt(i));
        }
    }

    private static void writeInt(ByteArrayOutputStream output, int value) {
        output.write(value & 0xff);
        output.write((value >> 8) & 0xff);
        output.write((value >> 16) & 0xff);
        output.write((value >> 24) & 0xff);
    }

    private static void writeShort(ByteArrayOutputStream output, int value) {
        output.write(value & 0xff);
        output.write((value >> 8) & 0xff);
    }
}
