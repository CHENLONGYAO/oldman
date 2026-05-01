"""
Game UI views: game selection, play screens, leaderboards.
"""
import time
import streamlit as st
import pandas as pd

from auth import get_session_user
from games import (
    GAME_REGISTRY, save_game_score,
    reaction_time_start, reaction_time_register_click, reaction_time_score,
    memory_match_init, memory_match_pick, memory_match_score,
    balance_challenge_score,
    rhythm_match_init, rhythm_match_register, rhythm_match_score,
    get_user_total_games, get_user_best_score,
)
from leaderboard import (
    get_global_leaderboard, get_game_leaderboard,
    get_user_rank, get_weekly_challenge_status,
)


def view_games():
    """Main games hub view."""
    user = get_session_user()
    if not user:
        st.error("請先登入")
        return

    lang = st.session_state.get("settings", {}).get("lang", "zh")
    user_id = user["user_id"]

    st.title("🎮 " + ("互動遊戲" if lang == "zh" else "Interactive Games"))

    challenge = get_weekly_challenge_status(user_id)
    with st.container(border=True):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.subheader("🏆 " + ("本週挑戰" if lang == "zh" else "Weekly Challenge"))
            st.progress(challenge["progress_pct"] / 100)
            st.caption(
                f"{challenge['total_score']:.0f} / {challenge['target']} "
                f"{'分' if lang == 'zh' else 'pts'}"
            )
        with col2:
            if challenge["completed"]:
                st.success("✓ " + ("已完成" if lang == "zh" else "Done"))
            else:
                rank = get_user_rank(user_id)
                if rank:
                    st.metric(
                        "排名" if lang == "zh" else "Rank",
                        f"#{rank['rank']}/{rank['total']}",
                    )

    st.divider()

    selected = st.session_state.get("active_game")
    if selected:
        _render_game(selected, user_id, lang)
        return

    st.subheader("🎯 " + ("選擇遊戲" if lang == "zh" else "Choose a Game"))
    user_stats = get_user_total_games(user_id)
    cols = st.columns(2)

    for idx, (key, info) in enumerate(GAME_REGISTRY.items()):
        with cols[idx % 2]:
            with st.container(border=True):
                name = info["name_zh"] if lang == "zh" else info["name_en"]
                desc = info["desc_zh"] if lang == "zh" else info["desc_en"]
                st.markdown(f"### {info['icon']} {name}")
                st.caption(desc)

                stats = user_stats.get(key, {})
                if stats:
                    sc1, sc2 = st.columns(2)
                    with sc1:
                        st.caption(
                            f"{'最高' if lang == 'zh' else 'Best'}: "
                            f"{stats.get('best', 0):.0f}"
                        )
                    with sc2:
                        st.caption(
                            f"{'次數' if lang == 'zh' else 'Plays'}: "
                            f"{stats.get('plays', 0)}"
                        )

                btn_label = "▶️ " + ("開始" if lang == "zh" else "Play")
                if st.button(btn_label, key=f"play_{key}",
                             use_container_width=True, type="primary"):
                    st.session_state.active_game = key
                    st.session_state.game_state = None
                    st.rerun()

    st.divider()
    st.subheader("🏆 " + ("排行榜" if lang == "zh" else "Leaderboard"))

    tab1, tab2 = st.tabs([
        "🌍 " + ("全球本週" if lang == "zh" else "Global Week"),
        "🎯 " + ("各遊戲最高" if lang == "zh" else "Per-Game Best"),
    ])

    with tab1:
        global_lb = get_global_leaderboard(limit=10, days=7)
        if global_lb:
            df = pd.DataFrame([
                {
                    "🏅": _rank_emoji(e["rank"]),
                    "玩家" if lang == "zh" else "Player": e["name"],
                    "總分" if lang == "zh" else "Total": e["total_score"],
                    "次數" if lang == "zh" else "Plays": e["plays"],
                    "最佳" if lang == "zh" else "Best": e["best_score"],
                }
                for e in global_lb
            ])
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("尚無資料" if lang == "zh" else "No data yet")

    with tab2:
        game_choice = st.selectbox(
            "選擇遊戲" if lang == "zh" else "Select game",
            options=list(GAME_REGISTRY.keys()),
            format_func=lambda k: (
                GAME_REGISTRY[k]["name_zh"] if lang == "zh"
                else GAME_REGISTRY[k]["name_en"]
            ),
        )
        game_lb = get_game_leaderboard(game_choice, limit=10)
        if game_lb:
            df = pd.DataFrame([
                {
                    "🏅": _rank_emoji(e["rank"]),
                    "玩家" if lang == "zh" else "Player": e["name"],
                    "最佳" if lang == "zh" else "Best": e["best_score"],
                    "次數" if lang == "zh" else "Plays": e["plays"],
                }
                for e in game_lb
            ])
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("尚無資料" if lang == "zh" else "No data yet")


def _rank_emoji(rank: int) -> str:
    if rank == 1:
        return "🥇"
    if rank == 2:
        return "🥈"
    if rank == 3:
        return "🥉"
    return f"#{rank}"


