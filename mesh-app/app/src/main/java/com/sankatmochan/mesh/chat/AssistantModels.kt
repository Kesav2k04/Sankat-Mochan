package com.sankatmochan.mesh.chat

/**
 * The offline assistant's model catalogue.
 *
 * Every entry is a small **GGUF** chat model that GenieX runs through its llama.cpp runtime,
 * which schedules tensors across the Snapdragon NPU, GPU, or CPU. GGUF models are pulled from
 * Hugging Face at runtime and are chipset-agnostic — unlike the QAIRT NPU bundles, which are
 * locked to one Snapdragon part — so the same build works on any device the app installs on.
 *
 * Licensing (CLAUDE.md #1): only permissively-licensed model weights are listed here —
 * Qwen3 and Granite are Apache-2.0, Phi-4-mini is MIT. No GPL/proprietary weights.
 *
 * The field names mirror what GenieX's `ModelPullInput` / model manager expect. See the
 * official reference app for the schema:
 * https://github.com/qualcomm/ai-hub-apps/blob/main/geniex_chat_android/src/main/assets/model_list.json
 */
data class AssistantModel(
    /** Stable key used for selection and the "which model is loaded" check. */
    val id: String,
    /** Human-readable label shown in the picker. */
    val displayName: String,
    /** `org/repo` on the hub, exactly as GenieX's model manager expects. */
    val modelName: String,
    /** Quantization the manager should pull. */
    val quant: String,
    /** Hub enum name understood by `com.geniex.sdk.bean.HubSource`. */
    val hub: String = "HUGGINGFACE",
    /** Rough on-disk download size, shown so the user knows what they're committing to. */
    val approxSize: String,
    /** One-line "why pick this one". */
    val blurb: String,
)

object AssistantModels {

    /**
     * Ordered lightest-capability-first so the recommended default (index 0) is a good
     * balance of quality and download size for a phone on a patchy connection.
     */
    val catalog: List<AssistantModel> = listOf(
        AssistantModel(
            id = "Qwen3-1.7B-GGUF",
            displayName = "Qwen3 1.7B",
            modelName = "unsloth/Qwen3-1.7B-GGUF",
            quant = "Q4_0",
            approxSize = "~1.1 GB",
            blurb = "Recommended — best balance of answers and speed on-device.",
        ),
        AssistantModel(
            id = "Qwen3-0.6B-GGUF",
            displayName = "Qwen3 0.6B",
            modelName = "unsloth/Qwen3-0.6B-GGUF",
            quant = "Q4_0",
            approxSize = "~0.4 GB",
            blurb = "Fastest to download and run. Good for a quick demo.",
        ),
        AssistantModel(
            id = "granite-4.0-micro-GGUF",
            displayName = "Granite 4.0 Micro",
            modelName = "ibm-granite/granite-4.0-micro-GGUF",
            quant = "Q4_0",
            approxSize = "~2.0 GB",
            blurb = "IBM Granite — steady, careful answers. Larger download.",
        ),
        AssistantModel(
            id = "Phi-4-mini-instruct-GGUF",
            displayName = "Phi-4 mini",
            modelName = "bartowski/microsoft_Phi-4-mini-instruct-GGUF",
            quant = "Q4_0",
            approxSize = "~2.3 GB",
            blurb = "Microsoft Phi-4 mini (MIT). Strong reasoning, largest download.",
        ),
    )

    val default: AssistantModel get() = catalog.first()

    fun byId(id: String): AssistantModel? = catalog.firstOrNull { it.id == id }
}
