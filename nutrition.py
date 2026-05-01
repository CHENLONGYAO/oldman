"""
Nutrition tracker: meal logging with macros, hydration, and recovery food tips.
"""
from __future__ import annotations
import json
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

from db import execute_query, execute_update


FOOD_LIBRARY = {
    # protein-rich (recovery)
    "雞胸肉": {"name_en": "Chicken breast", "kcal": 165, "protein": 31, "carbs": 0, "fat": 3.6, "tag": "protein"},
    "鮭魚": {"name_en": "Salmon", "kcal": 208, "protein": 20, "carbs": 0, "fat": 13, "tag": "protein"},
    "雞蛋": {"name_en": "Egg", "kcal": 78, "protein": 6, "carbs": 0.6, "fat": 5, "tag": "protein"},
    "豆腐": {"name_en": "Tofu", "kcal": 76, "protein": 8, "carbs": 1.9, "fat": 4.8, "tag": "protein"},
    "希臘優格": {"name_en": "Greek yogurt", "kcal": 100, "protein": 17, "carbs": 6, "fat": 0.7, "tag": "protein"},
    # carbs (energy)
    "糙米": {"name_en": "Brown rice", "kcal": 216, "protein": 5, "carbs": 45, "fat": 1.8, "tag": "carb"},
    "燕麥": {"name_en": "Oatmeal", "kcal": 150, "protein": 5, "carbs": 27, "fat": 3, "tag": "carb"},
    "地瓜": {"name_en": "Sweet potato", "kcal": 103, "protein": 2.3, "carbs": 24, "fat": 0.2, "tag": "carb"},
    "全麥麵包": {"name_en": "Whole wheat bread", "kcal": 80, "protein": 4, "carbs": 14, "fat": 1, "tag": "carb"},
    # fruits/veg
    "香蕉": {"name_en": "Banana", "kcal": 105, "protein": 1.3, "carbs": 27, "fat": 0.4, "tag": "fruit"},
    "藍莓": {"name_en": "Blueberries", "kcal": 84, "protein": 1.1, "carbs": 21, "fat": 0.5, "tag": "fruit"},
    "菠菜": {"name_en": "Spinach", "kcal": 23, "protein": 2.9, "carbs": 3.6, "fat": 0.4, "tag": "veg"},
    "花椰菜": {"name_en": "Broccoli", "kcal": 55, "protein": 3.7, "carbs": 11, "fat": 0.6, "tag": "veg"},
    # fats
    "酪梨": {"name_en": "Avocado", "kcal": 240, "protein": 3, "carbs": 13, "fat": 22, "tag": "fat"},
    "杏仁": {"name_en": "Almonds (28g)", "kcal": 161, "protein": 6, "carbs": 6, "fat": 14, "tag": "fat"},
    "橄欖油": {"name_en": "Olive oil (1 tbsp)", "kcal": 119, "protein": 0, "carbs": 0, "fat": 14, "tag": "fat"},
}


def calculate_targets(weight_kg: float, age: int, activity_level: str = "moderate") -> Dict:
    """Calculate daily nutrition targets based on Mifflin-St Jeor + activity."""
    bmr = 10 * weight_kg + 6.25 * 165 - 5 * age + 5

    activity_mult = {
        "sedentary": 1.2,
        "light": 1.375,
        "moderate": 1.55,
        "active": 1.725,
    }.get(activity_level, 1.55)

    kcal = bmr * activity_mult
    protein_g = weight_kg * 1.6
    carb_g = (kcal * 0.45) / 4
    fat_g = (kcal * 0.30) / 9

    return {
        "kcal": round(kcal),
        "protein_g": round(protein_g),
        "carbs_g": round(carb_g),
        "fat_g": round(fat_g),
        "water_ml": round(weight_kg * 35),
    }


def log_meal(user_id: str, meal_type: str, foods: List[Dict],
             notes: str = "") -> bool:
    """Log a meal with food items.

    foods: list of {"name": str, "servings": float}
    meal_type: breakfast/lunch/dinner/snack
    """
    totals = _calculate_meal_totals(foods)

    payload = {
        "meal_type": meal_type,
        "foods": foods,
        "totals": totals,
        "notes": notes,
        "logged_at": datetime.now().isoformat(),
    }

    try:
        execute_update(
            """
            INSERT INTO offline_cache (user_id, cache_type, data_json, expires_at)
            VALUES (?, ?, ?, datetime('now', '+1 year'))
            """,
            (user_id, f"meal_{date.today().isoformat()}",
             json.dumps(payload, ensure_ascii=False)),
        )
        return True
    except Exception:
        return False


