package com.sankatmochan.mesh.chat

/**
 * The offline assistant's model catalogue.
 *
 * Every hub entry is a small **GGUF** chat model that GenieX runs through its llama.cpp
 * runtime, which schedules tensors across the Snapdragon NPU, GPU, or CPU. GGUF models are
 * pulled at runtime and are chipset-agnostic, so the same build works on any device.
 *
 * Licensing (CLAUDE.md #1): Granite and Phi-4-mini are Apache-2.0 / MIT. **Gemma ships under
 * Google's Gemma Terms of Use - NOT an OSI-approved licence** - and its weights are gated on
 * Hugging Face, so a token is required to download them (see [gated]). It is included here at
 * the user's explicit request; a human should confirm the Gemma Terms are acceptable for this
 * project before shipping.
 *
 * A [localPath] set (non-null) marks a model the user side-loaded from device storage - those
 * skip the hub entirely and load straight off disk (plug-and-play). See [GenieXEngine].
 */
data class AssistantModel(
    /** Stable key used for selection and the "which model is loaded" check. */
    val id: String,
    /** Human-readable label shown in the picker. */
    val displayName: String,
    /** `org/repo` on the hub, or the file name for a local model. */
    val modelName: String,
    /** Quantization the manager should pull (empty for local files). */
    val quant: String,
    /** Rough on-disk size, shown so the user knows what they're committing to. */
    val approxSize: String,
    /** One-line "why pick this one". */
    val blurb: String,
    /** True when the hub weights are gated and need the Hugging Face token to download. */
    val gated: Boolean = false,
    /** Absolute path when this model was side-loaded from device storage; null for hub models. */
    val localPath: String? = null,
) {
    val isLocal: Boolean get() = localPath != null
}

object AssistantModels {

    /** Hub models. Gemma first (the requested default); permissive, non-gated fallbacks after. */
    val catalog: List<AssistantModel> = listOf(
        AssistantModel(
            id = "gemma-4-E2B",
            displayName = "Gemma 4 E2B",
            // Google's QAT Q4_0 GGUF release of Gemma 4 E2B (gated on Hugging Face).
            modelName = "google/gemma-4-E2B-it-qat-q4_0-gguf",
            quant = "Q4_0",
            approxSize = "~1.5 GB",
            blurb = "Recommended - Google Gemma 4 E2B. One-time Hugging Face sign-in (token built in).",
            gated = true,
        ),
        AssistantModel(
            id = "gemma-4-E4B",
            displayName = "Gemma 4 E4B",
            modelName = "google/gemma-4-E4B-it-qat-q4_0-gguf",
            quant = "Q4_0",
            approxSize = "~2.8 GB",
            blurb = "Larger Gemma 4 E4B - better answers, bigger download.",
            gated = true,
        ),
        AssistantModel(
            id = "granite-4.0-micro-GGUF",
            displayName = "Granite 4.0 Micro",
            modelName = "ibm-granite/granite-4.0-micro-GGUF",
            quant = "Q4_0",
            approxSize = "~2.0 GB",
            blurb = "IBM Granite (Apache-2.0). No sign-in needed - a safe fallback.",
        ),
        AssistantModel(
            id = "Phi-4-mini-instruct-GGUF",
            displayName = "Phi-4 mini",
            modelName = "bartowski/microsoft_Phi-4-mini-instruct-GGUF",
            quant = "Q4_0",
            approxSize = "~2.3 GB",
            blurb = "Microsoft Phi-4 mini (MIT). No sign-in needed.",
        ),
    )

    val default: AssistantModel get() = catalog.first()

    fun byId(id: String): AssistantModel? = catalog.firstOrNull { it.id == id }
}
