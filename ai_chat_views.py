"""
AI chat coach UI: conversational interface.
"""
import streamlit as st

from auth import get_session_user
from ai_chat import chat, save_chat, get_chat_history


def view_ai_chat():
    """AI conversational coach view."""
    user = get_session_user()
    if not user:
        st.error("請先登入")
        return

    lang = st.session_state.get("settings", {}).get("lang", "zh")
    user_id = user["user_id"]

    st.title("🤖 " + ("AI 教練聊天" if lang == "zh" else "AI Coach Chat"))
    st.caption(
        "問我關於分數、訓練建議、疼痛或動作要領的問題！"
        if lang == "zh" else
        "Ask me about your score, training tips, pain, or form!"
    )

    if "chat_messages" not in st.session_state:
        history = get_chat_history(user_id, limit=10)
        st.session_state.chat_messages = []
        for h in history:
            st.session_state.chat_messages.append(
                {"role": "user", "content": h["message"]}
            )
            st.session_state.chat_messages.append(
                {"role": "assistant", "content": h["reply"]}
            )

    container = st.container(height=400, border=True)
    with container:
        if not st.session_state.chat_messages:
            sample_qs = (
                ["我最近進步如何？", "給我訓練建議", "怎麼緩解疼痛？",
                 "什麼時間訓練最好？"]
                if lang == "zh" else
                ["How am I doing?", "Give me advice", "How to reduce pain?",
                 "Best time to train?"]
            )
            st.markdown(
                "👋 " + ("試著問我：" if lang == "zh" else "Try asking:")
            )
            for q in sample_qs:
                if st.button(f"💭 {q}", key=f"sample_{q}",
                             use_container_width=True):
                    st.session_state.pending_msg = q
                    st.rerun()

        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    pending = st.session_state.pop("pending_msg", None)
    user_input = st.chat_input(
        "輸入訊息..." if lang == "zh" else "Type a message..."
    )

    msg_to_process = pending or user_input
    if msg_to_process:
        st.session_state.chat_messages.append(
            {"role": "user", "content": msg_to_process}
        )

        with st.spinner("思考中..." if lang == "zh" else "Thinking..."):
            result = chat(user_id, msg_to_process, lang)

        st.session_state.chat_messages.append(
            {"role": "assistant", "content": result["reply"]}
        )

        save_chat(user_id, msg_to_process, result["reply"], result["intent"])
        st.rerun()

    if st.session_state.chat_messages:
        if st.button(
            "🗑️ " + ("清除對話" if lang == "zh" else "Clear Chat"),
            use_container_width=False,
        ):
            st.session_state.chat_messages = []
            st.rerun()
