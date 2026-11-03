"""Friendly help for first-time visitors: intro, step tracker, sidebar guide, field tips, examples.

Everything here only draws help text and small helpers. It never touches the poster pipeline, so
adding it to the page cannot break generation. All text exists in English ("en") and Korean ("ko").

Typical use in streamlit_app.py (see the comments next to each function):

    from lyric2poster import ui_help
    ui_help.inject_css()
    lang = ui_help.sidebar_help()
    ui_help.show_steps(step, lang)
    ui_help.intro(lang, expanded=(step == 1))
    ui_help.mode_notice(director.name, engine.name, lang)
"""
from __future__ import annotations

import re
from typing import Callable, Sequence

import streamlit as st

try:  # normal case: this file lives inside the lyric2poster/ folder
    from .styles import STYLES
except ImportError:  # file was put somewhere else: look for styles.py as a package module or a sibling
    try:
        from lyric2poster.styles import STYLES
    except ImportError:
        from styles import STYLES  # type: ignore[no-redef]

LANGS = {"en": "English", "ko": "한국어"}
_LANG_KEY = "ui_lang"

TEXTS: dict[str, dict] = {
    "en": {
        "language": "Language",
        "access_title": "Access",
        "access_caption": "You do not need a key to try the app. Without one it runs in demo mode: a sample art brief and a simple drawn poster.",
        "passcode": "Class passcode (to use the owner's key)",
        "wrong_passcode": "Wrong passcode.",
        "byo_key": "Or paste your own Claude API key",
        "byo_help": "Used only for your requests in this session. Never stored.",
        "left": "Briefs left: {briefs}  |  Posters left: {posters}",
        "lbl_chart": "Chart",
        "lbl_song": "Song",
        "own_song": "Type my own song",
        "lbl_title": "Title",
        "lbl_artist": "Artist",
        "lbl_lyrics": "Lyrics (used once, never saved)",
        "btn_brief": "2. Write the art brief",
        "btn_reload": "Load lyrics again",
        "btn_poster": "3. Make the poster",
        "lbl_style": "Style",
        "mood": "Mood",
        "imagery": "Imagery",
        "palette": "Palette",
        "btn_download": "Download PNG",
        "ai_note": "AI-generated image. Title and artist were added as text afterwards.",
        "err_limit_brief": "You have used all your briefs for this session.",
        "err_limit_poster": "You have used all your posters for this session.",
        "err_style": "This style is not available yet. Please pick another one.",
        "fallback_warn": "The image engine failed, so this is the offline demo poster. ({note})",
        "lyrics_loaded": "Lyrics loaded from {name}. You can edit them. They are erased after the brief.",
        "lyrics_none": "No lyrics found for this song. Please paste your own text.",
        "example_loaded": "Example lyrics loaded. The song is made up for this demo.",
        "sensitive": "This song touches sensitive themes, so the poster will treat them abstractly.",
        "brief_intro": "This is the AI's plan for your poster. Happy with it? Pick a style below and press the poster button.",
        "poster_done": "Your poster is ready! Not quite right? Pick another style and press the button again.",
        "spinner_poster": "Painting your poster… this can take up to a minute.",
        "sidebar_title": "Quick guide",
        "hero_sub": "Paste the lyrics, let the AI plan the artwork, then pick a style. It takes about a minute.",
        "how_title": "How does this work?",
        "steps": [
            ("Add the song", "Pick a song, or type the title, artist and lyrics yourself."),
            ("Write the art brief", "The AI describes the mood, colors and imagery. You can read it before you go on."),
            ("Make the poster", "Choose a style, press the button, then download your poster."),
        ],
        "step_labels": ["1 · Add the song", "2 · Art brief", "3 · Poster"],
        "now": "You are here",
        "demo_director": "The art brief comes from sample ideas, not from your lyrics.",
        "demo_engine": "The picture is a simple generated landscape, not an AI image.",
        "demo_title": "Demo mode",
        "demo_body": "Everything works, but results are basic. The app owner can switch on the real AI in the app settings.",
        "privacy": "Your lyrics are used once to write the brief and are never saved. Only the title and artist are printed on the poster.",
        "copyright": "Only paste lyrics you are allowed to use. Posters are for learning and personal use.",
        "try_example": "Not sure where to start? Try an example:",
        "example_note": "Example songs are made up for this demo.",
        "styles_title": "What do the styles look like?",
        "faq_title": "Common questions",
        "faq": [
            ("Nothing happens when I press the button",
             "Check that the title, artist and lyrics are filled in. The first picture can take up to a minute."),
            ("The poster looks plain",
             "In demo mode the pictures are simple on purpose. Try another style, or ask the app owner to switch on the AI image engine."),
            ("How do I save my poster?",
             "Press the Download button under the poster."),
            ("Can I change the look?",
             "Yes. Pick another style and press the poster button again. Each style changes the whole look."),
        ],
        "tips": {
            "chart": "Browse songs from a chart, or keep the demo chart to try the app.",
            "song": "Choose a song from the chart, or pick 'Type my own song'.",
            "title": "The song title. It is printed on the poster.",
            "artist": "The artist name. It is printed under the title.",
            "lyrics": "Paste the lyrics here. They are used once to plan the artwork and are never saved. They are not printed on the poster.",
            "brief": "The AI reads the lyrics and writes a short plan for the poster: mood, colors and imagery.",
            "style": "The look of the poster. Open 'What do the styles look like?' for a guide.",
            "poster": "Creates the poster in the chosen style. It can take up to a minute.",
        },
        "need_title": "Please type the song title.",
        "need_artist": "Please type the artist name.",
        "need_lyrics": "Please paste the lyrics.",
        "short_lyrics": "The lyrics look very short. Add a few more lines so the AI can feel the mood.",
        "try_again": "Please try again. If it keeps failing, tell the app owner.",
        "hint_key": "Ask the app owner to check the access key.",
        "hint_busy": "The free image service may be busy or out of daily quota. Wait a few minutes and try again.",
        "hint_cut": "Please try again.",
        "hint_declined": "Try a different song.",
    },
    "ko": {
        "language": "언어",
        "access_title": "접근",
        "access_caption": "키가 없어도 체험할 수 있어요. 키가 없으면 데모 모드로 작동해요: 샘플 아트 브리프와 간단히 그린 포스터가 나와요.",
        "passcode": "수업 암호 (관리자 키를 사용하려면)",
        "wrong_passcode": "암호가 틀렸어요.",
        "byo_key": "또는 내 Claude API 키 붙여 넣기",
        "byo_help": "이 세션의 내 요청에만 사용되고 저장되지 않아요.",
        "left": "남은 브리프: {briefs}  |  남은 포스터: {posters}",
        "lbl_chart": "차트",
        "lbl_song": "노래",
        "own_song": "직접 입력하기",
        "lbl_title": "제목",
        "lbl_artist": "가수",
        "lbl_lyrics": "가사 (한 번만 사용, 저장 안 됨)",
        "btn_brief": "2. 아트 브리프 만들기",
        "btn_reload": "가사 다시 불러오기",
        "btn_poster": "3. 포스터 만들기",
        "lbl_style": "스타일",
        "mood": "분위기",
        "imagery": "이미지",
        "palette": "색상",
        "btn_download": "PNG 내려받기",
        "ai_note": "AI가 만든 이미지예요. 제목과 가수는 나중에 텍스트로 추가했어요.",
        "err_limit_brief": "이번 세션의 브리프를 모두 사용했어요.",
        "err_limit_poster": "이번 세션의 포스터를 모두 사용했어요.",
        "err_style": "이 스타일은 아직 사용할 수 없어요. 다른 스타일을 골라 주세요.",
        "fallback_warn": "이미지 엔진이 실패해서 오프라인 데모 포스터가 나왔어요. ({note})",
        "lyrics_loaded": "{name}에서 가사를 불러왔어요. 수정할 수 있고, 브리프를 만든 뒤에는 지워져요.",
        "lyrics_none": "이 노래의 가사를 찾지 못했어요. 직접 붙여 넣어 주세요.",
        "example_loaded": "예시 가사를 불러왔어요. 데모용으로 만든 가상의 곡이에요.",
        "sensitive": "이 노래에는 민감한 주제가 있어서 포스터에서는 추상적으로 표현해요.",
        "brief_intro": "AI가 세운 포스터 계획이에요. 마음에 드나요? 아래에서 스타일을 고르고 포스터 버튼을 누르세요.",
        "poster_done": "포스터가 완성됐어요! 마음에 안 들면 다른 스타일을 골라 버튼을 다시 누르세요.",
        "spinner_poster": "포스터를 그리는 중이에요… 최대 1분 정도 걸릴 수 있어요.",
        "sidebar_title": "빠른 사용법",
        "hero_sub": "가사를 붙여 넣으면 AI가 작품 아이디어를 짜고, 스타일을 고르면 포스터가 완성돼요. 1분이면 충분해요.",
        "how_title": "어떻게 쓰나요?",
        "steps": [
            ("노래 입력하기", "노래를 고르거나, 제목·가수·가사를 직접 입력하세요."),
            ("아트 브리프 만들기", "AI가 분위기, 색, 이미지를 정리해 줘요. 다음 단계로 가기 전에 읽어볼 수 있어요."),
            ("포스터 만들기", "스타일을 고르고 버튼을 누른 뒤 포스터를 내려받으세요."),
        ],
        "step_labels": ["1 · 노래 입력", "2 · 아트 브리프", "3 · 포스터"],
        "now": "지금 여기",
        "demo_director": "아트 브리프가 가사가 아니라 샘플 아이디어에서 나왔어요.",
        "demo_engine": "그림은 AI 이미지가 아니라 간단하게 만든 풍경이에요.",
        "demo_title": "데모 모드",
        "demo_body": "모든 기능은 작동하지만 결과는 기본 수준이에요. 앱 관리자가 설정에서 실제 AI를 켤 수 있어요.",
        "privacy": "가사는 브리프를 쓸 때 한 번만 사용되고 저장되지 않아요. 포스터에는 제목과 가수만 인쇄돼요.",
        "copyright": "사용해도 되는 가사만 붙여 넣어 주세요. 포스터는 학습과 개인 용도로만 사용하세요.",
        "try_example": "무엇부터 할지 모르겠다면 예시를 눌러 보세요:",
        "example_note": "예시 노래는 데모용으로 만든 가상의 곡이에요.",
        "styles_title": "스타일은 어떤 느낌인가요?",
        "faq_title": "자주 묻는 질문",
        "faq": [
            ("버튼을 눌러도 아무 일도 안 일어나요",
             "제목, 가수, 가사가 모두 채워졌는지 확인하세요. 첫 그림은 최대 1분까지 걸릴 수 있어요."),
            ("포스터가 밋밋해 보여요",
             "데모 모드에서는 그림이 일부러 단순해요. 다른 스타일을 써 보거나 앱 관리자에게 AI 이미지 엔진을 켜 달라고 요청하세요."),
            ("포스터는 어떻게 저장하나요?",
             "포스터 아래의 다운로드 버튼을 누르세요."),
            ("분위기를 바꿀 수 있나요?",
             "네. 다른 스타일을 고르고 포스터 버튼을 다시 누르세요. 스타일마다 전체 분위기가 달라져요."),
        ],
        "tips": {
            "chart": "차트에서 노래를 고르거나, 데모 차트로 앱을 체험해 보세요.",
            "song": "차트에서 노래를 고르거나 '직접 입력하기'를 선택하세요.",
            "title": "노래 제목이에요. 포스터에 인쇄돼요.",
            "artist": "가수 이름이에요. 제목 아래에 인쇄돼요.",
            "lyrics": "여기에 가사를 붙여 넣으세요. 작품 아이디어를 짤 때 한 번만 쓰이고 저장되지 않아요. 포스터에는 인쇄되지 않아요.",
            "brief": "AI가 가사를 읽고 포스터 계획(분위기, 색, 이미지)을 짧게 써 줘요.",
            "style": "포스터의 전체 분위기예요. '스타일은 어떤 느낌인가요?'에서 안내를 볼 수 있어요.",
            "poster": "고른 스타일로 포스터를 만들어요. 최대 1분 정도 걸릴 수 있어요.",
        },
        "need_title": "노래 제목을 입력해 주세요.",
        "need_artist": "가수 이름을 입력해 주세요.",
        "need_lyrics": "가사를 붙여 넣어 주세요.",
        "short_lyrics": "가사가 너무 짧아요. AI가 분위기를 알 수 있도록 몇 줄 더 넣어 주세요.",
        "try_again": "다시 시도해 주세요. 계속 실패하면 앱 관리자에게 알려 주세요.",
        "hint_key": "앱 관리자에게 접근 키를 확인해 달라고 요청하세요.",
        "hint_busy": "무료 이미지 서비스가 바쁘거나 하루 사용량을 넘었을 수 있어요. 몇 분 뒤에 다시 시도하세요.",
        "hint_cut": "다시 시도해 주세요.",
        "hint_declined": "다른 노래로 시도해 보세요.",
    },
}

