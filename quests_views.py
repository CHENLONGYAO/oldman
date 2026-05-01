"""
Quest UI: daily/weekly/lifetime missions with claim button.
"""
import streamlit as st

from auth import get_session_user
from quests import get_active_quests, claim_quest, get_quest_xp_total


def view_quests():
    """Quest dashboard."""
    user = get_session_user()
    if not user:
        st.error("請先登入")
        return

    lang = st.session_state.get("settings", {}).get("lang", "zh")
    user_id = user["user_id"]

    st.title("🎯 " + ("任務" if lang == "zh" else "Quests"))

    total_xp = get_quest_xp_total(user_id)
    st.metric(
        "任務累積 XP" if lang == "zh" else "Quest XP Total",
        total_xp,
    )

    quests = get_active_quests(user_id, lang)

    daily = [q for q in quests if q["type"] == "daily"]
    weekly = [q for q in quests if q["type"] == "weekly"]
    one_time = [q for q in quests if q["type"] == "one_time"]

    tabs = st.tabs([
        f"🌅 {'每日' if lang == 'zh' else 'Daily'} ({len(daily)})",
        f"📅 {'週任務' if lang == 'zh' else 'Weekly'} ({len(weekly)})",
        f"🏆 {'成就' if lang == 'zh' else 'Achievements'} ({len(one_time)})",
    ])

    for tab, quest_list in zip(tabs, [daily, weekly, one_time]):
        with tab:
            for quest in quest_list:
                _render_quest_card(quest, user_id, lang)


def _render_quest_card(quest: dict, user_id: str, lang: str) -> None:
    """Render single quest as a card."""
    with st.container(border=True):
        col1, col2 = st.columns([4, 1])

        with col1:
            status_icon = "✅" if quest["completed"] else quest["icon"]
            st.markdown(f"### {status_icon} {quest['name']}")
            st.caption(quest["desc"])

            if not quest["completed"]:
                st.progress(quest["progress_pct"] / 100)
                st.caption(
                    f"{quest['current']}/{quest['goal']} "
                    f"• {'獎勵' if lang == 'zh' else 'Reward'}: "
                    f"+{quest['xp']} XP"
                )
            else:
                st.success(
                    f"✓ {'已完成' if lang == 'zh' else 'Completed'} "
                    f"(+{quest['xp']} XP)"
                )

        with col2:
            if quest["ready_to_claim"]:
                if st.button(
                    "🎁 " + ("領取" if lang == "zh" else "Claim"),
                    key=f"claim_{quest['key']}",
                    type="primary",
                    use_container_width=True,
                ):
                    result = claim_quest(user_id, quest["key"])
                    if result["success"]:
                        st.balloons()
                        st.success(
                            f"+{result['xp_gained']} XP!"
                            + (f" 🏅 {result['badge']}"
                               if result.get("badge") else "")
                        )
                        st.rerun()
                    else:
                        st.error(result.get("error", "Failed"))
            elif not quest["completed"]:
                st.caption(
                    f"{quest['progress_pct']:.0f}%"
                )
