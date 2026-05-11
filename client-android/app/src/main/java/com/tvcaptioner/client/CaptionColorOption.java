package com.tvcaptioner.client;

final class CaptionColorOption {
    final String label;
    final int color;

    CaptionColorOption(String label, int color) {
        this.label = label;
        this.color = color;
    }

    @Override
    public String toString() {
        return label;
    }

    static CaptionColorOption[] options() {
        return new CaptionColorOption[] {
                new CaptionColorOption("深灰", 0xFF0F172A),
                new CaptionColorOption("纯黑", 0xFF000000),
                new CaptionColorOption("靛蓝", 0xFF1E3A8A),
                new CaptionColorOption("墨绿", 0xFF14532D),
                new CaptionColorOption("酒红", 0xFF7F1D1D),
                new CaptionColorOption("琥珀", 0xFF78350F)
        };
    }

    static int indexOf(CaptionColorOption[] options, int color) {
        for (int i = 0; i < options.length; i++) {
            if (options[i].color == color) {
                return i;
            }
        }
        return 0;
    }
}