STYLE_BLURBS_KO = {
    "risograph": "두 가지 잉크를 겹쳐 찍은 인쇄 느낌, 크림색 종이",
    "film_grain": "35mm 필름 사진 느낌, 거친 입자",
    "paper_cut": "겹겹이 쌓은 종이 공예, 부드러운 그림자",
    "neon_noir": "비 오는 밤, 번쩍이는 네온, 깊은 그림자",
    "watercolor": "번지는 물감, 부드러운 종이 질감",
    "bauhaus": "평평한 도형, 엄격한 구성",
    "vaporwave": "파스텔 노을, 격자 수평선, 80년대 꿈 같은 분위기",
    "ukiyo_e": "굵은 윤곽선, 평평한 색, 한지 느낌의 목판화",
    "art_deco": "대칭, 금색 선, 1920년대 화려함",
    "pixel_art": "16비트 게임 장면, 도트 그래픽",
    "blueprint": "파란 바탕에 흰 선, 설계도 느낌",
    "pop_art": "굵은 선, 점 무늬, 강렬한 색",
    "xerox_zine": "복사기로 찍은 펑크 콜라주, 흑백",
    "pastel_dream": "뿌연 부드러운 빛, 은은한 그라데이션",
}

# Made-up songs with original lyrics, so a first-time visitor can see the app work in one click.
EXAMPLES = [
    {
        "label": "Last Train Home",
        "title": "Last Train Home",
        "artist": "The Paper Lanterns (made up)",
        "lyrics": (
            "The platform hums a sleepy tune\n"
            "and the clock forgets to chase the moon.\n"
            "I fold my map into a little boat\n"
            "and let the evening carry it afloat.\n\n"
            "Windows paint the fields in gold,\n"
            "stories none of us were told.\n"
            "One more stop and then we're through,\n"
            "the whole wide night is waiting too."
        ),
    },
    {
        "label": "한강의 밤",
        "title": "한강의 밤",
        "artist": "Demo Band (made up)",
        "lyrics": (
            "강물 위에 별이 내려앉으면\n"
            "우리는 말없이 걸었지\n"
            "가로등이 길게 그려 준 길 위로\n"
            "오늘이 천천히 지나가네\n\n"
            "편의점 불빛 아래 웃음소리\n"
            "식어 가는 커피 한 잔\n"
            "내일은 몰라도 괜찮아\n"
            "이 밤은 우리 것이니까"
        ),
    },
]