def _render_game(game_type: str, user_id: str, lang: str) -> None:
    """Render the active game UI."""
    info = GAME_REGISTRY[game_type]
    name = info["name_zh"] if lang == "zh" else info["name_en"]

    col_a, col_b = st.columns([5, 1])
    with col_a:
        st.subheader(f"{info['icon']} {name}")
    with col_b:
        if st.button("← " + ("返回" if lang == "zh" else "Back")):
            st.session_state.active_game = None
            st.session_state.game_state = None
            st.rerun()

    if game_type == "reaction_time":
        _render_reaction_time(user_id, lang)
    elif game_type == "memory_match":
        _render_memory_match(user_id, lang)
    elif game_type == "balance_challenge":
        _render_balance_challenge(user_id, lang)
    elif game_type == "rhythm_match":
        _render_rhythm_match(user_id, lang)


def _render_reaction_time(user_id: str, lang: str) -> None:
    """Render reaction time game."""
    state = st.session_state.get("game_state")

    if state is None:
        st.markdown(
            "點擊開始，當紅色按鈕變綠時立即點擊！" if lang == "zh"
            else "Click start, then tap as soon as the button turns green!"
        )
        if st.button("▶️ " + ("開始" if lang == "zh" else "Start"),
                     type="primary", use_container_width=True):
            st.session_state.game_state = reaction_time_start()
            st.rerun()
        return

    if state.get("completed"):
        rt = state["reaction_ms"]
        score = reaction_time_score(rt)
        st.success(
            f"{'反應時間' if lang == 'zh' else 'Reaction'}: {rt:.0f}ms"
        )
        st.metric(
            "分數" if lang == "zh" else "Score",
            f"{score:.0f}"
        )

        if "saved" not in state:
            save_game_score(user_id, "reaction_time", score, {"reaction_ms": rt})
            state["saved"] = True
            best = get_user_best_score(user_id, "reaction_time")
            if best and score >= best:
                st.balloons()
                st.success("🎉 " + ("新紀錄！" if lang == "zh" else "New record!"))

        if st.button("🔄 " + ("再玩一次" if lang == "zh" else "Play again"),
                     use_container_width=True):
            st.session_state.game_state = None
            st.rerun()
        return

    now = time.time()
    if now < state["stimulus_at"]:
        st.markdown(
            "<div style='font-size:80px;text-align:center;color:#ff3b30'>"
            "🔴</div>",
            unsafe_allow_html=True,
        )
        st.caption("等待...準備好了嗎？" if lang == "zh" else "Wait... get ready!")
        time.sleep(0.1)
        st.rerun()
    else:
        if not state["stimulus_shown"]:
            state["stimulus_shown"] = True
            state["stimulus_at"] = time.time()
            st.session_state.game_state = state

        st.markdown(
            "<div style='font-size:80px;text-align:center;color:#34c759'>"
            "🟢</div>",
            unsafe_allow_html=True,
        )
        if st.button("⚡ " + ("點擊!" if lang == "zh" else "TAP!"),
                     type="primary", use_container_width=True):
            st.session_state.game_state = reaction_time_register_click(state)
            st.rerun()


def _render_memory_match(user_id: str, lang: str) -> None:
    """Render memory match game."""
    state = st.session_state.get("game_state")

    if state is None:
        size = st.radio(
            "難度" if lang == "zh" else "Difficulty",
            [4, 6],
            format_func=lambda s: (
                f"{s}x{s} ({'容易' if s == 4 else '困難'})" if lang == "zh"
                else f"{s}x{s} ({'Easy' if s == 4 else 'Hard'})"
            ),
            horizontal=True,
        )
        if st.button("▶️ " + ("開始" if lang == "zh" else "Start"),
                     type="primary", use_container_width=True):
            st.session_state.game_state = memory_match_init(size)
            st.rerun()
        return

    if state.get("completed"):
        pairs = (state["size"] * state["size"]) // 2
        score = memory_match_score(state["moves"], state["elapsed_s"], pairs)
        st.success(
            f"{'用了' if lang == 'zh' else 'Took'} {state['moves']} "
            f"{'步,' if lang == 'zh' else 'moves,'} "
            f"{state['elapsed_s']:.1f}s"
        )
        st.metric("分數" if lang == "zh" else "Score", f"{score:.0f}")

        if "saved" not in state:
            save_game_score(
                user_id, "memory_match", score,
                {"moves": state["moves"], "elapsed_s": state["elapsed_s"]}
            )
            state["saved"] = True

        if st.button("🔄 " + ("再玩" if lang == "zh" else "Play again"),
                     use_container_width=True):
            st.session_state.game_state = None
            st.rerun()
        return

    pending = state.get("pending_hide")
    if pending:
        time.sleep(0.8)
        new_state = {**state}
        new_state["revealed"] = list(state["revealed"])
        for idx in pending:
            new_state["revealed"][idx] = False
        new_state["pending_hide"] = None
        st.session_state.game_state = new_state
        st.rerun()
        return

    size = state["size"]
    st.caption(
        f"{'步數' if lang == 'zh' else 'Moves'}: {state['moves']}"
    )

    for row in range(size):
        cols = st.columns(size)
        for col in range(size):
            idx = row * size + col
            if state["matched"][idx]:
                cols[col].markdown(
                    f"<div style='font-size:36px;text-align:center;"
                    f"opacity:0.3'>{state['grid'][idx]}</div>",
                    unsafe_allow_html=True,
                )
            elif state["revealed"][idx]:
                cols[col].markdown(
                    f"<div style='font-size:36px;text-align:center'>"
                    f"{state['grid'][idx]}</div>",
                    unsafe_allow_html=True,
                )
            else:
                if cols[col].button("?", key=f"card_{idx}",
                                     use_container_width=True):
                    st.session_state.game_state = memory_match_pick(state, idx)
                    st.rerun()


