"""Localised clarification questions and spoken confirmations.

Strings for Hindi, Tamil and Marathi are first drafts and need native-speaker review
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
        "UNKNOWN_PRODUCT": "I couldn't find \"{spoken}\" in the catalogue. Which product is it?",
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
        "UNKNOWN_PRODUCT": "\"{spoken}\" catalogue mein nahi mila. Kaun sa product hai?",
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
        "UNKNOWN_PRODUCT": "\"{spoken}\" कैटलॉग में नहीं मिला। कौन सा प्रोडक्ट है?",
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
        "MISSING_QUANTITY": "{item} किती हवे?",
        "UNIT_MISMATCH": "{item} साठी कोणते एकक?",
        "MISSING_AMOUNT": "रक्कम किती आहे?",
        "AMBIGUOUS_DATE": "{what} साठी कोणती तारीख?",
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
}

_WHAT = {
    "payment": {"en-IN": "the payment", "hinglish": "payment", "hi-IN": "भुगतान", "ta-IN": "பணம்", "mr-IN": "पेमेंट"},
    "delivery": {"en-IN": "the delivery", "hinglish": "delivery", "hi-IN": "डिलीवरी", "ta-IN": "டெலிவரி", "mr-IN": "डिलिव्हरी"},
}


def _lang(code: str) -> str:
    return code if code in _Q else "en-IN"


def render_question(language: str, issue: dict[str, Any], draft: dict[str, Any]) -> str:
    template = _Q[_lang(language)].get(issue["code"], _Q["en-IN"]["MISSING_CUSTOMER"])
    return template.format(
        spoken=issue.get("spoken") or "",
        item=issue.get("item") or "",
        what=_what(language, issue),
    )


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
