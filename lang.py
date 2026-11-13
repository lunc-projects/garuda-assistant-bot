# ─────────────────────────────────────────────────────────────
# Language selection for Garuda Assistant Bot.
# Per-USER preference (not per-group): one user switching language never
# changes what anyone else sees. Stored in store.py (user_lang table).
# The bot's own UI texts follow the requester's language: /start,
# /language and the picker are translated here. (AI features were
# removed 2026-11-13 — the language choice now only affects these
# texts.) Data-command outputs (/price, /proposals, etc.) are
# mostly numbers + tickers and stay in English for now.
# Labels are in each language's own script so anyone can spot their
# language without reading English first.
# ─────────────────────────────────────────────────────────────

# (code, native label, English name)
LANGS = [
    ("en", "English", "English"),
    ("es", "Español", "Spanish"),
    ("pt", "Português", "Portuguese"),
    ("fr", "Français", "French"),
    ("de", "Deutsch", "German"),
    ("it", "Italiano", "Italian"),
    ("nl", "Nederlands", "Dutch"),
    ("ru", "Русский", "Russian"),
    ("uk", "Українська", "Ukrainian"),
    ("tr", "Türkçe", "Turkish"),
    ("ar", "العربية", "Arabic"),
    ("hi", "हिन्दी", "Hindi"),
    ("id", "Bahasa Indonesia", "Indonesian"),
    ("vi", "Tiếng Việt", "Vietnamese"),
    ("th", "ไทย", "Thai"),
    ("ko", "한국어", "Korean"),
    ("ja", "日本語", "Japanese"),
    ("zh", "简体中文", "Simplified Chinese"),
]

CODES = {c for c, _, _ in LANGS}
LABELS = {c: label for c, label, _ in LANGS}
ENGLISH_NAMES = {c: name for c, _, name in LANGS}
DEFAULT = "en"

