"""Localised clarification questions and spoken confirmations.

Strings for every language except English and Hinglish are first drafts and need native-speaker review
before any public demo.
"""

from __future__ import annotations

from typing import Any

_Q: dict[str, dict[str, str]] = {
    "en-IN": {
        "MISSING_CUSTOMER": "Which retailer did you visit?",
        "UNKNOWN_CUSTOMER": "I couldn't find \"{spoken}\". Which retailer did you visit?",
        "AMBIGUOUS_CUSTOMER": "Which retailer did you mean by \"{spoken}\"?",
        "AMBIGUOUS_PRODUCT": "Which product did you mean by \"{spoken}\"?",
        "UNKNOWN_PRODUCT": "I couldn't find \"{spoken}\" in the catalogue. Pick the product, or say \"add it\" with its price, e.g. \"add, 60 rupees per kg\".",
        "NEW_PRODUCT_PRICE": "What is the price of {item}? Say the price in rupees{unit}.",
        "NEW_PRODUCT_UNIT": "{item} is sold by which unit: kg, packet, bottle or piece?",
        "MISSING_QUANTITY": "How many {item}?",
        "UNIT_MISMATCH": "Which unit for {item}?",
        "MISSING_AMOUNT": "What is the payment amount?",
        "AMBIGUOUS_DATE": "Which date should I use for: {what}?",
    },
    "hinglish": {
        "MISSING_CUSTOMER": "Aap kis retailer se mile?",
        "UNKNOWN_CUSTOMER": "\"{spoken}\" nahi mila. Aap kis retailer se mile?",
        "AMBIGUOUS_CUSTOMER": "\"{spoken}\" se aapka matlab kaun sa retailer hai?",
        "AMBIGUOUS_PRODUCT": "\"{spoken}\" se aapka matlab kaun sa product hai?",
        "UNKNOWN_PRODUCT": "\"{spoken}\" catalogue mein nahi mila. Product chuniye, ya bolo \"add karo\" aur price, jaise \"add karo, 60 rupaye kilo\".",
        "NEW_PRODUCT_PRICE": "{item} ka price kitna hai? Rupaye mein bolo{unit}.",
        "NEW_PRODUCT_UNIT": "{item} kis unit mein bikta hai: kilo, packet, bottle ya piece?",
        "MISSING_QUANTITY": "{item} kitna chahiye?",
        "UNIT_MISMATCH": "{item} ki unit kya hai?",
        "MISSING_AMOUNT": "Payment ki raashi kitni hai?",
        "AMBIGUOUS_DATE": "{what} ke liye kaun si tareekh rakhun?",
    },
    "hi-IN": {
        "MISSING_CUSTOMER": "आप किस रिटेलर से मिले?",
        "UNKNOWN_CUSTOMER": "\"{spoken}\" नहीं मिला। आप किस रिटेलर से मिले?",
        "AMBIGUOUS_CUSTOMER": "\"{spoken}\" से आपका मतलब कौन सा रिटेलर है?",
        "AMBIGUOUS_PRODUCT": "\"{spoken}\" से आपका मतलब कौन सा प्रोडक्ट है?",
        "UNKNOWN_PRODUCT": "\"{spoken}\" कैटलॉग में नहीं मिला। प्रोडक्ट चुनें, या बोलें \"add करो\" और कीमत।",
        "NEW_PRODUCT_PRICE": "{item} की कीमत कितनी है? रुपये में बोलें{unit}.",
        "NEW_PRODUCT_UNIT": "{item} किस यूनिट में बिकता है: किलो, पैकेट, बोतल या पीस?",
        "MISSING_QUANTITY": "{item} कितना चाहिए?",
        "UNIT_MISMATCH": "{item} की यूनिट क्या है?",
        "MISSING_AMOUNT": "भुगतान की राशि कितनी है?",
        "AMBIGUOUS_DATE": "{what} के लिए कौन सी तारीख रखूँ?",
    },
    "ta-IN": {
        "MISSING_CUSTOMER": "நீங்கள் எந்த கடையைச் சந்தித்தீர்கள்?",
        "UNKNOWN_CUSTOMER": "\"{spoken}\" கிடைக்கவில்லை. நீங்கள் எந்த கடையைச் சந்தித்தீர்கள்?",
        "AMBIGUOUS_CUSTOMER": "\"{spoken}\" என்பதில் எந்த கடை?",
        "AMBIGUOUS_PRODUCT": "\"{spoken}\" என்பதில் எந்த பொருள்?",
        "UNKNOWN_PRODUCT": "\"{spoken}\" பட்டியலில் இல்லை. எந்த பொருள்?",
        "NEW_PRODUCT_PRICE": "{item} விலை எவ்வளவு?{unit}",
        "NEW_PRODUCT_UNIT": "{item} எந்த அலகில் விற்கப்படுகிறது?",
        "MISSING_QUANTITY": "{item} எத்தனை வேண்டும்?",
        "UNIT_MISMATCH": "{item}க்கு எந்த அலகு?",
        "MISSING_AMOUNT": "பணத்தின் தொகை எவ்வளவு?",
        "AMBIGUOUS_DATE": "{what}க்கு எந்த தேதி?",
    },
    "mr-IN": {
        "MISSING_CUSTOMER": "तुम्ही कोणत्या दुकानदाराला भेटलात?",
        "UNKNOWN_CUSTOMER": "\"{spoken}\" सापडले नाही. तुम्ही कोणत्या दुकानदाराला भेटलात?",
        "AMBIGUOUS_CUSTOMER": "\"{spoken}\" म्हणजे कोणता दुकानदार?",
        "AMBIGUOUS_PRODUCT": "\"{spoken}\" म्हणजे कोणते उत्पादन?",
        "UNKNOWN_PRODUCT": "\"{spoken}\" यादीत सापडले नाही. कोणते उत्पादन?",
        "NEW_PRODUCT_PRICE": "{item} ची किंमत किती?{unit}",
        "NEW_PRODUCT_UNIT": "{item} कोणत्या एककात विकले जाते?",
        "MISSING_QUANTITY": "{item} किती हवे?",
        "UNIT_MISMATCH": "{item} साठी कोणते एकक?",
        "MISSING_AMOUNT": "रक्कम किती आहे?",
        "AMBIGUOUS_DATE": "{what} साठी कोणती तारीख?",
    },
    "te-IN": {
        "MISSING_CUSTOMER": "మీరు ఏ దుకాణాన్ని సందర్శించారు?",
        "UNKNOWN_CUSTOMER": "\"{spoken}\" కనబడలేదు. మీరు ఏ దుకాణాన్ని సందర్శించారు?",
        "AMBIGUOUS_CUSTOMER": "\"{spoken}\" అంటే ఏ దుకాణం?",
        "AMBIGUOUS_PRODUCT": "\"{spoken}\" అంటే ఏ ఉత్పత్తి?",
        "UNKNOWN_PRODUCT": "\"{spoken}\" జాబితాలో లేదు. ఏ ఉత్పత్తి?",
        "NEW_PRODUCT_PRICE": "{item} ధర ఎంత?{unit}",
        "NEW_PRODUCT_UNIT": "{item} ఏ యూనిట్‌లో అమ్ముతారు?",
        "MISSING_QUANTITY": "{item} ఎంత కావాలి?",
        "UNIT_MISMATCH": "{item} కి ఏ యూనిట్?",
        "MISSING_AMOUNT": "చెల్లింపు మొత్తం ఎంత?",
        "AMBIGUOUS_DATE": "{what} కి ఏ తేదీ?",
    },
    "kn-IN": {
        "MISSING_CUSTOMER": "ನೀವು ಯಾವ ಅಂಗಡಿಗೆ ಭೇಟಿ ನೀಡಿದ್ದೀರಿ?",
        "UNKNOWN_CUSTOMER": "\"{spoken}\" ಸಿಗಲಿಲ್ಲ. ನೀವು ಯಾವ ಅಂಗಡಿಗೆ ಭೇಟಿ ನೀಡಿದ್ದೀರಿ?",
        "AMBIGUOUS_CUSTOMER": "\"{spoken}\" ಎಂದರೆ ಯಾವ ಅಂಗಡಿ?",
        "AMBIGUOUS_PRODUCT": "\"{spoken}\" ಎಂದರೆ ಯಾವ ಉತ್ಪನ್ನ?",
        "UNKNOWN_PRODUCT": "\"{spoken}\" ಪಟ್ಟಿಯಲ್ಲಿ ಇಲ್ಲ. ಯಾವ ಉತ್ಪನ್ನ?",
        "NEW_PRODUCT_PRICE": "{item} ಬೆಲೆ ಎಷ್ಟು?{unit}",
        "NEW_PRODUCT_UNIT": "{item} ಯಾವ ಘಟಕದಲ್ಲಿ ಮಾರಾಟವಾಗುತ್ತದೆ?",
        "MISSING_QUANTITY": "{item} ಎಷ್ಟು ಬೇಕು?",
        "UNIT_MISMATCH": "{item} ಗೆ ಯಾವ ಘಟಕ?",
        "MISSING_AMOUNT": "ಪಾವತಿಯ ಮೊತ್ತ ಎಷ್ಟು?",
        "AMBIGUOUS_DATE": "{what} ಗೆ ಯಾವ ದಿನಾಂಕ?",
    },
    "ml-IN": {
        "MISSING_CUSTOMER": "നിങ്ങൾ ഏത് കടയാണ് സന്ദർശിച്ചത്?",
        "UNKNOWN_CUSTOMER": "\"{spoken}\" കണ്ടെത്തിയില്ല. നിങ്ങൾ ഏത് കടയാണ് സന്ദർശിച്ചത്?",
        "AMBIGUOUS_CUSTOMER": "\"{spoken}\" എന്നത് ഏത് കടയാണ്?",
        "AMBIGUOUS_PRODUCT": "\"{spoken}\" എന്നത് ഏത് ഉൽപ്പന്നമാണ്?",
        "UNKNOWN_PRODUCT": "\"{spoken}\" പട്ടികയിൽ ഇല്ല. ഏത് ഉൽപ്പന്നം?",
        "NEW_PRODUCT_PRICE": "{item} വില എത്രയാണ്?{unit}",
        "NEW_PRODUCT_UNIT": "{item} ഏത് യൂണിറ്റിലാണ് വിൽക്കുന്നത്?",
        "MISSING_QUANTITY": "{item} എത്ര വേണം?",
        "UNIT_MISMATCH": "{item} ന് ഏത് യൂണിറ്റ്?",
        "MISSING_AMOUNT": "പേയ്‌മെന്റ് തുക എത്രയാണ്?",
        "AMBIGUOUS_DATE": "{what} ന് ഏത് തീയതി?",
    },
    "bn-IN": {
        "MISSING_CUSTOMER": "আপনি কোন দোকানে গিয়েছিলেন?",
        "UNKNOWN_CUSTOMER": "\"{spoken}\" পাওয়া যায়নি। আপনি কোন দোকানে গিয়েছিলেন?",
        "AMBIGUOUS_CUSTOMER": "\"{spoken}\" বলতে কোন দোকান?",
        "AMBIGUOUS_PRODUCT": "\"{spoken}\" বলতে কোন পণ্য?",
        "UNKNOWN_PRODUCT": "\"{spoken}\" তালিকায় নেই। কোন পণ্য?",
        "NEW_PRODUCT_PRICE": "{item} এর দাম কত?{unit}",
        "NEW_PRODUCT_UNIT": "{item} কোন ইউনিটে বিক্রি হয়?",
        "MISSING_QUANTITY": "{item} কতটা লাগবে?",
        "UNIT_MISMATCH": "{item} এর ইউনিট কী?",
        "MISSING_AMOUNT": "পেমেন্টের পরিমাণ কত?",
        "AMBIGUOUS_DATE": "{what} এর জন্য কোন তারিখ?",
    },
    "gu-IN": {
        "MISSING_CUSTOMER": "તમે કયા દુકાનદારને મળ્યા?",
        "UNKNOWN_CUSTOMER": "\"{spoken}\" મળ્યું નથી. તમે કયા દુકાનદારને મળ્યા?",
        "AMBIGUOUS_CUSTOMER": "\"{spoken}\" એટલે કયા દુકાનદાર?",
        "AMBIGUOUS_PRODUCT": "\"{spoken}\" એટલે કયું ઉત્પાદન?",
        "UNKNOWN_PRODUCT": "\"{spoken}\" યાદીમાં નથી. કયું ઉત્પાદન?",
        "NEW_PRODUCT_PRICE": "{item} ની કિંમત કેટલી છે?{unit}",
        "NEW_PRODUCT_UNIT": "{item} કયા એકમમાં વેચાય છે?",
        "MISSING_QUANTITY": "{item} કેટલું જોઈએ?",
        "UNIT_MISMATCH": "{item} માટે કયું એકમ?",
        "MISSING_AMOUNT": "ચુકવણીની રકમ કેટલી છે?",
        "AMBIGUOUS_DATE": "{what} માટે કઈ તારીખ?",
    },
    "pa-IN": {
        "MISSING_CUSTOMER": "ਤੁਸੀਂ ਕਿਹੜੇ ਦੁਕਾਨਦਾਰ ਨੂੰ ਮਿਲੇ?",
        "UNKNOWN_CUSTOMER": "\"{spoken}\" ਨਹੀਂ ਮਿਲਿਆ। ਤੁਸੀਂ ਕਿਹੜੇ ਦੁਕਾਨਦਾਰ ਨੂੰ ਮਿਲੇ?",
        "AMBIGUOUS_CUSTOMER": "\"{spoken}\" ਤੋਂ ਤੁਹਾਡਾ ਮਤਲਬ ਕਿਹੜਾ ਦੁਕਾਨਦਾਰ ਹੈ?",
        "AMBIGUOUS_PRODUCT": "\"{spoken}\" ਤੋਂ ਤੁਹਾਡਾ ਮਤਲਬ ਕਿਹੜਾ ਉਤਪਾਦ ਹੈ?",
        "UNKNOWN_PRODUCT": "\"{spoken}\" ਸੂਚੀ ਵਿੱਚ ਨਹੀਂ ਹੈ। ਕਿਹੜਾ ਉਤਪਾਦ?",
        "NEW_PRODUCT_PRICE": "{item} ਦੀ ਕੀਮਤ ਕਿੰਨੀ ਹੈ?{unit}",
        "NEW_PRODUCT_UNIT": "{item} ਕਿਸ ਇਕਾਈ ਵਿੱਚ ਵਿਕਦਾ ਹੈ?",
        "MISSING_QUANTITY": "{item} ਕਿੰਨਾ ਚਾਹੀਦਾ ਹੈ?",
        "UNIT_MISMATCH": "{item} ਲਈ ਕਿਹੜੀ ਇਕਾਈ?",
        "MISSING_AMOUNT": "ਭੁਗਤਾਨ ਦੀ ਰਕਮ ਕਿੰਨੀ ਹੈ?",
        "AMBIGUOUS_DATE": "{what} ਲਈ ਕਿਹੜੀ ਤਾਰੀਖ?",
    },
}

