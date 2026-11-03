"""Lyric2Poster (open-source edition): chart song -> lyrics -> art brief (Claude) -> poster.

Runs as one Streamlit script, so it deploys to Streamlit Community Cloud straight from GitHub.
Lyrics live only in this browser session: they are cleared right after the art brief is made,
and nothing in this file writes them to disk, a log or a database.

Friendly-page layer (all in lyric2poster/ui_help.py, it only draws help text): step tracker,
how-to box, example songs, field tips, sidebar guide and an English / Korean switch.
"""
from __future__ import annotations

import logging
import random

import streamlit as st

from lyric2poster import ui_help
from lyric2poster.art_director import BriefError, build_art_director
from lyric2poster.charts import load_charts
from lyric2poster.config import load_settings
from lyric2poster.image_engines import EngineError, ImageRequest, build_engine, generate_with_fallback
from lyric2poster.lyrics import build_provider
from lyric2poster.limits import SessionLimiter, owner_key_allowed, passcode_ok
from lyric2poster.overlay import add_title_overlay
from lyric2poster.prompt_builder import build_image_prompt
from lyric2poster.safety import InputError, blocked_reason, clean_label, clean_lyrics, needs_softening
from lyric2poster.schemas import STYLE_PRESETS, ArtBrief
from lyric2poster.styles import STYLES, get_style

log = logging.getLogger("l2p.app")

st.set_page_config(page_title="Lyric2Poster", page_icon="🎨", layout="centered")
ui_help.inject_css()
lang = ui_help.sidebar_help()  # language switch + quick guide + FAQ in the sidebar

OWN_SONG = "Type my own song"  # internal value of the last option in the Song list


def T(key: str, **values) -> str:
    """Text in the chosen language. Extra keyword arguments fill {placeholders}."""
    text = ui_help.t(key, lang)
    return text.format(**values) if values else text


def _secrets():
    try:
        return st.secrets
    except Exception:  # noqa: BLE001 - no secrets file when running locally
        return None


settings = load_settings(secrets=_secrets())
limiter = SessionLimiter(st.session_state, settings.brief_limit, settings.poster_limit)


@st.cache_data(ttl=3600, show_spinner=False)
def _charts(directory: str, url: str) -> list[dict]:
    return load_charts(directory, url)


# ------------------------------------------------------------------ sidebar: keys and limits
with st.sidebar:
    st.divider()
    st.header(T("access_title"))
    st.caption(T("access_caption"))
    if settings.app_passcode:
        code = st.text_input(T("passcode"), type="password", key="passcode_input")
        if code:
            st.session_state["unlocked"] = passcode_ok(code, settings.app_passcode)
            if not st.session_state["unlocked"]:
                st.error(T("wrong_passcode"))
    own_claude = st.text_input(T("byo_key"), type="password", key="byo_claude", help=T("byo_help"))
    st.caption(T("left", briefs=limiter.remaining("briefs"), posters=limiter.remaining("posters")))

unlocked = bool(st.session_state.get("unlocked"))
anthropic_key = own_claude.strip() or (settings.anthropic_api_key if owner_key_allowed(settings, unlocked) else "")
openai_key = settings.openai_api_key if owner_key_allowed(settings, unlocked) else ""
# A key pasted in the sidebar always means Claude, even when no owner key is configured.
llm = "claude" if own_claude.strip() else settings.llm
director = build_art_director(
    llm if (anthropic_key or openai_key) else "demo",
    anthropic_api_key=anthropic_key, openai_api_key=openai_key,
    claude_model=settings.claude_model, openai_model=settings.openai_model,
)
engine = build_engine(settings)

st.title("Lyric2Poster")
st.caption(f"Art director: **{director.name}**  |  Image engine: **{engine.name}**")

step_labels = ui_help.t("step_labels", lang)
steps_slot = st.container()  # filled at the very end, once we know which step the visitor is on
ui_help.intro(lang, expanded=("brief" not in st.session_state))
ui_help.mode_notice(director.name, engine.name, lang)


# ------------------------------------------------------------------ step 1: choose a song
def fill_example(ex_title: str, ex_artist: str, ex_lyrics: str) -> None:
    """Runs before the page redraws, so it may set the values of the boxes below."""
    st.session_state.update(
        song_choice=OWN_SONG, title_input=ex_title, artist_input=ex_artist, lyrics=ex_lyrics,
        _lyrics_for=(clean_label(ex_title), clean_label(ex_artist)),  # stops the lyrics loader overwriting it
        lyrics_note=T("example_loaded"), error="", poster_error="",
    )
    st.session_state.pop("brief", None)
    st.session_state.pop("poster", None)


st.subheader(step_labels[0])
ui_help.example_buttons(fill_example, lang)

charts = _charts(settings.charts_dir, settings.charts_url)
chart = st.selectbox(T("lbl_chart"), charts, format_func=lambda c: c.get("label", c["chart_id"]),
                     help=ui_help.tip("chart", lang))
tracks = chart["tracks"]
labels = [f"{t['rank']}. {t['title']} - {t['artist']}" for t in tracks] + [OWN_SONG]
if st.session_state.get("song_choice") not in labels:  # e.g. after the chart changed
    st.session_state.pop("song_choice", None)
choice = st.selectbox(T("lbl_song"), labels, key="song_choice", help=ui_help.tip("song", lang),
                      format_func=lambda s: T("own_song") if s == OWN_SONG else s)
if choice == OWN_SONG:
    title = st.text_input(T("lbl_title"), max_chars=120, key="title_input", help=ui_help.tip("title", lang))
    artist = st.text_input(T("lbl_artist"), max_chars=120, key="artist_input", help=ui_help.tip("artist", lang))
else:
    picked = tracks[labels.index(choice)]
    title, artist = picked["title"], picked["artist"]
