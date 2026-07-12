package com.sankatmochan.mesh.agent

/**
 * Pre-authored fallback strings for the Sahayak agent — used ONLY when the on-device LLM is
 * not loaded/available. The live path generates every question and reassurance with the LLM;
 * these exist so the agent never dies in a victim's hands (fallback ladder, last rung).
 *
 * Three languages: the demo languages (Tamil, Hindi) + English. Hand-written, not
 * machine-generated — they must be correct under panic, not fancy.
 */
object AgentStrings {

    data class Pack(
        val opener: String,
        val qCount: String,
        val qHurtTrapped: String,
        val qLandmark: String,
        val statusDelivered: String,
        val statusAccepted: String,
        val checkIn: String,
        val thanks: String,
        val hazardWater: String,
        val hazardFire: String,
    )

    private val EN = Pack(
        opener = "Your SOS has been sent. I'm Sahayak — I'll stay with you. A few quick questions will help the rescue team.",
        qCount = "How many people are with you?",
        qHurtTrapped = "Is anyone hurt or trapped?",
        qLandmark = "What can you see near you — a shop, temple, bridge?",
        statusDelivered = "The control room has your message.",
        statusAccepted = "A rescue team has accepted and is on the way.",
        checkIn = "I'm here. Tap the big button when you can.",
        thanks = "Thank you. The rescue team now knows your situation. Stay where you are if it is safe.",
        hazardWater = "Stay out of the water. Move to the highest place you can reach.",
        hazardFire = "Stay low, below the smoke. Cover your nose and mouth.",
    )

    private val TA = Pack(
        opener = "உங்கள் SOS அனுப்பப்பட்டது. நான் சகாயக் — உங்களுடன் இருக்கிறேன். சில சிறு கேள்விகள் மீட்புக் குழுவுக்கு உதவும்.",
        qCount = "உங்களுடன் எத்தனை பேர் இருக்கிறார்கள்?",
        qHurtTrapped = "யாருக்காவது காயமா? யாராவது மாட்டிக்கொண்டிருக்கிறார்களா?",
        qLandmark = "உங்கள் அருகில் என்ன தெரிகிறது — கடை, கோவில், பாலம்?",
        statusDelivered = "உங்கள் செய்தி கட்டுப்பாட்டு அறையை அடைந்தது.",
        statusAccepted = "மீட்புக் குழு ஏற்றுக்கொண்டது — உதவி வருகிறது.",
        checkIn = "நான் இங்கே இருக்கிறேன். முடிந்தால் பெரிய பொத்தானைத் தட்டவும்.",
        thanks = "நன்றி. உங்கள் நிலைமை மீட்புக் குழுவுக்குத் தெரியும். பாதுகாப்பாக இருந்தால் அங்கேயே இருங்கள்.",
        hazardWater = "தண்ணீரில் இறங்க வேண்டாம். முடிந்தவரை உயரமான இடத்திற்குச் செல்லுங்கள்.",
        hazardFire = "புகைக்குக் கீழே குனிந்து இருங்கள். மூக்கையும் வாயையும் மூடிக்கொள்ளுங்கள்.",
    )

    private val HI = Pack(
        opener = "आपका SOS भेज दिया गया है। मैं सहायक हूँ — आपके साथ हूँ। कुछ छोटे सवाल बचाव दल की मदद करेंगे।",
        qCount = "आपके साथ कितने लोग हैं?",
        qHurtTrapped = "क्या कोई घायल है? क्या कोई फँसा हुआ है?",
        qLandmark = "आपके पास क्या दिख रहा है — दुकान, मंदिर, पुल?",
        statusDelivered = "आपका संदेश कंट्रोल रूम तक पहुँच गया है।",
        statusAccepted = "बचाव दल ने स्वीकार कर लिया है — मदद आ रही है।",
        checkIn = "मैं यहीं हूँ। जब हो सके, बड़ा बटन दबाइए।",
        thanks = "धन्यवाद। बचाव दल को अब आपकी स्थिति पता है। अगर सुरक्षित हैं तो वहीं रहिए।",
        hazardWater = "पानी में मत उतरिए। जितना हो सके ऊँची जगह पर जाइए।",
        hazardFire = "धुएँ के नीचे झुककर रहिए। नाक और मुँह ढक लीजिए।",
    )

    fun forLang(lang: String): Pack = when (lang.lowercase().take(2)) {
        "ta" -> TA
        "hi" -> HI
        else -> EN
    }

    /** English names for the LLM's reply-language instruction (mirrors ChatViewModel). */
    fun languageName(code: String): String = when (code.lowercase().take(2)) {
        "hi" -> "Hindi"; "ta" -> "Tamil"; "te" -> "Telugu"; "kn" -> "Kannada"
        "ml" -> "Malayalam"; "bn" -> "Bengali"; "mr" -> "Marathi"; "gu" -> "Gujarati"
        "pa" -> "Punjabi"; "or" -> "Odia"; "as" -> "Assamese"; "ur" -> "Urdu"
        else -> "English"
    }
}