def _render_balance_challenge(user_id: str, lang: str) -> None:
    """Render balance challenge (simplified - timed hold)."""
    state = st.session_state.get("game_state")

    if state is None:
        st.markdown(
            "保持平衡姿勢 15 秒！" if lang == "zh"
            else "Hold a balance position for 15 seconds!"
        )
        st.markdown(
            "*建議姿勢：單腳站立、腳跟接腳尖、瑜伽樹式*" if lang == "zh"
            else "*Suggested: single-leg stand, heel-to-toe, tree pose*"
        )
        if st.button("▶️ " + ("開始計時" if lang == "zh" else "Start Timer"),
                     type="primary", use_container_width=True):
            st.session_state.game_state = {
                "started_at": time.time(),
                "target": 15,
                "completed": False,
            }
            st.rerun()
        return

    if not state.get("completed"):
        elapsed = time.time() - state["started_at"]
        remaining = max(0, state["target"] - elapsed)
        progress = min(1.0, elapsed / state["target"])

        st.progress(progress)
        st.markdown(
            f"<div style='font-size:60px;text-align:center'>"
            f"{remaining:.1f}s</div>",
            unsafe_allow_html=True,
        )

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("✓ " + ("完成" if lang == "zh" else "Done"),
                         type="primary", use_container_width=True):
                state["completed"] = True
                state["actual_seconds"] = elapsed
                st.session_state.game_state = state
                st.rerun()
        with col_b:
            if st.button("✗ " + ("失敗" if lang == "zh" else "Lost balance"),
                         use_container_width=True):
                state["completed"] = True
                state["actual_seconds"] = elapsed
                state["failed"] = True
                st.session_state.game_state = state
                st.rerun()

        if remaining > 0:
            time.sleep(0.5)
            st.rerun()
    else:
        actual = state.get("actual_seconds", 0)
        score = balance_challenge_score(actual, state["target"])
        st.success(f"{'保持了' if lang == 'zh' else 'Held'} {actual:.1f}s")
        st.metric("分數" if lang == "zh" else "Score", f"{score:.0f}")

        if "saved" not in state:
            save_game_score(
                user_id, "balance_challenge", score,
                {"hold_seconds": actual}
            )
            state["saved"] = True

        if st.button("🔄 " + ("再玩" if lang == "zh" else "Play again"),
                     use_container_width=True):
            st.session_state.game_state = None
            st.rerun()


def _render_rhythm_match(user_id: str, lang: str) -> None:
    """Render rhythm match game."""
    state = st.session_state.get("game_state")

    if state is None:
        st.markdown(
            "依序按下顯示的方向鍵！" if lang == "zh"
            else "Press the direction shown in order!"
        )
        if st.button("▶️ " + ("開始" if lang == "zh" else "Start"),
                     type="primary", use_container_width=True):
            st.session_state.game_state = rhythm_match_init(num_beats=10)
            st.rerun()
        return

    if state.get("completed"):
        score = rhythm_match_score(state["hits"], len(state["sequence"]))
        st.success(
            f"{'命中' if lang == 'zh' else 'Hits'}: "
            f"{state['hits']}/{len(state['sequence'])}"
        )
        st.metric("分數" if lang == "zh" else "Score", f"{score:.0f}")

        if "saved" not in state:
            save_game_score(
                user_id, "rhythm_match", score,
                {"hits": state["hits"], "total": len(state["sequence"])}
            )
            state["saved"] = True

        if st.button("🔄 " + ("再玩" if lang == "zh" else "Play again"),
                     use_container_width=True):
            st.session_state.game_state = None
            st.rerun()
        return

    idx = state["current_idx"]
    expected = state["sequence"][idx]

    progress = idx / len(state["sequence"])
    st.progress(progress)
    st.caption(
        f"{idx+1} / {len(state['sequence'])} | "
        f"{'命中' if lang == 'zh' else 'Hits'}: {state['hits']}"
    )

    st.markdown(
        f"<div style='font-size:120px;text-align:center'>{expected}</div>",
        unsafe_allow_html=True,
    )

    cols = st.columns(4)
    moves = ["⬆️", "⬇️", "⬅️", "➡️"]
    for i, move in enumerate(moves):
        if cols[i].button(move, key=f"move_{i}_{idx}",
                          use_container_width=True):
            st.session_state.game_state = rhythm_match_register(state, move)
            st.rerun()