_CONFIRM: dict[str, dict[str, str]] = {
    "en-IN": {
        "visit": "Visit to {customer} saved.",
        "order": "Order of {n} items, total {amount} rupees.",
        "follow": "{k} follow-ups scheduled.",
    },
    "hinglish": {
        "visit": "{customer} ka visit save ho gaya.",
        "order": "Order mein {n} items hain, total {amount} rupaye.",
        "follow": "{k} follow-up schedule ho gaye.",
    },
    "hi-IN": {
        "visit": "{customer} की विज़िट सेव हो गई।",
        "order": "ऑर्डर में {n} आइटम हैं, कुल {amount} रुपये।",
        "follow": "{k} फॉलो-अप शेड्यूल हो गए।",
    },
    "ta-IN": {
        "visit": "{customer} வருகை சேமிக்கப்பட்டது.",
        "order": "ஆர்டரில் {n} பொருட்கள், மொத்தம் {amount} ரூபாய்.",
        "follow": "{k} பின்தொடர்தல்கள் திட்டமிடப்பட்டன.",
    },
    "mr-IN": {
        "visit": "{customer} ची भेट जतन झाली.",
        "order": "ऑर्डरमध्ये {n} वस्तू, एकूण {amount} रुपये.",
        "follow": "{k} फॉलो-अप ठरवले गेले.",
    },
    "te-IN": {
        "visit": "{customer} సందర్శన సేవ్ చేయబడింది.",
        "order": "ఆర్డర్‌లో {n} వస్తువులు, మొత్తం {amount} రూపాయలు.",
        "follow": "{k} ఫాలో-అప్‌లు షెడ్యూల్ చేయబడ్డాయి.",
    },
    "kn-IN": {
        "visit": "{customer} ಭೇಟಿ ಉಳಿಸಲಾಗಿದೆ.",
        "order": "ಆರ್ಡರ್‌ನಲ್ಲಿ {n} ವಸ್ತುಗಳು, ಒಟ್ಟು {amount} ರೂಪಾಯಿ.",
        "follow": "{k} ಫಾಲೋ-ಅಪ್‌ಗಳನ್ನು ನಿಗದಿಪಡಿಸಲಾಗಿದೆ.",
    },
    "ml-IN": {
        "visit": "{customer} സന്ദർശനം സേവ് ചെയ്തു.",
        "order": "ഓർഡറിൽ {n} ഇനങ്ങൾ, ആകെ {amount} രൂപ.",
        "follow": "{k} ഫോളോ-അപ്പുകൾ ഷെഡ്യൂൾ ചെയ്തു.",
    },
    "bn-IN": {
        "visit": "{customer} এর ভিজিট সেভ হয়েছে।",
        "order": "অর্ডারে {n}টি আইটেম, মোট {amount} টাকা।",
        "follow": "{k}টি ফলো-আপ নির্ধারিত হয়েছে।",
    },
    "gu-IN": {
        "visit": "{customer} ની મુલાકાત સેવ થઈ ગઈ.",
        "order": "ઓર્ડરમાં {n} વસ્તુઓ, કુલ {amount} રૂપિયા.",
        "follow": "{k} ફોલો-અપ નક્કી થયા.",
    },
    "pa-IN": {
        "visit": "{customer} ਦੀ ਵਿਜ਼ਿਟ ਸੇਵ ਹੋ ਗਈ।",
        "order": "ਆਰਡਰ ਵਿੱਚ {n} ਆਈਟਮ, ਕੁੱਲ {amount} ਰੁਪਏ।",
        "follow": "{k} ਫਾਲੋ-ਅੱਪ ਤੈਅ ਹੋ ਗਏ।",
    },
}

