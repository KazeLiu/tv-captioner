package com.tvcaptioner.client;

final class ModelOption {
    final String key;
    final String label;
    final boolean ready;

    ModelOption(String key, String label, boolean ready) {
        this.key = key;
        this.label = label;
        this.ready = ready;
    }

    boolean canUse() {
        return ready && key != null && !key.trim().isEmpty();
    }

    @Override
    public String toString() {
        return label;
    }

    static ModelOption loading(String label) {
        return new ModelOption("", label, false);
    }
}