# ---------------------------------------------------------------- language and text


def _lang(lang: str | None = None) -> str:
    chosen = lang or st.session_state.get(_LANG_KEY, "en")
    return chosen if chosen in TEXTS else "en"


def t(key: str, lang: str | None = None):
    """Look up a text in the chosen language (falls back to English)."""
    return TEXTS[_lang(lang)].get(key, TEXTS["en"].get(key, key))


def tip(field: str, lang: str | None = None) -> str:
    """Tooltip text for a field, for example st.text_input("Title", help=ui_help.tip("title", lang))."""
    return t("tips", lang).get(field, "")


def language_picker() -> str:
    """Small English / 한국어 switch. Returns the chosen language code."""
    codes = list(LANGS)
    current = _lang()
    choice = st.radio(
        t("language", current), codes, index=codes.index(current), format_func=LANGS.get,
        horizontal=True, key=_LANG_KEY,
    )
    return choice


# ---------------------------------------------------------------- look and feel


def inject_css() -> None:
    """Rounder buttons, a bit more breathing room. Safe to call on every run."""
    st.markdown(
        """
        <style>
        .stButton > button { border-radius: 10px; font-weight: 600; padding: 0.55rem 1.1rem; }
        .stButton > button[kind="primary"] { box-shadow: 0 2px 8px rgba(228, 87, 46, 0.25); }
        .block-container { padding-top: 2.2rem; max-width: 820px; }
        .l2p-step { border-radius: 10px; padding: 0.55rem 0.8rem; background: #F5F2EC; font-size: 0.95rem; }
        .l2p-step.done { background: #E6F4EA; }
        .l2p-step.now { background: #FDE9E2; border: 1.5px solid #E4572E; }
        .l2p-step small { display: block; color: #5b6070; margin-top: 0.15rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------- page pieces


def show_steps(current: int, lang: str | None = None) -> None:
    """Three boxes: done / you are here / still to do.  current is 1, 2 or 3 (3 = poster is ready)."""
    lg = _lang(lang)
    labels, steps = t("step_labels", lg), t("steps", lg)
    cols = st.columns(3)
    for i, col in enumerate(cols, start=1):
        state = "done" if i < current else "now" if i == current else "todo"
        mark = "✅" if state == "done" else "👉" if state == "now" else "⚪"
        hint = f"<small>{steps[i - 1][1]}</small>" if state == "now" else ""
        col.markdown(
            f'<div class="l2p-step {state}">{mark} <b>{labels[i - 1]}</b>{hint}</div>',
            unsafe_allow_html=True,
        )


def intro(lang: str | None = None, expanded: bool = True) -> None:
    """One sentence under the title plus a 'How does this work?' box."""
    lg = _lang(lang)
    st.markdown(t("hero_sub", lg))
    with st.expander(t("how_title", lg), expanded=expanded):
        for i, (name, text) in enumerate(t("steps", lg), start=1):
            st.markdown(f"**{i}. {name}**  \n{text}")
        st.caption(t("privacy", lg))


def mode_notice(director_name: str, engine_name: str, lang: str | None = None) -> None:
    """Explain 'demo' mode in plain words. Shows nothing when the real AI is in use."""
    lg = _lang(lang)
    lines = []
    if director_name == "demo":
        lines.append(t("demo_director", lg))
    if engine_name == "demo":
        lines.append(t("demo_engine", lg))
    if lines:
        st.info(f"**{t('demo_title', lg)}**  \n" + " ".join(lines) + "  \n" + t("demo_body", lg))


def example_buttons(on_pick: Callable[[str, str, str], None], lang: str | None = None) -> None:
    """One button per made-up example. on_pick(title, artist, lyrics) runs BEFORE the page redraws,
    so it can safely set the values of your text boxes in st.session_state."""
    lg = _lang(lang)
    st.caption(t("try_example", lg))
    cols = st.columns(len(EXAMPLES))
    for i, (col, ex) in enumerate(zip(cols, EXAMPLES)):
        col.button(ex["label"], key=f"l2p_example_{i}", on_click=on_pick,
                   args=(ex["title"], ex["artist"], ex["lyrics"]))
    st.caption(t("example_note", lg))


def style_blurb(key: str, lang: str | None = None) -> str:
    """One line describing a style, in the chosen language. Empty if the style is unknown."""
    spec = STYLES.get(key)
    if spec is None:
        return ""
    return STYLE_BLURBS_KO.get(key, spec.blurb) if _lang(lang) == "ko" else spec.blurb


def style_guide(lang: str | None = None) -> None:
    """A short list of what each style looks like. Put it in an expander near the Style box."""
    lg = _lang(lang)
    with st.expander(t("styles_title", lg)):
        left, right = st.columns(2)
        for i, spec in enumerate(STYLES.values()):
            (left if i % 2 == 0 else right).markdown(f"**{spec.label}**  \n{style_blurb(spec.key, lg)}")


_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def swatches(palette: Sequence[str], label: str = "") -> None:
    """Show palette colors as round color chips. Only strict #RRGGBB values are drawn (safe for HTML)."""
    chips = "".join(
        '<span style="display:inline-flex;align-items:center;gap:0.35rem;margin-right:1rem">'
        f'<span style="width:1.3rem;height:1.3rem;border-radius:50%;background:{c};border:1px solid rgba(0,0,0,0.2)"></span>'
        f"<code>{c}</code></span>"
        for c in palette if isinstance(c, str) and _HEX.match(c)
    )
    if chips:
        prefix = f"<b>{label}</b>&nbsp; " if label else ""
        st.markdown(prefix + chips, unsafe_allow_html=True)


def sidebar_help() -> str:
    """Quick guide, FAQ and privacy note in the sidebar. Returns the language code to use elsewhere."""
    with st.sidebar:
        lg = language_picker()
        st.header(t("sidebar_title", lg))
        for i, (name, text) in enumerate(t("steps", lg), start=1):
            st.markdown(f"**{i}. {name}**  \n{text}")
        st.caption(t("privacy", lg))
        st.caption(t("copyright", lg))
        with st.expander(t("faq_title", lg)):
            for question, answer in t("faq", lg):
                st.markdown(f"**{question}**  \n{answer}")
    return lg


# ---------------------------------------------------------------- checks and messages


def check_inputs(title: str, artist: str, lyrics: str, lang: str | None = None) -> list[str]:
    """Friendly problems to show before running the AI. An empty list means 'good to go'."""
    lg = _lang(lang)
    problems = []
    if not (title or "").strip():
        problems.append(t("need_title", lg))
    if not (artist or "").strip():
        problems.append(t("need_artist", lg))
    if not (lyrics or "").strip():
        problems.append(t("need_lyrics", lg))
    elif len(lyrics.strip()) < 40:
        problems.append(t("short_lyrics", lg))
    return problems


def friendly_hint(message: str, lang: str | None = None) -> str:
    """A next step for an error message from the art director or image engine."""
    lg = _lang(lang)
    m = (message or "").lower()
    if "token" in m or "key" in m or "rejected" in m:
        return t("hint_key", lg)
    if "space" in m or "quota" in m or "server" in m or "busy" in m:
        return t("hint_busy", lg)
    if "cut off" in m:
        return t("hint_cut", lg)
    if "declined" in m:
        return t("hint_declined", lg)
    return t("try_again", lg)


def show_error(message: str, lang: str | None = None, hint: bool = True) -> None:
    """Show an error plus what to do next. hint=False for plain input problems like 'type a title'."""
    st.error(message)
    if hint:
        st.caption(friendly_hint(message, lang))
