package com.tvcaptioner.client;

import java.util.List;

final class BackendModels {
    final List<ModelOption> asrModels;
    final List<ModelOption> translationModels;

    BackendModels(List<ModelOption> asrModels, List<ModelOption> translationModels) {
        this.asrModels = asrModels;
        this.translationModels = translationModels;
    }
}