def log_water(user_id: str, ml: int) -> bool:
    """Log water intake."""
    today = date.today().isoformat()
    rows = execute_query(
        """
        SELECT data_json FROM offline_cache
        WHERE user_id = ? AND cache_type = ?
        """,
        (user_id, f"water_{today}"),
    )

    current = 0
    if rows:
        try:
            current = json.loads(rows[0]["data_json"]).get("ml", 0)
        except Exception:
            pass

    new_total = current + ml

    try:
        if rows:
            execute_update(
                """
                UPDATE offline_cache SET data_json = ?
                WHERE user_id = ? AND cache_type = ?
                """,
                (json.dumps({"ml": new_total}), user_id, f"water_{today}"),
            )
        else:
            execute_update(
                """
                INSERT INTO offline_cache (user_id, cache_type, data_json, expires_at)
                VALUES (?, ?, ?, datetime('now', '+90 days'))
                """,
                (user_id, f"water_{today}",
                 json.dumps({"ml": new_total})),
            )
        return True
    except Exception:
        return False


def get_today_summary(user_id: str) -> Dict:
    """Get today's nutrition summary."""
    today = date.today().isoformat()

    meal_rows = execute_query(
        """
        SELECT data_json FROM offline_cache
        WHERE user_id = ? AND cache_type = ?
        ORDER BY created_at ASC
        """,
        (user_id, f"meal_{today}"),
    )

    meals = []
    totals = {"kcal": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0}
    for row in meal_rows:
        try:
            m = json.loads(row["data_json"])
            meals.append(m)
            mt = m.get("totals", {})
            for k in totals:
                totals[k] += mt.get(k, 0)
        except Exception:
            continue

    water_rows = execute_query(
        """
        SELECT data_json FROM offline_cache
        WHERE user_id = ? AND cache_type = ?
        """,
        (user_id, f"water_{today}"),
    )
    water_ml = 0
    if water_rows:
        try:
            water_ml = json.loads(water_rows[0]["data_json"]).get("ml", 0)
        except Exception:
            pass

    return {
        "meals": meals,
        "totals": {k: round(v, 1) for k, v in totals.items()},
        "water_ml": water_ml,
        "meal_count": len(meals),
    }


def get_history(user_id: str, days: int = 7) -> List[Dict]:
    """Get nutrition history for past N days."""
    cutoff_date = date.today() - timedelta(days=days)
    history = []

    for i in range(days):
        d = date.today() - timedelta(days=i)
        d_str = d.isoformat()

        rows = execute_query(
            """
            SELECT data_json FROM offline_cache
            WHERE user_id = ? AND cache_type = ?
            """,
            (user_id, f"meal_{d_str}"),
        )

        day_totals = {"kcal": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0}
        for row in rows:
            try:
                m = json.loads(row["data_json"])
                mt = m.get("totals", {})
                for k in day_totals:
                    day_totals[k] += mt.get(k, 0)
            except Exception:
                continue

        history.append({"date": d_str, **day_totals})

    return list(reversed(history))


def _calculate_meal_totals(foods: List[Dict]) -> Dict:
    """Sum macros from library items or AI-estimated food entries."""
    totals = {"kcal": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0}
    for item in foods:
        name = item.get("name", "")
        servings = max(0, _safe_float(item.get("servings"), 1))
        if any(key in item for key in ("kcal", "protein_g", "carbs_g", "fat_g")):
            totals["kcal"] += _safe_float(item.get("kcal")) * servings
            totals["protein_g"] += _safe_float(item.get("protein_g")) * servings
            totals["carbs_g"] += _safe_float(item.get("carbs_g")) * servings
            totals["fat_g"] += _safe_float(item.get("fat_g")) * servings
            continue

        food_data = FOOD_LIBRARY.get(name)
        if not food_data:
            continue
        totals["kcal"] += food_data["kcal"] * servings
        totals["protein_g"] += food_data["protein"] * servings
        totals["carbs_g"] += food_data["carbs"] * servings
        totals["fat_g"] += food_data["fat"] * servings
    return {k: round(v, 1) for k, v in totals.items()}


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def get_recovery_tips(lang: str = "zh") -> List[str]:
    """Recovery-focused nutrition tips."""
    if lang == "zh":
        return [
            "🥚 訓練後 30 分鐘內補充蛋白質有助肌肉修復",
            "💧 訓練前後各喝 250ml 水",
            "🍌 香蕉、燕麥提供持久能量",
            "🐟 鮭魚的 Omega-3 有抗發炎作用",
            "🥦 綠色蔬菜富含維他命 K，幫助骨骼修復",
            "🥛 鈣質幫助肌肉收縮，每日 1000mg",
        ]
    return [
        "🥚 Eat protein within 30 min post-workout",
        "💧 Drink 250ml water before & after",
        "🍌 Banana, oatmeal for sustained energy",
        "🐟 Salmon Omega-3 reduces inflammation",
        "🥦 Greens have vitamin K for bone repair",
        "🥛 1000mg calcium daily for muscle function",
    ]