# Short UI strings only. {name} = the language's native label.
# Russian/Ukrainian "picked" phrasing deliberately avoids case inflection
# ("all replies will be in this language") so the label slots in cleanly.
STRINGS = {
    "pick": {
        "en": "Choose your language:",
        "es": "Elige tu idioma:",
        "pt": "Escolha seu idioma:",
        "fr": "Choisissez votre langue :",
        "de": "Wähle deine Sprache:",
        "it": "Scegli la tua lingua:",
        "nl": "Kies je taal:",
        "ru": "Выберите язык:",
        "uk": "Оберіть мову:",
        "tr": "Dilinizi seçin:",
        "ar": "اختر لغتك:",
        "hi": "अपनी भाषा चुनें:",
        "id": "Pilih bahasa Anda:",
        "vi": "Chọn ngôn ngữ của bạn:",
        "th": "เลือกภาษาของคุณ:",
        "ko": "언어를 선택하세요:",
        "ja": "言語を選んでください:",
        "zh": "选择你的语言：",
    },
    "picked": {
        "en": "Language set to {name} — I'll reply in {name} from now on.",
        "es": "Idioma establecido: {name}. A partir de ahora responderé en {name}.",
        "pt": "Idioma definido: {name}. A partir de agora responderei em {name}.",
        "fr": "Langue définie : {name}. Je répondrai désormais en {name}.",
        "de": "Sprache eingestellt: {name}. Ich antworte ab jetzt auf {name}.",
        "it": "Lingua impostata: {name}. D'ora in poi risponderò in {name}.",
        "nl": "Taal ingesteld: {name}. Ik antwoord vanaf nu in {name}.",
        "ru": "Язык установлен: {name}. Все ответы будут на этом языке.",
        "uk": "Мову встановлено: {name}. Усі відповіді будуть цією мовою.",
        "tr": "Dil ayarlandı: {name}. Artık {name} yanıt vereceğim.",
        "ar": "تم تعيين اللغة: {name}. سأرد من الآن فصاعدًا بـ{name}.",
        "hi": "भाषा सेट हो गई: {name}। अब से मैं {name} में जवाब दूँगा।",
        "id": "Bahasa diatur: {name}. Mulai sekarang saya akan membalas dalam {name}.",
        "vi": "Đã đặt ngôn ngữ: {name}. Từ giờ tôi sẽ trả lời bằng {name}.",
        "th": "ตั้งค่าภาษาเป็น {name} แล้ว ต่อไปผมจะตอบเป็น {name}",
        "ko": "언어가 {name}(으)로 설정되었습니다. 이제부터 {name}(으)로 답변드리겠습니다.",
        "ja": "言語を{name}に設定しました。これからは{name}で返信します。",
        "zh": "语言已设置为 {name}，我从现在起会用 {name} 回复。",
    },
    "current": {
        "en": "Your language is {name}. Pick another below to change it.",
        "es": "Tu idioma es {name}. Elige otro abajo para cambiarlo.",
        "pt": "Seu idioma é {name}. Escolha outro abaixo para alterá-lo.",
        "fr": "Votre langue est {name}. Choisissez-en une autre ci-dessous pour la changer.",
        "de": "Deine Sprache ist {name}. Wähle unten eine andere, um sie zu ändern.",
        "it": "La tua lingua è {name}. Scegline un'altra qui sotto per cambiarla.",
        "nl": "Je taal is {name}. Kies hieronder een andere om te wijzigen.",
        "ru": "Ваш язык: {name}. Выберите другой ниже, чтобы изменить.",
        "uk": "Ваша мова: {name}. Оберіть іншу нижче, щоб змінити.",
        "tr": "Diliniz {name}. Değiştirmek için aşağıdan başka bir dil seçin.",
        "ar": "لغتك هي {name}. اختر لغة أخرى أدناه لتغييرها.",
        "hi": "आपकी भाषा {name} है। बदलने के लिए नीचे कोई और चुनें।",
        "id": "Bahasa Anda adalah {name}. Pilih yang lain di bawah untuk mengubahnya.",
        "vi": "Ngôn ngữ của bạn là {name}. Chọn ngôn ngữ khác bên dưới để thay đổi.",
        "th": "ภาษาของคุณคือ {name} เลือกภาษาอื่นด้านล่างเพื่อเปลี่ยน",
        "ko": "현재 언어는 {name}입니다. 변경하려면 아래에서 다른 언어를 선택하세요.",
        "ja": "現在の言語は{name}です。変更するには下から別の言語を選んでください。",
        "zh": "你当前的语言是 {name}。如需更改，请在下方选择其他语言。",
    },
    "intro": {
        "en": "🤖 I'm Garuda Assistant Bot — I answer Garuda DeFi questions from a verified knowledge base, and show live prices, proposals, and staking help.\n\nTry /ask to ask a Garuda question, /dex for the live DEX overview, or pick your language below — I'll reply in the language you choose.",
        "es": "🤖 Soy Garuda Assistant Bot: respondo preguntas sobre Garuda DeFi desde una base de conocimientos verificada y muestro precios en vivo, propuestas y ayuda sobre staking.\n\nPrueba /ask para preguntarme sobre Garuda, o elige tu idioma abajo: responderé en el idioma que elijas.",
        "pt": "🤖 Sou o Garuda Assistant Bot: respondo perguntas sobre Garuda DeFi a partir de uma base de conhecimento verificada e mostro preços ao vivo, propostas e ajuda sobre staking.\n\nExperimente /ask para me perguntar sobre a Garuda, ou escolha seu idioma abaixo: responderei no idioma que você escolher.",
        "fr": "🤖 Je suis Garuda Assistant Bot : je réponds aux questions sur Garuda DeFi à partir d'une base de connaissances vérifiée et j'affiche les prix en direct, les propositions et l'aide au staking.\n\nEssayez /ask pour me poser une question sur Garuda, ou choisissez votre langue ci-dessous : je répondrai dans la langue choisie.",
        "de": "🤖 Ich bin der Garuda Assistant Bot: Ich beantworte Fragen zu Garuda DeFi aus einer geprüften Wissensbasis und zeige Live-Preise, Vorschläge und Staking-Hilfe.\n\nProbier /ask, um mich etwas zu Garuda zu fragen, oder wähle unten deine Sprache — ich antworte in der Sprache, die du wählst.",
        "it": "🤖 Sono Garuda Assistant Bot: rispondo a domande su Garuda DeFi da una base di conoscenza verificata e mostro prezzi in tempo reale, proposte e aiuto sullo staking.\n\nProva /ask per chiedermi qualcosa su Garuda, oppure scegli la tua lingua qui sotto: risponderò nella lingua che scegli.",
        "nl": "🤖 Ik ben Garuda Assistant Bot: ik beantwoord vragen over Garuda DeFi vanuit een geverifieerde kennisbank en toon live prijzen, voorstellen en staking-hulp.\n\nProbeer /ask om me iets over Garuda te vragen, of kies hieronder je taal — ik antwoord in de taal die jij kiest.",
        "ru": "🤖 Я Garuda Assistant Bot: отвечаю на вопросы о Garuda DeFi из проверенной базы знаний и показываю цены в реальном времени, предложения и помощь по стейкингу.\n\nПопробуйте /ask, чтобы задать мне вопрос о Garuda, или выберите язык ниже — я буду отвечать на выбранном вами языке.",
        "uk": "🤖 Я Garuda Assistant Bot: відповідаю на запитання про Garuda DeFi з перевіреної бази знань та показую ціни в реальному часі, пропозиції і допомогу зі стейкінгом.\n\nСпробуйте /ask, щоб поставити мені запитання про Garuda, або оберіть мову нижче — я відповідатиму обраною вами мовою.",
        "tr": "🤖 Ben Garuda Assistant Bot: Garuda DeFi sorularını doğrulanmış bir bilgi tabanından yanıtlıyor ve canlı fiyatları, teklifleri ve staking yardımını gösteriyorum.\n\nGaruda hakkında sormak için /ask komutunu deneyin veya aşağıdan dilinizi seçin — seçtiğiniz dilde yanıt veririm.",
        "ar": "🤖 أنا Garuda Assistant Bot: أجيب عن أسئلة Garuda DeFi من قاعدة معرفة موثّقة، وأعرض الأسعار المباشرة والمقترحات والمساعدة في الستاكينغ.\n\nجرّب /ask لطرح سؤال عن Garuda، أو اختر لغتك أدناه — سأرد باللغة التي تختارها.",
        "hi": "🤖 मैं Garuda Assistant Bot हूँ: मैं सत्यापित ज्ञान-आधार से Garuda DeFi के सवालों का जवाब देता हूँ, और लाइव कीमतें, प्रस्ताव और स्टेकिंग मदद दिखाता हूँ।\n\nGaruda के बारे में पूछने के लिए /ask आज़माएँ, या नीचे अपनी भाषा चुनें — मैं आपकी चुनी भाषा में जवाब दूँगा।",
        "id": "🤖 Saya Garuda Assistant Bot: saya menjawab pertanyaan tentang Garuda DeFi dari basis pengetahuan terverifikasi, dan menampilkan harga live, proposal, serta bantuan staking.\n\nCoba /ask untuk bertanya tentang Garuda, atau pilih bahasa Anda di bawah — saya akan membalas dalam bahasa yang Anda pilih.",
        "vi": "🤖 Tôi là Garuda Assistant Bot: tôi trả lời câu hỏi về Garuda DeFi từ cơ sở kiến thức đã xác minh và hiển thị giá trực tiếp, đề xuất và trợ giúp staking.\n\nThử /ask để hỏi tôi về Garuda, hoặc chọn ngôn ngữ của bạn bên dưới — tôi sẽ trả lời bằng ngôn ngữ bạn chọn.",
        "th": "🤖 ผมคือ Garuda Assistant Bot: ผมตอบคำถามเกี่ยวกับ Garuda DeFi จากฐานความรู้ที่ตรวจสอบแล้ว และแสดงราคาสด ข้อเสนอ และความช่วยเหลือเรื่อง staking\n\nลอง /ask เพื่อถามเรื่อง Garuda หรือเลือกภาษาของคุณด้านล่าง — ผมจะตอบในภาษาที่คุณเลือก",
        "ko": "🤖 저는 Garuda Assistant Bot입니다. 검증된 지식 베이스로 Garuda DeFi에 대한 질문에 답하며, 실시간 가격, 제안, 스테이킹 도움을 보여줍니다.\n\nGaruda에 대해 물어보려면 /ask를 사용하거나 아래에서 언어를 선택하세요. 선택하신 언어로 답변드리겠습니다.",
        "ja": "🤖 私はGaruda Assistant Botです。検証済みのナレッジベースでGaruda DeFiに関する質問に答え、ライブ価格や提案、ステーキングのヘルプを表示します。\n\nGarudaについての質問は /ask を試すか、下で言語を選んでください。選んだ言語で返信します。",
        "zh": "🤖 我是 Garuda Assistant Bot：我会根据已验证的知识库回答 Garuda DeFi 相关问题，并显示实时价格、提案和质押帮助。\n\n试试用 /ask 向我询问 Garuda，或在下方选择你的语言——我会用你选择的语言回复。",
    },
}


def normalize(code):
    """Any stored/unknown code falls back to English — never crash on it."""
    return code if code in CODES else DEFAULT


def t(key, lang=DEFAULT, **kw):
    """Translated UI string; falls back to English for a missing key/lang."""
    table = STRINGS.get(key, {})
    text = table.get(normalize(lang)) or table.get(DEFAULT, "")
    return text.format(**kw) if kw else text


def lang_keyboard():
    """Inline keyboard: 2 columns of native-script labels. Imported lazily
    so plain unit tests can use this module without python-telegram-bot."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    rows = []
    for i in range(0, len(LANGS), 2):
        row = [InlineKeyboardButton(LANGS[j][1], callback_data=f"lang:{LANGS[j][0]}")
               for j in range(i, min(i + 2, len(LANGS)))]
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def instruction(lang):
    """Extra system-prompt line for AI replies. Empty for English."""
    lang = normalize(lang)
    if lang == DEFAULT:
        return ""
    return (f"Reply entirely in {ENGLISH_NAMES[lang]}. "
            "Keep tickers, contract addresses, wallet addresses, numbers, "
            "and command names exactly as-is — translate only the prose around them.")
