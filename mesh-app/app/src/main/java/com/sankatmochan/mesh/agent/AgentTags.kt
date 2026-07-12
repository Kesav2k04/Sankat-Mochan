package com.sankatmochan.mesh.agent

/**
 * The compact structured-tag vocabulary the Sahayak agent sends up the mesh after a victim
 * conversation, riding the normal SOS envelope's gist field:
 *
 *   "TAGS c:3 inj:bleed trap:y hz:water mob:n unresp:y lm:old temple gate"
 *
 * Mirrors `parse_tags` / `TAG_ENUMS` in command-post/intelligence.py — keep the two in sync.
 * Every value is an enum or a small int; `lm` (landmark) is the only free text, always LAST
 * so it may contain spaces, and length-capped. All parsing treats input as untrusted data
 * (CLAUDE.md #8) — unknown keys and out-of-range values are dropped, never stored.
 */
object AgentTags {

    const val PREFIX = "TAGS "
    const val COUNT_MAX = 99
    const val LM_MAX = 48

    val INJ = setOf("none", "bleed", "fracture", "burn", "breath", "uncon", "other")
    val HZ = setOf("none", "water", "fire", "collapse", "gas", "electric")
    private val YN = setOf("y", "n")

    /** Key order on the wire. Criticality-first: SosMessage.encode() trims the gist from the
     *  END to fit the 244-byte frame, so the keys that must survive trimming come first —
     *  unresp (the escalation flag) before everything, free-text lm last (it also eats the
     *  remainder of the string, so it must be last for parsing anyway). */
    private val KEY_ORDER = listOf("unresp", "c", "inj", "trap", "hz", "mob", "lm")

    /** Validate one key/value pair against the shared vocabulary. */
    fun isValid(key: String, value: String): Boolean = when (key) {
        "c" -> value.toIntOrNull()?.let { it in 1..COUNT_MAX } == true
        "inj" -> value in INJ
        "hz" -> value in HZ
        "trap", "mob" -> value in YN
        "unresp" -> value == "y"
        "lm" -> value.isNotBlank()
        else -> false
    }

    /** Wire string from validated tags. Invalid pairs are silently dropped. */
    fun build(tags: Map<String, String>): String? {
        val parts = ArrayList<String>(tags.size)
        for (key in KEY_ORDER) {
            val v = tags[key]?.trim()?.lowercase() ?: continue
            val value = if (key == "lm") tags["lm"]!!.trim().take(LM_MAX) else v
            if (isValid(key, value)) parts.add("$key:$value")
        }
        if (parts.isEmpty()) return null
        return PREFIX + parts.joinToString(" ")
    }

    /** Parse an incoming "TAGS …" gist (responder phones render these as merged detail,
     *  never as raw wire text). Returns null when it isn't valid TAGS at all. */
    fun parse(gist: String): Map<String, String>? {
        if (!gist.startsWith(PREFIX)) return null
        var rest = gist.removePrefix(PREFIX).trim()
        if (rest.isEmpty()) return null
        val tags = LinkedHashMap<String, String>()
        while (rest.isNotEmpty()) {
            val colon = rest.indexOf(':')
            // A malformed TAIL (a 244B gist-trim can cut mid-pair) keeps the pairs already
            // parsed; a malformed HEAD means this isn't TAGS at all.
            if (colon <= 0) return if (tags.isEmpty()) null else tags
            val key = rest.substring(0, colon).trim().lowercase()
            if (!key.all { it.isLetter() }) return if (tags.isEmpty()) null else tags
            val after = rest.substring(colon + 1)
            if (key == "lm") {
                val lm = after.trim().take(LM_MAX)
                if (lm.isNotEmpty()) tags["lm"] = lm
                break
            }
            val space = after.indexOf(' ')
            val value = (if (space < 0) after else after.substring(0, space)).trim().lowercase()
            rest = if (space < 0) "" else after.substring(space + 1).trim()
            if (isValid(key, value)) tags[key] = value
            // invalid pair: drop it, keep parsing the rest (mirrors the server)
        }
        return tags.ifEmpty { null }
    }

    /** Plain-text English summary for responder cards / logs — never the raw wire string. */
    fun humanize(tags: Map<String, String>): String {
        val parts = ArrayList<String>()
        tags["c"]?.toIntOrNull()?.let { parts.add(if (it > 1) "$it people" else "1 person") }
        when (tags["inj"]) {
            "bleed" -> parts.add("bleeding"); "fracture" -> parts.add("fracture")
            "burn" -> parts.add("burns"); "breath" -> parts.add("breathing difficulty")
            "uncon" -> parts.add("unconscious"); "other" -> parts.add("injured")
        }
        if (tags["trap"] == "y") parts.add("trapped")
        when (tags["hz"]) {
            "water" -> parts.add("rising water"); "fire" -> parts.add("fire")
            "collapse" -> parts.add("collapse risk"); "gas" -> parts.add("gas leak")
            "electric" -> parts.add("electrical hazard")
        }
        if (tags["mob"] == "n") parts.add("cannot move")
        if (tags["unresp"] == "y") parts.add("UNRESPONSIVE")
        tags["lm"]?.let { parts.add("near $it") }
        return parts.joinToString(" · ").ifEmpty { "situation update" }
    }
}
