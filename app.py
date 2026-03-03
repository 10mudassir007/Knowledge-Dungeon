import streamlit as st
import json
import os
import time

from agents import generate_question, check_answer, get_hint, generate_environment

# ---------------------------------------------------------
# Persistence helpers (shared question history – same as CLI)
# ---------------------------------------------------------
HISTORY_PATH = os.path.join("data", "history.json")


def load_history(path: str):
    try:
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_history(path: str, history_list):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history_list, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------
# Game constants
# ---------------------------------------------------------
LEVEL_POINTS = 30
MAX_LEVEL = 3
STARTING_LIVES = 3
POINTS_PER_CORRECT = 10
WIN_POINTS = LEVEL_POINTS * MAX_LEVEL
VERDICT_DISPLAY_SECONDS = 4


def compute_level(points: int) -> int:
    return min(MAX_LEVEL, (points // LEVEL_POINTS) + 1)


# ---------------------------------------------------------
# Session-state helpers
# ---------------------------------------------------------
def _init_state():
    """Initialise all session-state keys on the very first run."""
    defaults = {
        "screen": "entry",       # entry | game | verdict | gameover
        "player_name": "",
        "age": 0,
        "interest": "",
        "lives": STARTING_LIVES,
        "points": 0,
        "level": 1,
        "won": False,
        "environment": "",
        "question": "",
        "correct_answer": "",
        "hint": None,
        "verdict": None,
        "verdict_answer": "",
        "prev_level": 1,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def _sync():
    """Re-derive level, won, game_over from points/lives."""
    st.session_state.level = compute_level(st.session_state.points)
    st.session_state.won = st.session_state.points >= WIN_POINTS
    st.session_state.game_over = st.session_state.lives <= 0


def _fetch_question():
    """Ask LLM for a new question and store it in state."""
    history = load_history(HISTORY_PATH)
    raw = generate_question(
        st.session_state.interest,
        st.session_state.age,
        history,
    )
    parts = raw.split("||", 1)
    if len(parts) != 2:
        st.error("⚠️ Question format error from the model. Try again.")
        return
    q_text = parts[0].strip()
    q_answer = parts[1].strip()
    history.append({"question": q_text, "answer": q_answer})
    save_history(HISTORY_PATH, history)
    st.session_state.question = q_text
    st.session_state.correct_answer = q_answer
    st.session_state.hint = None
    st.session_state.verdict = None


def _fetch_environment():
    """Ask LLM for dungeon flavour text, providing previous-round context."""
    st.session_state.environment = generate_environment(
        st.session_state.interest,
        st.session_state.age,
        st.session_state.level,
        last_verdict=st.session_state.verdict,
        points=st.session_state.points,
        previous_environment=st.session_state.environment or None,
    )


# ---------------------------------------------------------
# Page config
# ---------------------------------------------------------
st.set_page_config(
    page_title="Knowledge Dungeon",
    page_icon="🏰",
    layout="centered",
)

_init_state()


# ---------------------------------------------------------
# Sidebar HUD (shown during game & verdict screens)
# ---------------------------------------------------------
def _render_sidebar():
    with st.sidebar:
        st.title("🏰 Knowledge Dungeon")
        st.divider()

        st.subheader(f"🧙 {st.session_state.player_name}")

        # Lives
        hearts = "❤️ " * st.session_state.lives + "🖤 " * (STARTING_LIVES - st.session_state.lives)
        st.markdown(f"**Lives:** {hearts}")

        # Points & Level
        col1, col2 = st.columns(2)
        col1.metric("⭐ Points", st.session_state.points)
        col2.metric("📊 Level", f"{st.session_state.level} / {MAX_LEVEL}")

        # Progress bar toward next level / win
        progress = st.session_state.points / WIN_POINTS
        st.progress(min(progress, 1.0), text=f"{st.session_state.points} / {WIN_POINTS} pts to win")

        st.divider()
        st.caption(f"Interest: {st.session_state.interest}")


# =========================================================
# SCREEN: ENTRY
# =========================================================
def _render_entry():
    st.title("⚔️ Knowledge Dungeon")
    st.markdown("*Enter the dungeon. Answer to survive.*")
    st.write("")

    with st.form("start_form"):
        name = st.text_input("🧙 Hero Name", placeholder="Enter your name…")
        age = st.number_input("🎂 Age", min_value=1, max_value=120, value=18, step=1)
        interest = st.text_input("💡 Interest", placeholder="e.g. Science, History, Sports…", max_chars=80)
        submitted = st.form_submit_button("⚡ Start Quest", use_container_width=True)

    if submitted and name.strip() and interest.strip():
        with st.spinner("Entering the dungeon…"):
            st.session_state.player_name = name.strip()
            st.session_state.age = int(age)
            st.session_state.interest = interest.strip()
            st.session_state.lives = STARTING_LIVES
            st.session_state.points = 0
            st.session_state.level = 1
            st.session_state.won = False
            st.session_state.prev_level = 1
            _fetch_environment()
            _fetch_question()
            st.session_state.screen = "game"
            st.rerun()


# =========================================================
# SCREEN: GAME
# =========================================================
def _render_game():
    _render_sidebar()

    # Level-up toast
    if st.session_state.level > st.session_state.prev_level:
        st.toast(f"⬆️ Level Up! You are now Level {st.session_state.level}", icon="🎉")
        st.session_state.prev_level = st.session_state.level

    # Environment flavour text
    st.info(f"🏰 {st.session_state.environment}")

    # Question
    st.subheader("❓ Question")
    st.markdown(f"**{st.session_state.question}**")

    st.write("")

    # Hint
    col_hint, _ = st.columns([1, 2])
    with col_hint:
        hint_disabled = st.session_state.hint is not None
        if st.button("💡 Get Hint", disabled=hint_disabled, use_container_width=True):
            with st.spinner("Thinking…"):
                hint_text = get_hint(
                    st.session_state.question,
                    st.session_state.correct_answer,
                    st.session_state.interest,
                )
                st.session_state.hint = hint_text
                st.rerun()

    if st.session_state.hint:
        st.success(f"💡 **Hint:** {st.session_state.hint}")

    # Answer form
    with st.form("answer_form", clear_on_submit=True):
        user_answer = st.text_input("Your answer", placeholder="Type your answer…", label_visibility="collapsed")
        submitted = st.form_submit_button("⚔️ Submit Answer", use_container_width=True)

    if submitted and user_answer.strip():
        with st.spinner("Checking…"):
            verdict_raw = check_answer(
                st.session_state.question,
                st.session_state.correct_answer,
                user_answer.strip(),
            )
            verdict_norm = (verdict_raw or "").strip().lower()

            st.session_state.verdict_answer = st.session_state.correct_answer

            if verdict_norm == "correct":
                st.session_state.points += POINTS_PER_CORRECT
                st.session_state.verdict = "Correct"
            else:
                st.session_state.lives = max(0, st.session_state.lives - 1)
                st.session_state.verdict = "Incorrect"

            _sync()
            st.session_state.screen = "verdict"
            st.rerun()


# =========================================================
# SCREEN: VERDICT (timed splash)
# =========================================================
def _render_verdict():
    _render_sidebar()

    is_correct = (st.session_state.verdict or "").strip().lower() == "correct"

    st.write("")
    st.write("")

    if is_correct:
        st.balloons()
        st.success("## ✅ Correct!", icon="🎉")
    else:
        st.error("## ❌ Incorrect!", icon="💀")
        st.warning(f"The correct answer was: **{st.session_state.verdict_answer}**")

    # Hold the banner for a few seconds, then advance
    time.sleep(VERDICT_DISPLAY_SECONDS)

    if st.session_state.won or st.session_state.lives <= 0:
        st.session_state.screen = "gameover"
    else:
        _fetch_environment()
        _fetch_question()
        st.session_state.verdict = None
        st.session_state.verdict_answer = ""
        st.session_state.screen = "game"

    st.rerun()


# =========================================================
# SCREEN: GAME OVER
# =========================================================
def _render_gameover():
    name = st.session_state.player_name
    won = st.session_state.won

    st.write("")

    if won:
        st.balloons()
        st.title("🏆 Victory!")
        st.markdown(f"Incredible, **{name}**! You conquered the Knowledge Dungeon!")
    else:
        st.snow()
        st.title("💀 Game Over")
        st.markdown(f"The dungeon claims another soul… Better luck next time, **{name}**.")

    st.write("")

    col1, col2 = st.columns(2)
    col1.metric("⭐ Final Points", st.session_state.points)
    col2.metric("📊 Final Level", f"{st.session_state.level} / {MAX_LEVEL}")

    st.write("")
    if st.button("🔄 Play Again", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()


# =========================================================
# Router
# =========================================================
screen = st.session_state.get("screen", "entry")
if screen == "entry":
    _render_entry()
elif screen == "game":
    _render_game()
elif screen == "verdict":
    _render_verdict()
elif screen == "gameover":
    _render_gameover()
