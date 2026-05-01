"""
簡易多語支援（繁體中文 / English）。

使用方式：
    from i18n import t
    st.title(t("app_title", lang))
"""
from __future__ import annotations

LANGS = ("zh", "en")

_TABLE = {
    # 通用
    "app_title": {"zh": "智慧居家復健評估系統", "en": "Smart Home Rehab Assessment"},
    "subtitle":  {"zh": "AI 姿態估計 × DTW × 個人化回饋",
                  "en": "AI pose estimation × DTW × personalized feedback"},
    "welcome_desc": {
        "zh": "結合深度學習 3D 姿態估計（MotionAGFormer）、STGCN/LSTM 動作分析與動態時間扭曲 (DTW)，協助您在家中獨立進行復健訓練並獲得即時、量化、可解釋的專業回饋。",
        "en": "Combining deep-learning 3D pose estimation (MotionAGFormer), STGCN/LSTM action analysis, and Dynamic Time Warping (DTW) to deliver quantitative, interpretable feedback during at-home rehab.",
    },
    "start": {"zh": "開始使用", "en": "Get started"},
    "next": {"zh": "下一步", "en": "Next"},
    "back": {"zh": "返回", "en": "Back"},
    "home": {"zh": "首頁", "en": "Home"},
    "username": {"zh": "用戶名", "en": "Username"},
    "password": {"zh": "密碼", "en": "Password"},

    # 步驟標籤
    "step_welcome": {"zh": "歡迎", "en": "Welcome"},
    "step_profile": {"zh": "基本資料", "en": "Profile"},
    "step_home":    {"zh": "主選單", "en": "Menu"},
    "step_record":  {"zh": "錄影/上傳", "en": "Record"},
    "step_analyze": {"zh": "分析中", "en": "Analyzing"},
    "step_result":  {"zh": "結果", "en": "Result"},
    "step_progress":{"zh": "進度", "en": "Progress"},
    "step_custom":  {"zh": "自訂範本", "en": "Custom template"},
    "step_therapist":{"zh": "治療師", "en": "Therapist"},
    "step_analytics":{"zh": "分析", "en": "Analytics"},
    "step_games":{"zh": "遊戲", "en": "Games"},
    "step_wearables":{"zh": "連接裝置", "en": "Devices"},
    "step_cloud_sync":{"zh": "雲端備份", "en": "Cloud Sync"},
    "step_ai_chat":{"zh": "AI 對話", "en": "AI Chat"},
    "step_quests":{"zh": "任務", "en": "Quests"},
    "step_nutrition":{"zh": "營養", "en": "Nutrition"},
    "step_sleep":{"zh": "睡眠", "en": "Sleep"},
    "step_notifications":{"zh": "通知", "en": "Notifications"},
    "step_audit_log":{"zh": "稽核日誌", "en": "Audit Log"},
    "step_live_enhanced":{"zh": "即時教練 ✨", "en": "Live Coach ✨"},
    "step_auto_exercise":{"zh": "AI 自動分析", "en": "Auto Analysis"},
    "step_daily_routine":{"zh": "今日總覽", "en": "Daily Routine"},
    "step_ai_chat":{"zh": "AI 對話教練", "en": "AI Chat"},
    "step_quests":{"zh": "任務挑戰", "en": "Quests"},
    "step_nutrition":{"zh": "營養追蹤", "en": "Nutrition"},
    "step_sleep":{"zh": "睡眠追蹤", "en": "Sleep"},
    "step_notifications":{"zh": "通知中心", "en": "Notifications"},
    "step_audit_log":{"zh": "稽核紀錄", "en": "Audit Log"},
    "step_clinician":{"zh": "臨床總覽", "en": "Clinician view"},
    "step_ai_media":{"zh": "AI 教練", "en": "AI Coach"},
    "step_settings":{"zh": "設定", "en": "Settings"},

    # 基本資料
    "basic_info":  {"zh": "基本資料", "en": "Profile"},
    "name":   {"zh": "稱呼（用於儲存紀錄）", "en": "Display name (for records)"},
    "age":    {"zh": "年齡", "en": "Age"},
    "gender": {"zh": "性別", "en": "Gender"},
    "female": {"zh": "女", "en": "Female"},
    "male":   {"zh": "男", "en": "Male"},
    "other":  {"zh": "不願透露", "en": "Prefer not to say"},
    "goals":  {"zh": "主要復健目標（可複選）", "en": "Rehab goals (multi-select)"},
    "goal_upper":   {"zh": "上肢活動度", "en": "Upper-limb mobility"},
    "goal_lower":   {"zh": "下肢肌力", "en": "Lower-limb strength"},
    "goal_balance": {"zh": "平衡訓練", "en": "Balance training"},
    "goal_postop":  {"zh": "術後恢復", "en": "Post-op recovery"},
    "goal_general": {"zh": "一般保健", "en": "General wellness"},

    # 首頁/選單
    "choose_exercise": {"zh": "請選擇今日的訓練動作", "en": "Choose today's exercise"},
    "select_this":     {"zh": "選擇此動作", "en": "Select"},
    "view_progress":   {"zh": "查看我的進度", "en": "View my progress"},
    "record_template": {"zh": "錄製自訂範本", "en": "Record custom template"},
    "clinician":       {"zh": "臨床總覽", "en": "Clinician dashboard"},
    "settings":        {"zh": "設定", "en": "Settings"},
    "cue":             {"zh": "重點提醒", "en": "Key cue"},

    # 錄影
    "upload_video":  {"zh": "上傳動作影片（mp4 / mov / avi / mkv）",
                      "en": "Upload video (mp4 / mov / avi / mkv)"},
    "video_hint":    {"zh": "提示：全身入鏡、光線充足、完整執行動作 1 次以上（5-15 秒）。",
                      "en": "Tip: Full body in frame, good lighting, 5-15s clip."},
    "start_analysis":{"zh": "開始分析", "en": "Analyze"},

    # 結果
    "result":        {"zh": "評估結果", "en": "Results"},
    "overall_score": {"zh": "整體分數", "en": "Overall score"},
    "rep_count":     {"zh": "偵測次數", "en": "Reps detected"},
    "suggestions":   {"zh": "個人化建議", "en": "Personalized advice"},
    "joint_detail":  {"zh": "關節詳細分析", "en": "Per-joint analysis"},
    "angle_chart":   {"zh": "主導關節角度曲線（患者 vs 範本）",
                      "en": "Dominant joint angle curve (patient vs template)"},
    "skeleton_overlay": {"zh": "關節偏差視覺化（紅點＝偏差過大）",
                         "en": "Skeleton overlay (red = over threshold)"},
    "export_pdf":    {"zh": "匯出 PDF 報告", "en": "Export PDF"},
    "export_csv":    {"zh": "匯出 CSV 紀錄", "en": "Export CSV"},
    "voice_play":    {"zh": "🔊 朗讀回饋", "en": "🔊 Read feedback"},
    "retry":         {"zh": "再做一次", "en": "Retry"},
    "another":       {"zh": "換個動作", "en": "Another exercise"},

    # 進度
    "progress_title":{"zh": "訓練進度", "en": "Training progress"},
    "trend":         {"zh": "分數趨勢", "en": "Score trend"},
    "history":       {"zh": "歷次紀錄", "en": "Session history"},
    "badges":        {"zh": "成就徽章", "en": "Badges"},
    "streak":        {"zh": "連續訓練日", "en": "Current streak"},
    "no_sessions":   {"zh": "尚無訓練紀錄。", "en": "No sessions yet."},
    "day_unit":      {"zh": "天", "en": "days"},

    # 設定
    "language":      {"zh": "語言", "en": "Language"},
    "threshold":     {"zh": "偏差警示門檻 (°)", "en": "Deviation threshold (°)"},
    "senior_mode":   {"zh": "長者友善評分（65 歲以上自動加成）", "en": "Senior-friendly scoring"},
    "enable_voice":  {"zh": "啟用語音回饋", "en": "Enable voice feedback"},
    "ema_alpha":     {"zh": "關鍵點平滑強度", "en": "Keypoint smoothing (EMA α)"},
    "save":          {"zh": "儲存設定", "en": "Save settings"},

    # 自訂範本
    "custom_desc": {
        "zh": "請錄製專家/治療師示範影片上傳，系統將擷取關節角度作為新範本，日後可重複使用。",
        "en": "Upload a demonstration video; the system extracts joint angles as a reusable template.",
    },
    "template_name": {"zh": "範本名稱", "en": "Template name"},
    "template_desc": {"zh": "動作說明", "en": "Description"},
    "template_cue":  {"zh": "重點提醒", "en": "Key cue"},
    "save_template": {"zh": "儲存範本", "en": "Save template"},
    "template_saved":{"zh": "範本已儲存！", "en": "Template saved!"},

    # 臨床
    "clinician_desc":{"zh": "查看所有使用者的訓練紀錄與進度。",
                      "en": "Overview of all users' training records."},
    "user_count":    {"zh": "使用者總數", "en": "Total users"},
    "session_count": {"zh": "總訓練次數", "en": "Total sessions"},
    "avg_score":     {"zh": "平均分數", "en": "Average score"},

    # 引擎狀態
    "engine_status": {"zh": "模型狀態", "en": "Model status"},

    # 新模組：日記、計畫、疼痛、生命跡象、藥物、行事曆、引導、提醒、同步、AI演示
    "step_onboarding": {"zh": "引導", "en": "Onboarding"},
    "step_programs":   {"zh": "復健計畫", "en": "Programs"},
    "step_journal":    {"zh": "健康日記", "en": "Journal"},
    "step_pain_map":   {"zh": "疼痛地圖", "en": "Pain Map"},
    "step_vitals":     {"zh": "生命跡象", "en": "Vitals"},
    "step_medication": {"zh": "藥物管理", "en": "Medications"},
    "step_calendar":   {"zh": "行事曆", "en": "Calendar"},
    "step_reminders":  {"zh": "智能提醒", "en": "Reminders"},
    "step_ai_demos":   {"zh": "AI 教練", "en": "AI Coach"},
    "step_sync":       {"zh": "多設備同步", "en": "Multi-Device Sync"},

    "today":           {"zh": "今日", "en": "Today"},
    "not_logged_in":   {"zh": "請先登入", "en": "Please log in first"},
    "mood":            {"zh": "心情", "en": "Mood"},
    "energy":          {"zh": "精力", "en": "Energy"},
    "sleep":           {"zh": "睡眠", "en": "Sleep"},
    "weather":         {"zh": "天氣", "en": "Weather"},
    "notes":           {"zh": "備注", "en": "Notes"},

    "program_select":  {"zh": "選擇復健計畫", "en": "Select a Program"},
    "program_start":   {"zh": "開始計畫", "en": "Start Program"},
    "program_progress":{"zh": "計畫進度", "en": "Program Progress"},
    "program_week":    {"zh": "第", "en": "Week"},
    "program_focus":   {"zh": "焦點", "en": "Focus"},
    "program_exercises":{"zh": "動作", "en": "Exercises"},
    "program_end":     {"zh": "結束計畫", "en": "End Program"},

    "pain_record":     {"zh": "記錄疼痛", "en": "Record Pain"},
    "pain_areas":      {"zh": "疼痛區域", "en": "Areas with Pain"},
    "pain_intensity":  {"zh": "疼痛強度", "en": "Pain Intensity"},

    "vitals_record":   {"zh": "記錄生命跡象", "en": "Record Vitals"},
    "bp_systolic":     {"zh": "收縮壓", "en": "Systolic"},
    "bp_diastolic":    {"zh": "舒張壓", "en": "Diastolic"},
    "heart_rate":      {"zh": "心率", "en": "Heart Rate"},
    "spo2":            {"zh": "血氧", "en": "O2 Saturation"},
    "weight":          {"zh": "體重", "en": "Weight"},
    "temperature":     {"zh": "體溫", "en": "Temperature"},

    "medication_today":{"zh": "今日服藥", "en": "Today's Medications"},
    "medication_manage":{"zh": "管理藥物", "en": "Manage Medications"},
    "medication_add":  {"zh": "新增藥物", "en": "Add Medication"},
    "medication_dose": {"zh": "劑量", "en": "Dose"},
    "medication_time": {"zh": "服用時間", "en": "Time"},
    "medication_freq": {"zh": "頻率", "en": "Frequency"},

    "calendar_upcoming":{"zh": "即將到來的預約", "en": "Upcoming Appointments"},
    "calendar_add":    {"zh": "新增預約", "en": "New Appointment"},
    "calendar_type":   {"zh": "預約類型", "en": "Type"},
    "calendar_doctor": {"zh": "醫師", "en": "Doctor"},
    "calendar_location":{"zh": "地點", "en": "Location"},

    # 其它
    "excellent":     {"zh": "動作品質優良，繼續保持！", "en": "Excellent movement quality!"},
    "ok":            {"zh": "動作大致到位，仍有細微調整空間。",
                      "en": "Mostly on track; small refinements possible."},
    "needs_work":    {"zh": "動作幅度或節奏與範本落差較大，建議放慢練習。",
                      "en": "Significant deviation from template; slow down and review."},
    "no_person":     {"zh": "未能偵測到穩定的人體姿態。請確認全身入鏡、光線充足並重新錄影。",
                      "en": "Could not detect a stable body. Ensure full body and good lighting."},
    "disclaimer":    {"zh": "※ 本系統僅供輔助參考，非醫療診斷。若有疼痛請諮詢專業人員。",
                      "en": "※ Advisory only — not a medical diagnosis. Consult a professional for pain."},
}


def t(key: str, lang: str = "zh") -> str:
    entry = _TABLE.get(key)
    if entry is None:
        return key
    return entry.get(lang) or entry.get("zh") or key


def language_label(lang: str) -> str:
    return "繁體中文" if lang == "zh" else "English"