_WHAT = {
    "payment": {"en-IN": "the payment", "hinglish": "payment", "hi-IN": "भुगतान", "ta-IN": "பணம்", "mr-IN": "पेमेंट", "te-IN": "చెల్లింపు", "kn-IN": "ಪಾವತಿ", "ml-IN": "പേയ്‌മെന്റ്", "bn-IN": "পেমেন্ট", "gu-IN": "ચુકવણી", "pa-IN": "ਭੁਗਤਾਨ"},
    "delivery": {"en-IN": "the delivery", "hinglish": "delivery", "hi-IN": "डिलीवरी", "ta-IN": "டெலிவரி", "mr-IN": "डिलिव्हरी", "te-IN": "డెలివరీ", "kn-IN": "ಡೆಲಿವರಿ", "ml-IN": "ഡെലിവറി", "bn-IN": "ডেলিভারি", "gu-IN": "ડિલિવરી", "pa-IN": "ਡਿਲੀਵਰੀ"},
}


def _lang(code: str) -> str:
    return code if code in _Q else "en-IN"


def render_question(language: str, issue: dict[str, Any], draft: dict[str, Any]) -> str:
    template = _Q[_lang(language)].get(issue["code"], _Q["en-IN"]["MISSING_CUSTOMER"])
    return template.format(
        spoken=issue.get("spoken") or "",
        item=issue.get("item") or "",
        what=_what(language, issue),
        unit=_per(issue),
    )


def _per(issue: dict[str, Any]) -> str:
    """' per kg' when the unit of a new item is already known."""
    return f" per {issue['unit']}" if issue.get("unit") else ""


def _what(language: str, issue: dict[str, Any]) -> str:
    path = issue.get("fieldPath", "")
    if path.startswith("collections"):
        return _WHAT["payment"][_lang(language)]
    if path.startswith("order"):
        return _WHAT["delivery"][_lang(language)]
    return issue.get("what") or ""


def render_confirmation(language: str, *, customer: str, items: int, total_paise: int, follow_ups: int) -> str:
    t = _CONFIRM[_lang(language)]
    parts = [t["visit"].format(customer=customer)]
    if items:
        parts.append(t["order"].format(n=items, amount=f"{total_paise / 100:,.0f}"))
    if follow_ups:
        parts.append(t["follow"].format(k=follow_ups))
    return " ".join(parts)
