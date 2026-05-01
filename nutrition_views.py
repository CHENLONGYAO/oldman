"""
Nutrition tracker UI: meal logging, water tracking, daily summary.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from auth import get_session_user
from nutrition import (
    FOOD_LIBRARY, calculate_targets, log_meal, log_water,
    get_today_summary, get_history, get_recovery_tips,
)
from photo_ai import ai_available, analyze_meal_photo, configured_model_name


def _safe_number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_ai_foods(raw_foods, totals=None):
    """Convert model-estimated food totals into per-serving values."""
    totals = totals if isinstance(totals, dict) else {}
    foods = [food for food in (raw_foods or []) if isinstance(food, dict)]
    normalized = []

    for food in foods:
        name = str(food.get("name") or "").strip()
        if not name:
            continue
        servings = max(0.1, _safe_number(food.get("servings"), 1.0))
        macro_totals = {
            "kcal": max(0.0, _safe_number(food.get("kcal"))),
            "protein_g": max(0.0, _safe_number(food.get("protein_g"))),
            "carbs_g": max(0.0, _safe_number(food.get("carbs_g"))),
            "fat_g": max(0.0, _safe_number(food.get("fat_g"))),
        }
        if len(foods) == 1 and not any(macro_totals.values()):
            macro_totals = {
                key: max(0.0, _safe_number(totals.get(key)))
                for key in ("kcal", "protein_g", "carbs_g", "fat_g")
            }
        normalized.append({
            "name": name,
            "servings": servings,
            "kcal": round(macro_totals["kcal"] / servings, 1),
            "protein_g": round(macro_totals["protein_g"] / servings, 1),
            "carbs_g": round(macro_totals["carbs_g"] / servings, 1),
            "fat_g": round(macro_totals["fat_g"] / servings, 1),
            "source": "ai_photo",
        })

    return normalized


def view_nutrition():
    """Nutrition dashboard."""
    user = get_session_user()
    if not user:
        st.error("請先登入")
        return

    lang = st.session_state.get("settings", {}).get("lang", "zh")
    user_id = user["user_id"]
    user_data = st.session_state.get("user", {})

    st.title("🍎 " + ("營養追蹤" if lang == "zh" else "Nutrition Tracker"))

    weight = user_data.get("weight_kg", 60)
    age = user_data.get("age", 30)
    targets = calculate_targets(float(weight), int(age))

    summary = get_today_summary(user_id)
    totals = summary["totals"]

    st.subheader("📊 " + ("今日進度" if lang == "zh" else "Today's Progress"))

    cols = st.columns(4)
    metrics = [
        ("🔥", "卡路里" if lang == "zh" else "Calories",
         totals["kcal"], targets["kcal"], "kcal"),
        ("🍗", "蛋白質" if lang == "zh" else "Protein",
         totals["protein_g"], targets["protein_g"], "g"),
        ("🌾", "碳水" if lang == "zh" else "Carbs",
         totals["carbs_g"], targets["carbs_g"], "g"),
        ("🥑", "脂肪" if lang == "zh" else "Fat",
         totals["fat_g"], targets["fat_g"], "g"),
    ]

    for i, (icon, label, current, target, unit) in enumerate(metrics):
        with cols[i]:
            pct = min(100, (current / target * 100) if target else 0)
            st.metric(f"{icon} {label}", f"{current:.0f}{unit}",
                     delta=f"目標 {target}{unit}" if lang == "zh"
                           else f"target {target}{unit}")
            st.progress(pct / 100)

    st.divider()

    col_water, col_log = st.columns(2)

    with col_water:
        st.subheader("💧 " + ("水分" if lang == "zh" else "Hydration"))
        water_pct = min(100, (summary["water_ml"] / targets["water_ml"]) * 100)
        st.metric(
            "今日攝取" if lang == "zh" else "Today",
            f"{summary['water_ml']} ml",
            delta=f"目標 {targets['water_ml']} ml" if lang == "zh"
                  else f"target {targets['water_ml']}ml",
        )
        st.progress(water_pct / 100)

        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("+250ml", use_container_width=True):
                log_water(user_id, 250)
                st.rerun()
        with c2:
            if st.button("+500ml", use_container_width=True):
                log_water(user_id, 500)
                st.rerun()
        with c3:
            if st.button("+750ml", use_container_width=True):
                log_water(user_id, 750)
                st.rerun()

    with col_log:
        st.subheader("🍽️ " + ("記錄餐點" if lang == "zh" else "Log Meal"))
        meal_type = st.selectbox(
            "餐次" if lang == "zh" else "Meal type",
            ["breakfast", "lunch", "dinner", "snack"],
            format_func=lambda m: {
                "breakfast": "早餐" if lang == "zh" else "Breakfast",
                "lunch": "午餐" if lang == "zh" else "Lunch",
                "dinner": "晚餐" if lang == "zh" else "Dinner",
                "snack": "點心" if lang == "zh" else "Snack",
            }[m],
        )

        with st.expander(
            "📷 拍照辨識餐點" if lang == "zh" else "📷 Scan meal",
            expanded=False,
        ):
            if ai_available():
                st.success(
                    "AI 視覺辨識已啟用" if lang == "zh"
                    else "AI vision is enabled"
                )
                st.caption(f"Model: {configured_model_name()}")
            else:
                st.info(
                    "未設定 ANTHROPIC_API_KEY，仍可拍照後手動選擇食物。"
                    if lang == "zh"
                    else "ANTHROPIC_API_KEY is not set; you can still take a photo and enter foods manually."
                )

            meal_photo = st.camera_input(
                "拍攝餐點照片" if lang == "zh" else "Take a meal photo",
                key="meal_photo_camera",
            )
            meal_upload = st.file_uploader(
                "或上傳餐點照片" if lang == "zh" else "Or upload a meal photo",
                type=["jpg", "jpeg", "png", "webp"],
                key="meal_photo_upload",
            )
            meal_image = meal_photo or meal_upload
            if meal_image and st.button(
                "AI 辨識並建立餐點草稿" if lang == "zh" else "Analyze with AI",
                key="meal_photo_analyze",
                type="primary",
            ):
                result = analyze_meal_photo(
                    meal_image.getvalue(),
                    media_type=getattr(meal_image, "type", "image/jpeg"),
                    lang=lang,
                )
                st.session_state.meal_photo_draft = result.__dict__

            meal_draft = st.session_state.get("meal_photo_draft")
            if meal_draft:
                draft_foods = meal_draft.get("foods") or []
                draft_totals = meal_draft.get("totals") or {}
                st.write("**AI 建議草稿**" if lang == "zh" else "**AI draft**")
                if draft_foods:
                    st.dataframe(
                        pd.DataFrame(draft_foods),
                        hide_index=True,
                        use_container_width=True,
                    )
                if draft_totals:
                    st.caption(
                        f"{draft_totals.get('kcal', 0):.0f} kcal · "
                        f"P {draft_totals.get('protein_g', 0):.0f}g · "
                        f"C {draft_totals.get('carbs_g', 0):.0f}g · "
                        f"F {draft_totals.get('fat_g', 0):.0f}g"
                    )
                for warning in meal_draft.get("warnings") or []:
                    st.warning(warning)

                c_apply, c_clear = st.columns(2)
                with c_apply:
                    if st.button(
                        "套用到餐點" if lang == "zh" else "Apply to meal",
                        key="apply_meal_photo_draft",
                        disabled=not draft_foods,
                        use_container_width=True,
                    ):
                        st.session_state.meal_ai_foods = _normalize_ai_foods(
                            draft_foods,
                            draft_totals,
                        )
                        st.session_state.meal_ai_notes = meal_draft.get("notes", "")
                        st.toast(
                            "已套用，請確認份量後記錄" if lang == "zh"
                            else "Applied. Please review portions before logging.",
                            icon="🍽️",
                        )
                with c_clear:
                    if st.button(
                        "清除草稿" if lang == "zh" else "Clear draft",
                        key="clear_meal_photo_draft",
                        use_container_width=True,
                    ):
                        st.session_state.pop("meal_photo_draft", None)
                        st.session_state.pop("meal_ai_foods", None)
                        st.session_state.pop("meal_ai_notes", None)
                        st.rerun()

        foods = []
        ai_foods = st.session_state.get("meal_ai_foods") or []
        if ai_foods:
            st.markdown("**AI 辨識食物**" if lang == "zh" else "**AI foods**")
            for idx, food in enumerate(ai_foods):
                name = food.get("name", "")
                default_servings = max(0.1, _safe_number(food.get("servings"), 1.0))
                with st.container(border=True):
                    keep = st.checkbox(
                        name,
                        value=True,
                        key=f"meal_ai_keep_{idx}",
                    )
                    servings = st.number_input(
                        "份數" if lang == "zh" else "servings",
                        min_value=0.1,
                        max_value=10.0,
                        value=default_servings,
                        step=0.1,
                        key=f"meal_ai_servings_{idx}",
                    )
                    estimated_kcal = _safe_number(food.get("kcal")) * servings
                    st.caption(
                        f"{estimated_kcal:.0f} kcal"
                        if lang == "zh" else f"{estimated_kcal:.0f} kcal estimated"
                    )
                    if keep:
                        item = dict(food)
                        item["servings"] = servings
                        foods.append(item)
            if st.button(
                "清除 AI 食物" if lang == "zh" else "Clear AI foods",
                key="clear_meal_ai_foods",
            ):
                st.session_state.pop("meal_ai_foods", None)
                st.session_state.pop("meal_ai_notes", None)
                st.rerun()

        food_options = list(FOOD_LIBRARY.keys())
        selected_foods = st.multiselect(
            "手動選擇食物" if lang == "zh" else "Select foods manually",
            options=food_options,
            format_func=lambda f: (
                f if lang == "zh"
                else FOOD_LIBRARY[f]["name_en"]
            ),
        )

        if selected_foods:
            for food in selected_foods:
                servings = st.number_input(
                    f"{food} - {'份數' if lang == 'zh' else 'servings'}",
                    min_value=0.5, max_value=10.0, value=1.0, step=0.5,
                    key=f"servings_{food}",
                )
                foods.append({"name": food, "servings": servings})

        if st.button(
            "💾 " + ("記錄" if lang == "zh" else "Log Meal"),
            type="primary",
            use_container_width=True,
            disabled=not foods,
        ):
            if log_meal(
                user_id,
                meal_type,
                foods,
                notes=st.session_state.get("meal_ai_notes", ""),
            ):
                st.session_state.pop("meal_photo_draft", None)
                st.session_state.pop("meal_ai_foods", None)
                st.session_state.pop("meal_ai_notes", None)
                st.success("✓ " + ("已記錄" if lang == "zh" else "Logged"))
                st.rerun()
            else:
                st.error("失敗" if lang == "zh" else "Failed")

    st.divider()
    st.subheader("📅 " + ("今日餐點" if lang == "zh" else "Today's Meals"))

    if summary["meals"]:
        for meal in summary["meals"]:
            with st.container(border=True):
                st.markdown(f"**{meal['meal_type'].title()}** "
                           f"({meal['totals']['kcal']:.0f} kcal)")
                food_names = [
                    f"{f['name']} ×{f['servings']}"
                    for f in meal.get("foods", [])
                ]
                st.caption(" • ".join(food_names))
                if meal.get("notes"):
                    st.caption(meal["notes"])
    else:
        st.info("今日尚無記錄" if lang == "zh" else "No meals logged today")

    st.divider()
    st.subheader("📈 " + ("週趨勢" if lang == "zh" else "Weekly Trend"))

    history = get_history(user_id, days=7)
    if any(h["kcal"] > 0 for h in history):
        df = pd.DataFrame(history)
        fig = go.Figure()
        fig.add_trace(go.Bar(x=df["date"], y=df["kcal"],
                            name="kcal", marker_color="#74b9ff"))
        fig.add_hline(y=targets["kcal"], line_dash="dash",
                     annotation_text=f"目標 {targets['kcal']}" if lang == "zh"
                                     else f"target {targets['kcal']}")
        fig.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("💡 " + ("復健營養建議" if lang == "zh" else "Recovery Tips"))
    for tip in get_recovery_tips(lang):
        st.markdown(f"- {tip}")