title, artist = clean_label(title), clean_label(artist)


# ------------------------------------------------------------------ step 2: lyrics -> brief
def make_brief() -> None:
    st.session_state["error"] = ""
    st.session_state["error_hint"] = False
    raw = st.session_state.get("lyrics", "")
    try:
        lyrics = clean_lyrics(raw, min_chars=20, max_chars=8000)
    except InputError as exc:
        st.session_state["error"] = str(exc)
        return
    if not title:
        st.session_state["error"] = T("need_title")
        return
    if not artist:
        st.session_state["error"] = T("need_artist")
        return
    if not limiter.take("briefs"):
        st.session_state["error"] = T("err_limit_brief")
        return
    try:
        brief = director.brief(title, artist, lyrics)
    except BriefError as exc:
        st.session_state["error"] = str(exc)
        st.session_state["error_hint"] = True
        return
    finally:
        st.session_state["lyrics"] = ""  # lyrics are never kept after this point
    st.session_state["brief"] = brief.model_dump()
    st.session_state.pop("poster", None)
    st.session_state["poster_error"] = ""
    if brief.style_preset in STYLE_PRESETS:  # start the Style box on the style the art director chose
        st.session_state["style_choice"] = brief.style_preset


def load_lyrics() -> None:
    """Fill the lyrics box for the chosen song. Runs again only when the song changes."""
    provider = build_provider(settings.lyrics_provider)
    st.session_state["_lyrics_for"] = (title, artist)
    st.session_state["lyrics_note"] = ""
    if provider is None or not title or not artist:
        return
    found = provider.fetch(title, artist)
    if found:
        st.session_state["lyrics"] = found
        st.session_state["lyrics_note"] = T("lyrics_loaded", name=provider.name)
    else:
        st.session_state["lyrics_note"] = T("lyrics_none")


if st.session_state.get("_lyrics_for") != (title, artist):
    load_lyrics()

st.text_area(T("lbl_lyrics"), key="lyrics", height=200, max_chars=8000, help=ui_help.tip("lyrics", lang))
if st.session_state.get("lyrics_note"):
    st.caption(st.session_state["lyrics_note"])
if settings.lyrics_provider != "off":
    st.button(T("btn_reload"), on_click=load_lyrics)

st.subheader(step_labels[1])
st.button(T("btn_brief"), on_click=make_brief, type="primary", help=ui_help.tip("brief", lang))
if st.session_state.get("error"):
    ui_help.show_error(st.session_state["error"], lang, hint=bool(st.session_state.get("error_hint")))

# ------------------------------------------------------------------ step 3: review and generate
if "brief" in st.session_state:
    brief = ArtBrief.model_validate(st.session_state["brief"])
    reason = blocked_reason(brief)
    st.write(brief.summary)
    st.caption(f"{T('mood')}: {', '.join(brief.mood)}  |  {T('imagery')}: {', '.join(brief.imagery)}")
    ui_help.swatches(brief.palette, T("palette"))
    if reason:
        st.warning(reason)
    else:
        if needs_softening(brief):
            st.info(T("sensitive"))
        st.subheader(step_labels[2])
        st.caption(T("brief_intro"))
        options = list(STYLE_PRESETS)
        if st.session_state.get("style_choice") not in options:
            st.session_state["style_choice"] = brief.style_preset if brief.style_preset in options else options[0]
        style = st.selectbox(
            T("lbl_style"), options, key="style_choice", help=ui_help.tip("style", lang),
            format_func=lambda k: STYLES[k].label if k in STYLES else k.replace("_", " ").title(),
        )
        st.caption(ui_help.style_blurb(style, lang))
        ui_help.style_guide(lang)

        def make_poster() -> None:
            st.session_state["poster_error"] = ""
            try:
                prompt = build_image_prompt(brief, style)
            except (KeyError, ValueError):
                log.warning("prompt builder does not know style %r", style)
                st.session_state["poster_error"] = T("err_style")
                return
            if not limiter.take("posters"):
                st.session_state["poster_error"] = T("err_limit_poster")
                return
            req = ImageRequest(prompt=prompt, palette=brief.palette, seed=random.randint(0, 2**31 - 1), style=style)
            try:
                result, fell_back, note = generate_with_fallback(engine, req)
            except EngineError as exc:
                st.session_state["poster_error"] = str(exc)
                return
            spec = get_style(style)
            st.session_state["poster"] = {
                "png": add_title_overlay(
                    result.png, title, artist,
                    layout=spec.layout, accent=brief.palette[0] if brief.palette else None, uppercase=spec.uppercase,
                ),
                "engine": result.engine, "model": result.model, "fell_back": fell_back, "note": note,
            }

        if st.button(T("btn_poster"), type="primary", help=ui_help.tip("poster", lang)):
            with st.spinner(T("spinner_poster")):
                make_poster()
            st.rerun()  # redraw so the posters-left counter and the result are up to date
        if st.session_state.get("poster_error"):
            ui_help.show_error(st.session_state["poster_error"], lang)

if "poster" in st.session_state:
    poster = st.session_state["poster"]
    if poster["fell_back"]:
        st.warning(T("fallback_warn", note=poster["note"]))
    st.success(T("poster_done"))
    st.image(poster["png"], caption=f"{poster['engine']} / {poster['model']}")
    st.download_button(T("btn_download"), poster["png"], file_name="poster.png", mime="image/png")
    st.caption(T("ai_note"))

# ------------------------------------------------------------------ step tracker (drawn at the top)
has_inputs = bool(title and artist and str(st.session_state.get("lyrics", "")).strip())
step = 4 if "poster" in st.session_state else 3 if "brief" in st.session_state else 2 if has_inputs else 1
with steps_slot:
    ui_help.show_steps(step, lang)
