package com.tvcaptioner.client;

final class CaptionResult {
    final String sourceText;
    final String translatedText;
    final String detectedLanguage;

    CaptionResult(String sourceText, String translatedText, String detectedLanguage) {
        this.sourceText = sourceText;
        this.translatedText = translatedText;
        this.detectedLanguage = detectedLanguage;
    }
}
