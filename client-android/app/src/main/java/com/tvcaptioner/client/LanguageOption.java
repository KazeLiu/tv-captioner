package com.tvcaptioner.client;

final class LanguageOption {
    final String label;
    final String value;

    LanguageOption(String label, String value) {
        this.label = label;
        this.value = value;
    }

    @Override
    public String toString() {
        return label;
    }

    static LanguageOption[] sourceOptions() {
        return new LanguageOption[] {
                new LanguageOption("自动检测", "auto"),
                new LanguageOption("英语", "en"),
                new LanguageOption("日语", "ja"),
                new LanguageOption("韩语", "ko"),
                new LanguageOption("简体中文", "zh"),
                new LanguageOption("繁体中文", "zh"),
                new LanguageOption("法语", "fr"),
                new LanguageOption("德语", "de"),
                new LanguageOption("西班牙语", "es"),
                new LanguageOption("俄语", "ru")
        };
    }

    static LanguageOption[] targetOptions() {
        return new LanguageOption[] {
                new LanguageOption("简体中文", "Chinese"),
                new LanguageOption("繁体中文", "Traditional Chinese"),
                new LanguageOption("英语", "English"),
                new LanguageOption("日语", "Japanese"),
                new LanguageOption("韩语", "Korean"),
                new LanguageOption("法语", "French"),
                new LanguageOption("德语", "German"),
                new LanguageOption("西班牙语", "Spanish"),
                new LanguageOption("俄语", "Russian")
        };
    }

    static int indexOf(LanguageOption[] options, String value) {
        for (int i = 0; i < options.length; i++) {
            if (options[i].value.equals(value)) {
                return i;
            }
        }
        return 0;
    }
}
