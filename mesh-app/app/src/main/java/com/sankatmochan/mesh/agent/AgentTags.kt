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

    /**
     * Wire string from validated tags, guaranteed to fit [budgetBytes] UTF-8 bytes WITHOUT
     * ever cutting mid-pair or mid-word. The envelope's generic gist trim chops characters
     * blindly, which used to hand the command post half a tag ("inj:ble") or half a landmark
     * ("near old temp") — so the fitting happens HERE, where pair boundaries are known:
     * pairs that don't fit are dropped whole (KEY_ORDER is criticality-first, so the least
     * important go first), and the landmark sheds whole trailing words until it fits.
     * Invalid pairs are silently dropped.
     */
    fun build(tags: Map<String, String>, budgetBytes: Int = Int.MAX_VALUE): String? {
        val parts = ArrayList<String>(tags.size)
        fun fits(candidate: String): Boolean =
            (PREFIX + (parts + candidate).joinToString(" "))
                .toByteArray(Charsets.UTF_8).size <= budgetBytes
        for (key in KEY_ORDER) {
            val raw = tags[key]?.trim() ?: continue
            if (key == "lm") {
                var lm = capLandmark(raw)
                // Shed whole trailing words until it fits; a landmark that can't fit even
                // as one word is dropped entirely — the tags still carry the critical facts.
                while (lm.isNotEmpty() && !fits("lm:$lm")) lm = dropLastWord(lm)
                if (lm.isNotEmpty()) parts.add("lm:$lm")
            } else {
                val value = raw.lowercase()
                if (isValid(key, value) && fits("$key:$value")) parts.add("$key:$value")
            }
        }
        if (parts.isEmpty()) return null
        return PREFIX + parts.joinToString(" ")
    }

    /** Cap a landmark at [LM_MAX] chars on a WORD boundary — a mid-word cut reads as
     *  gibberish on the responder card, which is worse than a shorter landmark. */
    fun capLandmark(s: String): String {
        val t = s.trim()
        if (t.length <= LM_MAX) return t
        val cut = t.take(LM_MAX)
        val space = cut.lastIndexOf(' ')
        return (if (space > 0) cut.substring(0, space) else cut).trim()
    }

    private fun dropLastWord(s: String): String {
        val space = s.trimEnd().lastIndexOf(' ')
        return if (space > 0) s.substring(0, space).trimEnd() else ""
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
