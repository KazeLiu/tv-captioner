package com.tvcaptioner.client;

final class AudioSourceOption {
    final String value;
    final String label;

    AudioSourceOption(String value, String label) {
        this.value = value;
        this.label = label;
    }

    @Override
    public String toString() {
        return label;
    }

    static AudioSourceOption[] options() {
        return new AudioSourceOption[] {
                new AudioSourceOption(AppSettings.AUDIO_SOURCE_MICROPHONE, "麦克风"),
                new AudioSourceOption(AppSettings.AUDIO_SOURCE_SYSTEM, "系统播放声音")
        };
    }

    static int indexOf(AudioSourceOption[] options, String value) {
        for (int i = 0; i < options.length; i++) {
            if (options[i].value.equals(value)) {
                return i;
            }
        }
        return 0;
    }
}
