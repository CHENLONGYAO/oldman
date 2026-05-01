"""
UI 元件與樣式：
- inject_css        : 全域樣式覆寫（卡片、按鈕、漸層、字體）
- hero / chip       : HTML 區塊元件
- stat_card         : 圖示 + 數值小卡
- streak_card       : 連續訓練日彩色卡
- goal_progress     : 每日目標進度條
- plot_score_trend  : Plotly 趨勢圖（含滾動平均）
- plot_joint_radar  : Plotly 雷達圖
- plot_activity_cal : GitHub 風格活動熱圖
- plot_pain_change  : 訓練前後疼痛變化條形
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from typing import Dict, List, Optional

import streamlit as st
import streamlit.components.v1 as components

try:
    import plotly.graph_objects as go
    PLOTLY_OK = True
except Exception:  # pragma: no cover
    PLOTLY_OK = False


COLORS = {
    "primary": "#007aff",
    "primary_dark": "#005bb5",
    "primary_light": "#e5f1ff",
    "accent": "#ff2d55",
    "warning": "#ffcc00",
    "danger": "#ff3b30",
    "info": "#5ac8fa",
    "bg": "#f2f2f7",
    "card": "rgba(255, 255, 255, 0.75)",
    "text": "#1c1c1e",
    "muted": "#8e8e93",
    "border": "rgba(0, 0, 0, 0.05)",
}


# ============================================================
# 全域 CSS
# ============================================================
_GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=SF+Pro+Display:wght@400;500;600;700;800&display=swap');

/* 主版面 — 軟性漸層背景，模擬 iOS 主畫面層次 */
body, .stApp {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, Helvetica, Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol";
    background:
        radial-gradient(1200px 600px at 0% -10%, rgba(0,122,255,0.06), transparent 60%),
        radial-gradient(1000px 500px at 100% 0%, rgba(90,200,250,0.05), transparent 60%),
        #f2f2f7;
    background-attachment: fixed;
    color: #1c1c1e;
    -webkit-font-smoothing: antialiased;
}

.main .block-container {
    padding-top: 2rem;
    padding-bottom: 4rem;
    max-width: 1200px;
}

/* === 對齊修正：欄位間距、垂直對齊、等高 === */
[data-testid="stHorizontalBlock"] {
    gap: 1rem !important;
    align-items: stretch;
}
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    align-self: stretch;
}
[data-testid="stMetric"] {
    height: 100%;
}
[data-testid="stMetric"] > div {
    align-items: flex-start;
}

/* === 層疊式卡片系統 (像 APP 一樣一層一層的) === */
.app-page {
    display: flex;
    flex-direction: column;
    gap: 1rem;
}
.app-section {
    background: #ffffff;
    border-radius: 22px;
    padding: 1.4rem 1.5rem;
    border: 1px solid rgba(0,0,0,0.05);
    box-shadow:
        0 1px 2px rgba(0,0,0,0.04),
        0 8px 24px rgba(0,0,0,0.05);
    margin-bottom: 1rem;
}
.app-section + .app-section { margin-top: 0; }
.app-section .section-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1rem;
    padding-bottom: 0.7rem;
    border-bottom: 1px solid rgba(0,0,0,0.05);
}
.app-section .section-title {
    font-size: 1.05rem;
    font-weight: 700;
    letter-spacing: -0.01em;
    color: #1c1c1e;
}
.app-section .section-sub {
    font-size: 0.82rem;
    color: #8e8e93;
}

/* Tier 1 — 底層：頁面背景上的群組容器 */
.app-tier-1 {
    background: rgba(255,255,255,0.55);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border-radius: 22px;
    padding: 1.2rem 1.4rem;
    border: 1px solid rgba(0,0,0,0.04);
}

/* Tier 2 — 中層：實心白卡 */
.app-tier-2 {
    background: #ffffff;
    border-radius: 18px;
    padding: 1rem 1.2rem;
    border: 1px solid rgba(0,0,0,0.05);
    box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}

/* Tier 3 — 浮動層：互動區塊（按鈕群、focus row） */
.app-tier-3 {
    background: #ffffff;
    border-radius: 16px;
    padding: 0.85rem 1rem;
    border: 1px solid rgba(0,0,0,0.06);
    box-shadow:
        0 1px 2px rgba(0,0,0,0.04),
        0 8px 20px rgba(0,0,0,0.06);
}

/* APP 風格列表項：左 icon、中 title+sub、右 chevron */
.app-row {
    display: flex;
    align-items: center;
    gap: 0.9rem;
    padding: 0.85rem 1rem;
    background: #ffffff;
    border-radius: 14px;
    border: 1px solid rgba(0,0,0,0.05);
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.app-row:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 16px rgba(0,0,0,0.06);
}
.app-row + .app-row { margin-top: 0.5rem; }
.app-row .row-icon {
    width: 36px; height: 36px;
    border-radius: 10px;
    display: grid; place-items: center;
    background: rgba(0,122,255,0.08);
    color: #007aff;
    font-size: 1.1rem;
    flex-shrink: 0;
}
.app-row .row-body {
    flex: 1;
    min-width: 0;
}
.app-row .row-title {
    font-weight: 600;
    color: #1c1c1e;
    font-size: 0.98rem;
}
.app-row .row-sub {
    font-size: 0.82rem;
    color: #8e8e93;
    margin-top: 0.1rem;
}
.app-row .row-tail {
    color: #c7c7cc;
    font-size: 0.95rem;
    flex-shrink: 0;
}

/* 標題 */
h1, h2, h3, h4, h5, h6 { 
    color: #1c1c1e; 
    font-weight: 700; 
    letter-spacing: -0.02em; 
}
h1 { font-size: 2.2rem !important; }
h2 { font-size: 1.6rem !important; }
h3 { font-size: 1.3rem !important; }

/* 藥丸按鈕 (Pill Buttons) */
.stButton > button, .stDownloadButton > button {
    border-radius: 9999px; /* Pill shape */
    font-weight: 600;
    border: 1px solid rgba(0, 0, 0, 0.05);
    padding: 0.6rem 1.4rem;
    background: #ffffff;
    color: #007aff !important;
    transition: all 0.2s cubic-bezier(0.2, 0.8, 0.2, 1);
    box-shadow: 0 2px 5px rgba(0,0,0,0.02);
}
.stButton > button:hover, .stDownloadButton > button:hover {
    transform: scale(0.98);
    box-shadow: 0 4px 10px rgba(0,0,0,0.06);
    border-color: rgba(0, 0, 0, 0.1);
}
.stButton > button:active, .stDownloadButton > button:active {
    transform: scale(0.95);
    background: #f2f2f7;
}

/* Primary Button */
.stButton > button[kind="primary"] {
    background: #007aff;
    color: white !important;
    border: none;
    box-shadow: 0 4px 12px rgba(0, 122, 255, 0.3);
}
.stButton > button[kind="primary"]:hover {
    background: #005bb5;
    box-shadow: 0 6px 16px rgba(0, 122, 255, 0.4);
}

/* 邊框容器 (APP 段落卡 — 一層的核心元件) */
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 20px !important;
    border: 1px solid rgba(0, 0, 0, 0.05) !important;
    background: #ffffff !important;
    box-shadow:
        0 1px 2px rgba(0,0,0,0.04),
        0 6px 18px rgba(0,0,0,0.05);
    padding: 0.4rem 0.6rem;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}
div[data-testid="stVerticalBlockBorderWrapper"]:hover {
    transform: translateY(-1px);
    box-shadow:
        0 1px 2px rgba(0,0,0,0.04),
        0 12px 28px rgba(0,0,0,0.08);
}
/* 巢狀卡片不疊陰影，避免「卡中卡中卡」看起來髒 */
div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stVerticalBlockBorderWrapper"] {
    background: #f7f8fa !important;
    box-shadow: none !important;
    border: 1px solid rgba(0,0,0,0.05) !important;
}
div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stVerticalBlockBorderWrapper"]:hover {
    transform: none;
    box-shadow: none !important;
}

/* Metric (蘋果風數值小卡) */
[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid rgba(0, 0, 0, 0.05);
    border-radius: 16px;
    padding: 1rem 1.1rem;
    box-shadow:
        0 1px 2px rgba(0,0,0,0.04),
        0 4px 14px rgba(0,0,0,0.04);
    height: 100%;
    transition: transform 0.15s ease, box-shadow 0.2s ease;
}
[data-testid="stMetric"]:hover {
    transform: translateY(-1px);
    box-shadow: 0 1px 2px rgba(0,0,0,0.04), 0 8px 22px rgba(0,0,0,0.07);
}
[data-testid="stMetricValue"] {
    font-size: 1.85rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.03em !important;
    color: #1c1c1e !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.78rem !important;
    color: #8e8e93 !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}
[data-testid="stMetricDelta"] {
    font-size: 0.85rem !important;
    font-weight: 600 !important;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: rgba(242, 242, 247, 0.85);
    backdrop-filter: blur(25px);
    -webkit-backdrop-filter: blur(25px);
    border-right: 1px solid rgba(0,0,0,0.05);
}
[data-testid="stSidebar"] h3 { 
    font-size: 1.1rem; 
    font-weight: 600;
}

/* Tabs (iOS 分段控制) */
.stTabs [data-baseweb="tab-list"] {
    gap: 0;
    background: rgba(118, 118, 128, 0.12);
    border-radius: 10px;
    padding: 3px;
    margin-bottom: 1rem;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    padding: 0.45rem 1.4rem;
    font-weight: 600;
    font-size: 0.92rem;
    color: #3a3a3c !important;
    border: none;
    background: transparent;
    transition: all 0.15s ease;
}
.stTabs [aria-selected="true"] {
    background: #ffffff !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.06), 0 3px 8px rgba(0,0,0,0.08) !important;
    color: #1c1c1e !important;
}
.stTabs [data-baseweb="tab-border"] { display: none; }
.stTabs [data-baseweb="tab-panel"] {
    padding-top: 0.5rem;
}

/* Expander → 半通透卡片 */
[data-testid="stExpander"] {
    border-radius: 18px !important;
    border: 1px solid rgba(0,0,0,0.06) !important;
    background: #ffffff;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04), 0 4px 14px rgba(0,0,0,0.03);
    margin-bottom: 0.75rem;
    overflow: hidden;
}
[data-testid="stExpander"] summary {
    padding: 0.85rem 1.1rem !important;
    font-weight: 600;
    color: #1c1c1e;
}
[data-testid="stExpander"] summary:hover {
    background: rgba(0,122,255,0.04);
}
[data-testid="stExpander"] > details > div {
    padding: 0.5rem 1.1rem 1rem !important;
    border-top: 1px solid rgba(0,0,0,0.05);
}

/* Form → 內容卡片 */
[data-testid="stForm"] {
    background: #ffffff;
    border: 1px solid rgba(0,0,0,0.05);
    border-radius: 18px;
    padding: 1.2rem 1.4rem;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04), 0 6px 18px rgba(0,0,0,0.04);
    margin-bottom: 1rem;
}

/* Alert → 軟卡片 */
[data-testid="stAlert"] {
    border-radius: 14px !important;
    border: 1px solid rgba(0,0,0,0.05) !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.03);
    padding: 0.85rem 1rem !important;
}

/* Divider → 更溫和的視覺分隔 */
[data-testid="stDivider"], hr {
    border: none !important;
    height: 1px !important;
    background: linear-gradient(to right, transparent, rgba(0,0,0,0.08), transparent) !important;
    margin: 1.5rem 0 !important;
}

/* Subheader 變為段落標題 */
.main h2, .main h3 {
    margin-top: 0.5rem !important;
    margin-bottom: 0.6rem !important;
}
.main h3 {
    padding-left: 0.2rem;
    border-left: 3px solid #007aff;
    padding-left: 0.7rem;
}

/* 區段標題助手 (.section-hdr) */
.section-hdr {
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #8e8e93;
    margin: 1.5rem 0 0.7rem 0.2rem;
}

/* app_section() 內部標題 */
.app-section-head {
    margin: -0.2rem -0.2rem 0.7rem;
    padding-bottom: 0.7rem;
    border-bottom: 1px solid rgba(0,0,0,0.05);
}
.app-section-head .app-section-title {
    font-size: 1.05rem;
    font-weight: 700;
    color: #1c1c1e;
    letter-spacing: -0.01em;
}
.app-section-head .app-section-sub {
    font-size: 0.82rem;
    color: #8e8e93;
    margin-top: 0.15rem;
}

/* Progress bar */
.stProgress > div > div > div {
    background-color: #007aff !important;
    border-radius: 9999px;
}

/* Text Inputs / Sliders */
.stTextInput>div>div>input {
    border-radius: 12px;
    border: 1px solid rgba(0,0,0,0.1);
    padding: 0.8rem;
    background: #ffffff;
}
.stTextInput>div>div>input:focus {
    border-color: #007aff;
    box-shadow: 0 0 0 3px rgba(0,122,255,0.2);
}

/* Hide chrome */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header { background: transparent; }

/* === 自訂元件 (Apple Style) === */
.hero {
    background: linear-gradient(120deg, #007aff 0%, #5ac8fa 100%);
    color: white;
    padding: 2.2rem 2.5rem;
    border-radius: 24px;
    margin-bottom: 1.5rem;
    box-shadow: 0 12px 30px rgba(0, 122, 255, 0.25);
    position: relative;
    overflow: hidden;
}
.hero::before {
    content: '';
    position: absolute;
    top: -50%; left: -50%;
    width: 200%; height: 200%;
    background: radial-gradient(circle, rgba(255,255,255,0.2) 0%, transparent 60%);
    pointer-events: none;
}
.hero h1 { color: white !important; margin: 0 0 0.5rem 0; font-weight: 700; letter-spacing: -0.02em; }
.hero p { font-size: 1.15rem; opacity: 0.9; margin: 0; font-weight: 400; }
.hero .badges { margin-top: 1rem; position: relative; z-index: 1;}

.hero-warm {
    background: linear-gradient(120deg, #ff2d55 0%, #ff9500 100%);
    box-shadow: 0 12px 30px rgba(255, 45, 85, 0.25);
}

.stat-card {
    background: rgba(255, 255, 255, 0.8);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    padding: 1.2rem;
    border-radius: 20px;
    border: 1px solid rgba(255, 255, 255, 0.6);
    text-align: center;
    height: 100%;
    box-shadow: 0 8px 24px rgba(0,0,0,0.05);
    transition: transform 0.3s ease;
}
.stat-card:hover { transform: scale(1.02); }
.stat-card .icon { font-size: 2rem; margin-bottom: 0.4rem; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.1)); }
.stat-card .label { font-size: 0.85rem; color: #8e8e93; font-weight: 500; text-transform: uppercase; letter-spacing: 0.05em; }
.stat-card .value { font-size: 1.8rem; font-weight: 700; color: #1c1c1e; letter-spacing: -0.02em; margin: 0.2rem 0; }
.stat-card .delta { font-size: 0.85rem; font-weight: 600; margin-top: 0.3rem; }
.stat-card .delta-up { color: #34c759; }
.stat-card .delta-down { color: #ff3b30; }

.streak-card {
    background: linear-gradient(135deg, #ff9500 0%, #ffcc00 100%);
    color: white;
    padding: 1.5rem;
    border-radius: 20px;
    text-align: center;
    box-shadow: 0 10px 24px rgba(255, 149, 0, 0.3);
    position: relative;
    overflow: hidden;
}
.streak-card::after {
    content: '🔥';
    position: absolute;
    right: -20px; bottom: -30px;
    font-size: 8rem; opacity: 0.15;
    pointer-events: none;
}
.streak-card .flame { font-size: 2.8rem; line-height: 1; filter: drop-shadow(0 4px 6px rgba(0,0,0,0.2)); }
.streak-card .number { font-size: 2.5rem; font-weight: 800; line-height: 1.1; letter-spacing: -0.03em; }
.streak-card .label { font-size: 0.9rem; opacity: 0.9; font-weight: 500; }

.chip {
    display: inline-block;
    padding: 0.3rem 0.8rem;
    border-radius: 9999px;
    font-size: 0.85rem;
    font-weight: 600;
    margin: 0.2rem;
    background: rgba(255, 255, 255, 0.25);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    color: white;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    border: 1px solid rgba(255,255,255,0.2);
}

.badge-tile {
    display: inline-flex;
    flex-direction: column;
    align-items: center;
    padding: 1rem;
    border-radius: 20px;
    background: #ffffff;
    border: 1px solid rgba(0,0,0,0.05);
    margin: 0.4rem;
    min-width: 120px;
    box-shadow: 0 8px 20px rgba(0,0,0,0.04);
    transition: transform 0.2s ease;
}
.badge-tile:hover { transform: translateY(-3px); box-shadow: 0 12px 28px rgba(0,0,0,0.08); }
.badge-tile .b-icon { font-size: 2.2rem; filter: drop-shadow(0 4px 8px rgba(0,0,0,0.1)); }
.badge-tile .b-name { font-weight: 600; font-size: 0.9rem; margin-top: 0.4rem; color: #1c1c1e; }
.badge-tile .b-desc { font-size: 0.75rem; color: #8e8e93; margin-top: 0.2rem; text-align: center;}

.goal-bar {
    background: rgba(255,255,255,0.7);
    backdrop-filter: blur(15px);
    -webkit-backdrop-filter: blur(15px);
    border: 1px solid rgba(255,255,255,0.5);
    border-radius: 18px;
    padding: 1.2rem 1.5rem;
    box-shadow: 0 6px 16px rgba(0,0,0,0.03);
}
.goal-bar .top { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 0.6rem; }
.goal-bar .title { font-weight: 600; color: #1c1c1e; }
.goal-bar .ratio { color: #007aff; font-weight: 700; }
.goal-bar .track { height: 12px; background: rgba(0,0,0,0.05); border-radius: 9999px; overflow: hidden; box-shadow: inset 0 1px 3px rgba(0,0,0,0.05);}
.goal-bar .fill { height: 100%; background: linear-gradient(90deg, #007aff, #5ac8fa); border-radius: 9999px; transition: width 0.6s cubic-bezier(0.2, 0.8, 0.2, 1); }

.recent-user-card {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1rem;
    border-radius: 16px;
    border: 1px solid rgba(0,0,0,0.04);
    background: #ffffff;
    cursor: pointer;
    box-shadow: 0 4px 12px rgba(0,0,0,0.03);
    transition: all 0.2s ease;
}
.recent-user-card:hover { transform: scale(1.02); box-shadow: 0 8px 24px rgba(0,0,0,0.06); }
.recent-user-card .avatar {
    width: 48px; height: 48px;
    border-radius: 50%;
    background: linear-gradient(135deg, #5ac8fa, #007aff);
    display: flex; align-items: center; justify-content: center;
    color: white; font-weight: 700; font-size: 1.3rem;
    box-shadow: 0 4px 10px rgba(0, 122, 255, 0.3);
}
.recent-user-card .info .name { font-weight: 600; color: #1c1c1e; font-size: 1.05rem; }
.recent-user-card .info .meta { font-size: 0.85rem; color: #8e8e93; margin-top: 0.1rem; }

.score-display { text-align: center; padding: 1.5rem; }
.score-display .score-number {
    font-size: 4.5rem; font-weight: 800; line-height: 1; letter-spacing: -0.04em;
    background: linear-gradient(135deg, #007aff, #34c759);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    filter: drop-shadow(0 4px 8px rgba(0,0,0,0.05));
}
.score-display .score-label { color: #8e8e93; font-size: 1rem; margin-top: 0.5rem; font-weight: 500; text-transform: uppercase; letter-spacing: 0.05em; }

.pb-banner {
    background: linear-gradient(135deg, #ffcc00, #ff9500);
    color: white;
    padding: 1rem 1.5rem;
    border-radius: 16px;
    font-weight: 700;
    text-align: center;
    margin-bottom: 1rem;
    box-shadow: 0 8px 20px rgba(255, 149, 0, 0.3);
    font-size: 1.05rem;
}

/* ===== 倒數計時 ===== */
.countdown-wrap {
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 2rem;
}
.countdown-circle {
    width: 200px; height: 200px;
    border-radius: 50%;
    background: linear-gradient(135deg, #007aff, #5ac8fa);
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-size: 6rem;
    font-weight: 800;
    letter-spacing: -0.04em;
    box-shadow: 0 20px 50px rgba(0, 122, 255, 0.4);
    animation: pulse-cd 1s ease-out;
}
.countdown-circle.go {
    background: linear-gradient(135deg, #34c759, #30d158);
    font-size: 4rem;
    box-shadow: 0 20px 50px rgba(52, 199, 89, 0.4);
    animation: bounce-cd 0.5s ease-out;
}
@keyframes pulse-cd {
    0% { transform: scale(0.6); opacity: 0; }
    50% { transform: scale(1.15); opacity: 1; }
    100% { transform: scale(1); opacity: 1; }
}
@keyframes bounce-cd {
    0% { transform: scale(0.6) rotate(-10deg); opacity: 0; }
    60% { transform: scale(1.2) rotate(5deg); opacity: 1; }
    100% { transform: scale(1) rotate(0); opacity: 1; }
}

/* ===== 即時鏡頭狀態卡 ===== */
.live-card {
    background: #ffffff;
    color: #1c1c1e;
    border-radius: 24px;
    padding: 1.4rem 1.6rem;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04), 0 12px 32px rgba(0, 122, 255, 0.10);
    border: 1px solid rgba(0,0,0,0.05);
}
.live-card .top-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
}
.live-card .badge-rec {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.35rem 0.85rem;
    background: rgba(255, 59, 48, 0.10);
    border: 1px solid rgba(255, 59, 48, 0.25);
    border-radius: 999px;
    color: #ff3b30;
    font-size: 0.82rem;
    font-weight: 600;
}
.live-card .badge-rec::before {
    content: '';
    width: 8px; height: 8px;
    background: #ff3b30;
    border-radius: 50%;
    animation: rec-pulse 1.2s infinite;
}
@keyframes rec-pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.35; transform: scale(0.7); }
}
.live-card .timer {
    font-size: 1.1rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    color: #3a3a3c;
}
.live-card .stats-row {
    display: flex;
    gap: 1.5rem;
    flex-wrap: wrap;
    align-items: stretch;
}
.live-card .stat {
    flex: 1;
    min-width: 80px;
    background: #f5f6fa;
    border-radius: 14px;
    padding: 0.65rem 0.8rem;
    border: 1px solid rgba(0,0,0,0.04);
}
.live-card .stat .lbl {
    font-size: 0.72rem;
    color: #8e8e93;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 600;
}
.live-card .stat .val {
    font-size: 1.6rem;
    font-weight: 800;
    letter-spacing: -0.02em;
    color: #1c1c1e;
    margin-top: 0.2rem;
}
.live-card .stat .val.ok { color: #34c759; }
.live-card .stat .val.warn { color: #ff9500; }
.video-call-title {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
    margin-bottom: 0.65rem;
    padding: 0.75rem 1rem;
    border-radius: 18px;
    background: #ffffff;
    color: #1c1c1e;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04), 0 6px 16px rgba(0,0,0,0.06);
    border: 1px solid rgba(0,0,0,0.05);
}
.video-call-title .left {
    display: flex;
    align-items: center;
    gap: 0.65rem;
    font-weight: 800;
}
.video-call-title .dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: #ff3b30;
    box-shadow: 0 0 0 6px rgba(255,59,48,0.14);
    animation: rec-pulse 1.2s infinite;
}
.video-call-title .meta {
    color: #6e6e73;
    font-size: 0.86rem;
    font-weight: 700;
}
.coach-pip-card {
    height: 100%;
    padding: 1rem;
    border-radius: 24px;
    background: #ffffff;
    color: #1c1c1e;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04), 0 12px 32px rgba(0,0,0,0.08);
    border: 1px solid rgba(0,0,0,0.05);
}
.coach-pip-card .pip-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.8rem;
}
.coach-pip-card .pip-label {
    font-size: 0.78rem;
    font-weight: 800;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #8e8e93;
}
.coach-pip-card .pip-live {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    color: #ff3b30;
    font-size: 0.78rem;
    font-weight: 800;
}
.coach-pip-card .pip-live::before {
    content: '';
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #ff3b30;
}
.coach-pip-card .pip-screen {
    display: grid;
    grid-template-columns: 92px 1fr;
    align-items: center;
    gap: 0.9rem;
    border-radius: 20px;
    overflow: hidden;
    background: linear-gradient(135deg, #f5f5f7, #ffffff);
    min-height: 190px;
    padding: 1rem;
}
.coach-pip-card .pip-coach-avatar {
    width: 86px;
    height: 86px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    color: white;
    font-size: 2.7rem;
    font-weight: 900;
    box-shadow: inset 0 -8px 18px rgba(0,0,0,0.14);
}
.coach-pip-card .pip-board {
    border-radius: 18px;
    background: #ffffff;
    color: #1d1d1f;
    padding: 1rem;
    border: 2px solid rgba(0,113,227,0.18);
    box-shadow: 0 10px 24px rgba(0,0,0,0.08);
}
.coach-pip-card .pip-board-k {
    color: #86868b;
    font-size: 0.76rem;
    font-weight: 900;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}
.coach-pip-card .pip-board-v {
    margin-top: 0.3rem;
    font-size: 1.45rem;
    font-weight: 900;
    line-height: 1.15;
}
.coach-pip-card .pip-action {
    margin-top: 0.9rem;
    font-size: 1.35rem;
    font-weight: 900;
    line-height: 1.2;
}
.coach-pip-card .pip-detail {
    margin-top: 0.35rem;
    color: #6e6e73;
    line-height: 1.45;
    font-size: 0.94rem;
}
.coach-pip-card .pip-progress {
    height: 8px;
    border-radius: 999px;
    overflow: hidden;
    background: rgba(0,0,0,0.06);
    margin-top: 0.9rem;
}
.coach-pip-card .pip-progress span {
    display: block;
    height: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, #34c759, #5ac8fa);
}
.coach-pip-card .pip-audio {
    margin-top: 0.85rem;
    padding: 0.65rem 0.75rem;
    border-radius: 16px;
    background: #f5f6fa;
    color: #3a3a3c;
    font-size: 0.88rem;
    font-weight: 700;
    border: 1px solid rgba(0,0,0,0.04);
}

/* ===== 呼吸引導圈 ===== */
.breath-wrap {
    display: flex;
    justify-content: center;
    padding: 1rem;
}
.breath-orb {
    width: 120px; height: 120px;
    border-radius: 50%;
    background: radial-gradient(circle, #5ac8fa 0%, #007aff 70%);
    box-shadow: 0 0 60px rgba(0,122,255,0.4);
    animation: breath 6s ease-in-out infinite;
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-weight: 700;
    font-size: 0.9rem;
}
@keyframes breath {
    0%, 100% { transform: scale(0.7); opacity: 0.7; }
    50% { transform: scale(1.05); opacity: 1; }
}

/* ===== 心情選擇 ===== */
.mood-row {
    display: flex;
    gap: 0.6rem;
    justify-content: space-between;
    flex-wrap: wrap;
}
.mood-pill {
    flex: 1;
    text-align: center;
    padding: 0.7rem 0.4rem;
    border-radius: 14px;
    background: white;
    border: 1px solid rgba(0,0,0,0.06);
    font-size: 1.6rem;
    cursor: pointer;
    transition: all 0.2s;
}
.mood-pill:hover { transform: scale(1.05); }
.mood-pill .lbl {
    display: block;
    font-size: 0.7rem;
    color: #8e8e93;
    margin-top: 0.2rem;
}

/* ===== 每日挑戰卡 ===== */
.challenge-card {
    background: linear-gradient(135deg, #af52de 0%, #ff2d55 100%);
    color: white;
    padding: 1.4rem 1.6rem;
    border-radius: 22px;
    box-shadow: 0 12px 28px rgba(175, 82, 222, 0.3);
    position: relative;
    overflow: hidden;
}
.challenge-card::after {
    content: '✨';
    position: absolute;
    right: 16px; top: 12px;
    font-size: 2.2rem;
    opacity: 0.6;
}
.challenge-card .title-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.4rem;
}
.challenge-card .lbl {
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    background: rgba(255,255,255,0.2);
    padding: 0.2rem 0.6rem;
    border-radius: 999px;
    font-weight: 600;
}
.challenge-card .name {
    font-size: 1.4rem;
    font-weight: 800;
    margin: 0.4rem 0 0.3rem 0;
    letter-spacing: -0.02em;
}
.challenge-card .desc {
    opacity: 0.85;
    font-size: 0.92rem;
}

/* ===== 卡通教練 ===== */
.coach-card {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1rem 1.2rem;
    border-radius: 22px;
    background: linear-gradient(135deg,
        var(--coach-c1, #fdcb6e),
        var(--coach-c2, #e17055));
    color: white;
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.12);
    margin: 0.5rem 0 1rem 0;
    position: relative;
    overflow: hidden;
}
.coach-card::after {
    content: '';
    position: absolute;
    top: -40%; right: -20%;
    width: 280px; height: 280px;
    background: radial-gradient(circle,
        rgba(255,255,255,0.18), transparent 70%);
    pointer-events: none;
}
.coach-avatar {
    width: 68px; height: 68px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.28);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 2px solid rgba(255, 255, 255, 0.45);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 2.6rem;
    flex-shrink: 0;
    animation: coach-bob 3.5s ease-in-out infinite;
    z-index: 1;
}
.coach-avatar-starfish {
    background: transparent;
    border: 0;
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
    filter: drop-shadow(0 10px 18px rgba(140, 20, 70, 0.22));
}
.starfish-core {
    position: relative;
    width: 66px;
    height: 66px;
    display: block;
    background:
        radial-gradient(circle at 38% 38%, #fff3f6 0 5px, transparent 6px),
        radial-gradient(circle at 62% 38%, #fff3f6 0 5px, transparent 6px),
        radial-gradient(circle at 38% 38%, #2f1c2b 0 2px, transparent 3px),
        radial-gradient(circle at 62% 38%, #2f1c2b 0 2px, transparent 3px),
        radial-gradient(circle at 50% 62%, #bb2d63 0 5px, transparent 6px),
        linear-gradient(145deg, #ff9bb8, #ff5d8f);
    clip-path: polygon(
        50% 0%, 61% 31%, 94% 20%, 72% 47%, 96% 74%,
        63% 67%, 50% 100%, 37% 67%, 4% 74%, 28% 47%, 6% 20%, 39% 31%
    );
}
.starfish-core::after {
    content: '';
    position: absolute;
    left: 22px;
    bottom: 9px;
    width: 23px;
    height: 10px;
    border-radius: 10px 10px 4px 4px;
    background: linear-gradient(90deg, #22c7b8, #00a6ff);
    opacity: 0.95;
}
@keyframes coach-bob {
    0%, 100% { transform: translateY(0) rotate(-4deg); }
    50%      { transform: translateY(-6px) rotate(4deg); }
}
.coach-bubble {
    flex: 1;
    background: rgba(255, 255, 255, 0.22);
    border-radius: 18px;
    padding: 0.7rem 1rem;
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 255, 255, 0.32);
    position: relative;
    z-index: 1;
}
.coach-bubble::before {
    content: '';
    position: absolute;
    left: -7px;
    top: 22px;
    width: 14px; height: 14px;
    background: rgba(255, 255, 255, 0.22);
    transform: rotate(45deg);
    border-left: 1px solid rgba(255, 255, 255, 0.32);
    border-bottom: 1px solid rgba(255, 255, 255, 0.32);
}
.coach-name {
    font-weight: 700;
    font-size: 0.85rem;
    margin-bottom: 0.25rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    opacity: 0.95;
}
.coach-msg {
    font-size: 1.05rem;
    line-height: 1.4;
    font-weight: 500;
}

/* ===== Apple 風 cue card（方向提示）===== */
.cue-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 14px;
    margin: 1.2rem 0;
}
.cue-card {
    position: relative;
    background: #ffffff;
    border-radius: 22px;
    padding: 1.4rem 1.2rem 1.2rem 1.2rem;
    box-shadow: 0 8px 24px rgba(0,0,0,0.05);
    border: 1px solid rgba(0,0,0,0.04);
    overflow: hidden;
    transition: transform 0.2s, box-shadow 0.2s;
}
.cue-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 14px 34px rgba(0,0,0,0.08);
}
.cue-card .sev-bar {
    position: absolute;
    left: 0; top: 0; bottom: 0;
    width: 6px;
}
.cue-card.high .sev-bar { background: #ff3b30; }
.cue-card.mid  .sev-bar { background: #ff9500; }

.cue-card .arrow {
    font-size: 3.2rem;
    line-height: 1;
    background: linear-gradient(135deg, #007aff, #5856d6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 0.8rem;
}
.cue-card.high .arrow {
    background: linear-gradient(135deg, #ff3b30, #ff9500);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.cue-card .joint-name {
    font-size: 1.15rem;
    font-weight: 700;
    color: #1c1c1e;
    letter-spacing: -0.01em;
}
.cue-card .verb-action {
    font-size: 1.45rem;
    font-weight: 800;
    color: #1c1c1e;
    letter-spacing: -0.02em;
    margin-top: 0.2rem;
}
.cue-card .delta-num {
    margin-top: 0.8rem;
    font-size: 1rem;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    color: #8e8e93;
}
.cue-card.high .delta-num { color: #ff3b30; }
.cue-card.mid  .delta-num { color: #ff9500; }

/* ===== Apple 巨字 hero（給結果頁與歡迎頁）===== */
.apple-hero {
    text-align: center;
    padding: 3rem 1rem 2rem 1rem;
}
.apple-hero .eyebrow {
    font-size: 0.95rem;
    font-weight: 600;
    color: #8e8e93;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 1rem;
}
.apple-hero .headline {
    font-size: 4.2rem;
    font-weight: 800;
    letter-spacing: -0.04em;
    line-height: 1.05;
    color: #1c1c1e;
    margin: 0 auto 1rem auto;
    max-width: 900px;
}
.apple-hero .sub {
    font-size: 1.3rem;
    color: #6c6c70;
    max-width: 720px;
    margin: 0 auto;
    font-weight: 400;
}

/* ===== 巨型分數（蘋果產品頁式）===== */
.mega-score {
    text-align: center;
    padding: 2rem 1rem 1rem 1rem;
}
.mega-score .num {
    font-size: 7rem;
    font-weight: 800;
    line-height: 1;
    letter-spacing: -0.06em;
    background: linear-gradient(135deg, #007aff, #34c759);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.mega-score.warn .num {
    background: linear-gradient(135deg, #ff9500, #ffcc00);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.mega-score.bad .num {
    background: linear-gradient(135deg, #ff3b30, #ff2d55);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.mega-score .denom {
    font-size: 1.4rem;
    color: #8e8e93;
    font-weight: 500;
    margin-top: 0.4rem;
    letter-spacing: 0.02em;
}
.mega-score .verdict {
    font-size: 1.6rem;
    font-weight: 700;
    color: #1c1c1e;
    margin-top: 1rem;
    letter-spacing: -0.02em;
}

/* 區段分隔（極簡細線 + 標題）*/
.section-eyebrow {
    text-align: center;
    margin: 2.2rem 0 1.2rem 0;
}
.section-eyebrow .label {
    display: inline-block;
    font-size: 0.85rem;
    font-weight: 700;
    color: #8e8e93;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    padding: 0 1rem;
    background: #f2f2f7;
    position: relative;
    z-index: 1;
}
.section-eyebrow::before {
    content: '';
    display: block;
    height: 1px;
    background: rgba(0,0,0,0.08);
    margin-top: 11px;
    position: relative;
    top: -11px;
}

/* ===== 小人示範卡 ===== */
.demo-card {
    background: white;
    border-radius: 24px;
    padding: 1.4rem 1.2rem;
    box-shadow: 0 10px 30px rgba(0,0,0,0.06);
    border: 1px solid rgba(0,0,0,0.04);
    text-align: center;
}
.demo-card .demo-eyebrow {
    font-size: 0.75rem;
    color: #8e8e93;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    font-weight: 700;
    margin-bottom: 0.4rem;
}
.demo-card .demo-name {
    font-size: 1.4rem;
    font-weight: 800;
    color: #1c1c1e;
    letter-spacing: -0.02em;
    margin-bottom: 1rem;
}
.demo-card .demo-svg {
    display: flex;
    justify-content: center;
    margin: 0.4rem 0 1rem 0;
}
.demo-card .demo-cue {
    font-size: 0.95rem;
    color: #6c6c70;
    background: #f2f2f7;
    border-radius: 14px;
    padding: 0.7rem 1rem;
    line-height: 1.5;
}

/* 教練選擇器 */
.coach-pick {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 1rem 0.6rem;
    border-radius: 18px;
    background: white;
    border: 2px solid transparent;
    transition: all 0.2s;
    cursor: pointer;
}
.coach-pick.selected {
    border-color: #007aff;
    background: linear-gradient(180deg,
        rgba(0,122,255,0.06), white 60%);
    box-shadow: 0 8px 22px rgba(0,122,255,0.18);
}
.coach-pick .ava {
    font-size: 2.4rem;
    margin-bottom: 0.4rem;
    height: 44px;
    display: flex;
    align-items: center;
    justify-content: center;
}
.coach-pick .nm {
    font-weight: 700;
    font-size: 0.95rem;
    color: #1c1c1e;
}
.coach-pick .ava .starfish-core {
    width: 44px;
    height: 44px;
}

/* ===== 小助手浮動狀態 ===== */
.assistant-strip {
    display: flex;
    align-items: center;
    gap: 0.9rem;
    margin-top: 1rem;
    padding: 0.85rem 1rem;
    border-radius: 18px;
    background: rgba(255,255,255,0.10);
    border: 1px solid rgba(255,255,255,0.14);
}
.assistant-strip .mini-avatar {
    width: 46px;
    height: 46px;
    display: grid;
    place-items: center;
    flex: 0 0 auto;
    animation: coach-bob 3.2s ease-in-out infinite;
}
.assistant-strip .mini-avatar .starfish-core {
    width: 44px;
    height: 44px;
}
.assistant-strip .mini-title {
    font-size: 0.78rem;
    color: rgba(255,255,255,0.58);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}
.assistant-strip .mini-msg {
    margin-top: 0.15rem;
    color: white;
    font-size: 1rem;
    font-weight: 700;
}
.guide-panel {
    margin-top: 1rem;
    padding: 1rem;
    border-radius: 18px;
    background: rgba(255,255,255,0.10);
    border: 1px solid rgba(255,255,255,0.14);
}
.guide-panel .guide-kicker {
    color: rgba(255,255,255,0.58);
    font-size: 0.75rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 0.45rem;
}
.guide-panel .guide-main {
    display: flex;
    align-items: center;
    gap: 0.8rem;
}
.guide-panel .guide-icon {
    width: 48px;
    height: 48px;
    border-radius: 14px;
    background: rgba(255,255,255,0.16);
    display: grid;
    place-items: center;
    font-size: 2rem;
    flex: 0 0 auto;
}
.guide-panel .guide-action {
    color: white;
    font-size: 1.45rem;
    font-weight: 800;
    letter-spacing: -0.01em;
}
.guide-panel .guide-detail {
    color: rgba(255,255,255,0.72);
    font-size: 0.95rem;
    margin-top: 0.18rem;
    line-height: 1.45;
}
.guide-panel .guide-track {
    height: 8px;
    margin-top: 0.9rem;
    border-radius: 999px;
    overflow: hidden;
    background: rgba(255,255,255,0.12);
}
.guide-panel .guide-fill {
    height: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, #34c759, #5ac8fa);
    transition: width 0.25s ease;
}
.prep-guide-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: 0.8rem;
    margin: 0.9rem 0 1.1rem 0;
}
.prep-guide-card {
    padding: 1rem;
    border-radius: 18px;
    background: #ffffff;
    border: 1px solid rgba(0,0,0,0.05);
    box-shadow: 0 8px 20px rgba(0,0,0,0.04);
}
.prep-guide-card .prep-icon {
    width: 38px;
    height: 38px;
    border-radius: 12px;
    display: grid;
    place-items: center;
    background: rgba(0,122,255,0.10);
    color: #007aff;
    font-size: 1.45rem;
    font-weight: 800;
    margin-bottom: 0.7rem;
}
.prep-guide-card .prep-title {
    font-weight: 800;
    color: #1c1c1e;
    font-size: 1.05rem;
    margin-bottom: 0.35rem;
}
.prep-guide-card .prep-detail {
    color: #6c6c70;
    line-height: 1.45;
    font-size: 0.92rem;
}
.voice-demo-panel {
    height: 100%;
    padding: 1.3rem;
    border-radius: 24px;
    background: #ffffff;
    border: 1px solid rgba(0,0,0,0.05);
    box-shadow: 0 10px 30px rgba(0,0,0,0.06);
}
.voice-demo-panel .kicker {
    color: #8e8e93;
    font-size: 0.78rem;
    font-weight: 800;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin-bottom: 0.45rem;
}
.voice-demo-panel .headline {
    color: #1c1c1e;
    font-size: 1.45rem;
    font-weight: 800;
    line-height: 1.15;
    margin-bottom: 0.75rem;
}
.voice-demo-panel .voice-line {
    display: flex;
    gap: 0.65rem;
    align-items: flex-start;
    padding: 0.85rem 0;
    border-top: 1px solid rgba(0,0,0,0.06);
}
.voice-demo-panel .voice-line:first-of-type {
    border-top: 0;
}
.voice-demo-panel .voice-icon {
    width: 34px;
    height: 34px;
    border-radius: 12px;
    display: grid;
    place-items: center;
    color: #ffffff;
    background: #007aff;
    flex: 0 0 auto;
    font-weight: 800;
}
.voice-demo-panel .voice-title {
    color: #1c1c1e;
    font-weight: 800;
    margin-bottom: 0.18rem;
}
.voice-demo-panel .voice-detail {
    color: #6c6c70;
    line-height: 1.45;
    font-size: 0.94rem;
}
.voice-wave {
    display: inline-flex;
    gap: 3px;
    margin-left: 0.35rem;
    vertical-align: middle;
}
.voice-wave i {
    width: 3px;
    height: 12px;
    border-radius: 999px;
    background: #34c759;
    display: inline-block;
    animation: voice-wave 0.8s ease-in-out infinite;
}
.voice-wave i:nth-child(2) { animation-delay: 0.12s; }
.voice-wave i:nth-child(3) { animation-delay: 0.24s; }
@keyframes voice-wave {
    0%, 100% { transform: scaleY(0.45); opacity: 0.55; }
    50% { transform: scaleY(1.25); opacity: 1; }
}

/* ===== Apple-grade refinement pass ===== */
.stApp {
    background:
      linear-gradient(180deg, #fbfbfd 0%, #f5f5f7 42%, #ffffff 100%);
}
.main .block-container {
    max-width: 1320px;
    padding-left: 2rem;
    padding-right: 2rem;
}
[data-testid="stSidebar"] {
    background: rgba(255,255,255,0.78);
    border-right: 1px solid rgba(0,0,0,0.08);
}
[data-testid="stSidebar"] .stButton > button {
    justify-content: flex-start;
    border-radius: 14px;
    min-height: 42px;
    box-shadow: none;
    color: #1d1d1f !important;
    background: transparent;
    border: 1px solid transparent;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: #1d1d1f;
    color: #ffffff !important;
    box-shadow: 0 8px 22px rgba(0,0,0,0.16);
}
[data-testid="stSidebar"] .stButton > button:disabled {
    opacity: 0.35;
    background: transparent;
}
.hero {
    border-radius: 30px;
    background:
      linear-gradient(135deg, rgba(29,29,31,0.98), rgba(58,58,60,0.94));
    box-shadow: 0 20px 55px rgba(0,0,0,0.18);
}
.hero-warm {
    background:
      linear-gradient(135deg, rgba(0,113,227,0.98), rgba(52,199,89,0.9));
}
div[data-testid="stVerticalBlockBorderWrapper"],
.stat-card,
.goal-bar,
.demo-card,
.voice-demo-panel {
    border-radius: 24px !important;
    background: rgba(255,255,255,0.82) !important;
    border: 1px solid rgba(0,0,0,0.07) !important;
    box-shadow: 0 16px 44px rgba(0,0,0,0.07) !important;
}
.stButton > button, .stDownloadButton > button {
    border-radius: 14px;
    min-height: 42px;
    font-weight: 700;
    box-shadow: none;
}
.session-control {
    display: grid;
    grid-template-columns: minmax(0, 1.5fr) repeat(3, minmax(120px, 0.55fr));
    gap: 0.75rem;
    align-items: stretch;
    margin: 0.8rem 0 1rem 0;
}
.session-control .primary-tile,
.session-control .mini-tile {
    border-radius: 24px;
    padding: 1rem;
    background: rgba(255,255,255,0.86);
    border: 1px solid rgba(0,0,0,0.07);
    box-shadow: 0 14px 38px rgba(0,0,0,0.06);
}
.session-control .primary-tile {
    background: #1d1d1f;
    color: #ffffff;
}
.session-control .eyebrow {
    color: rgba(255,255,255,0.56);
    font-size: 0.78rem;
    font-weight: 800;
    letter-spacing: 0.1em;
    text-transform: uppercase;
}
.session-control .title {
    margin-top: 0.35rem;
    font-size: 1.55rem;
    font-weight: 900;
    line-height: 1.12;
}
.session-control .subtitle {
    margin-top: 0.35rem;
    color: rgba(255,255,255,0.7);
    font-size: 0.95rem;
    line-height: 1.4;
}
.session-control .mini-k {
    color: #86868b;
    font-size: 0.75rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}
.session-control .mini-v {
    margin-top: 0.35rem;
    color: #1d1d1f;
    font-size: 1.05rem;
    font-weight: 900;
}
.session-control .mini-d {
    margin-top: 0.25rem;
    color: #6e6e73;
    font-size: 0.85rem;
    line-height: 1.35;
}
.audio-doctor {
    border-radius: 24px;
    padding: 1rem;
    background: rgba(0,113,227,0.08);
    border: 1px solid rgba(0,113,227,0.18);
    margin: 0.7rem 0 1rem 0;
}
.audio-doctor .title {
    color: #1d1d1f;
    font-weight: 900;
    font-size: 1.05rem;
}
.audio-doctor .detail {
    margin-top: 0.2rem;
    color: #6e6e73;
    line-height: 1.4;
}
.live-clean-panel,
.live-stats-panel,
.today-plan-panel {
    border-radius: 8px;
    background: rgba(255,255,255,0.88);
    border: 1px solid rgba(0,0,0,0.08);
    box-shadow: 0 12px 32px rgba(0,0,0,0.08);
}
.live-clean-panel {
    padding: 1rem;
}
.live-clean-panel .kicker,
.live-stats-panel .kicker,
.today-plan-panel .kicker {
    color: #86868b;
    font-size: 0.74rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}
.live-clean-panel .cue {
    margin-top: 0.45rem;
    color: #1d1d1f;
    font-size: clamp(1.45rem, 3vw, 2.2rem);
    font-weight: 900;
    line-height: 1.08;
}
.live-clean-panel .detail {
    margin-top: 0.45rem;
    color: #6e6e73;
    font-size: 0.95rem;
    line-height: 1.4;
}
.live-clean-panel .bar,
.today-plan-panel .bar {
    height: 7px;
    border-radius: 999px;
    overflow: hidden;
    background: rgba(118,118,128,0.16);
    margin-top: 0.9rem;
}
.live-clean-panel .bar span,
.today-plan-panel .bar span {
    display: block;
    height: 100%;
    border-radius: 999px;
    background: #007aff;
}
.live-clean-panel .voice {
    margin-top: 0.8rem;
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    color: #1d1d1f;
    font-size: 0.86rem;
    font-weight: 700;
}
.live-stats-panel {
    padding: 0.85rem;
    margin-top: 0.75rem;
}
.live-stats-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.55rem;
    margin-top: 0.7rem;
}
.live-stat {
    border-radius: 8px;
    background: rgba(242,242,247,0.78);
    padding: 0.75rem;
}
.live-stat .label {
    color: #86868b;
    font-size: 0.72rem;
    font-weight: 800;
}
.live-stat .value {
    margin-top: 0.2rem;
    color: #1d1d1f;
    font-size: 1.2rem;
    font-weight: 900;
}
.today-plan-panel {
    padding: 1rem;
    margin: 1rem 0;
}
.today-plan-panel .title {
    margin-top: 0.25rem;
    color: #1d1d1f;
    font-size: 1.35rem;
    font-weight: 900;
}
.today-plan-panel .reminder {
    margin-top: 0.4rem;
    color: #6e6e73;
    line-height: 1.4;
}
.today-task {
    border-radius: 8px;
    background: rgba(242,242,247,0.78);
    padding: 0.8rem;
    margin-top: 0.65rem;
    border: 1px solid rgba(0,0,0,0.04);
}
.today-task .name {
    color: #1d1d1f;
    font-weight: 900;
}
.today-task .desc {
    margin-top: 0.2rem;
    color: #6e6e73;
    font-size: 0.9rem;
    line-height: 1.35;
}
.today-task.done {
    opacity: 0.68;
}
@media (max-width: 900px) {
    .session-control {
        grid-template-columns: 1fr;
    }
    .live-stats-grid {
        grid-template-columns: repeat(4, minmax(0, 1fr));
    }
    .main .block-container {
        padding-left: 1rem;
        padding-right: 1rem;
    }
    .ios-card {
      background: white;
      border-radius: 18px;
      padding: 18px 20px;
      box-shadow: 0 2px 12px rgba(0,0,0,0.08);
      margin-bottom: 14px;
    }
    .ios-section-title {
      font-size: 22px;
      font-weight: 700;
      color: #1c1c1e;
      letter-spacing: -0.5px;
      margin: 24px 0 10px;
    }
    .ios-label {
      font-size: 13px;
      font-weight: 600;
      color: #8e8e93;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .activity-rings-container {
      display: flex;
      align-items: center;
      gap: 24px;
      margin: 20px 0;
      padding: 20px;
      background: white;
      border-radius: 18px;
      box-shadow: 0 2px 12px rgba(0,0,0,0.08);
    }
    .activity-rings-svg {
      flex-shrink: 0;
    }
    .activity-rings-stats {
      flex: 1;
    }
    .activity-rings-stat {
      margin: 8px 0;
      font-size: 14px;
      color: #666;
    }
    .level-badge-container {
      background: linear-gradient(135deg, #007aff 0%, #0051d5 100%);
      color: white;
      border-radius: 18px;
      padding: 16px;
      margin: 12px 0;
      box-shadow: 0 4px 12px rgba(0,113,227,0.3);
    }
    .level-badge-text {
      font-size: 18px;
      font-weight: 700;
      margin-bottom: 8px;
    }
    .xp-progress {
      background: rgba(255,255,255,0.2);
      border-radius: 10px;
      height: 8px;
      overflow: hidden;
      margin-top: 8px;
    }
    .xp-progress-bar {
      height: 100%;
      background: #34C759;
      transition: width 0.3s ease;
    }
}
</style>
"""


from contextlib import contextmanager


@contextmanager
def app_section(title: str = "", subtitle: str = "", *, icon: str = ""):
    """Render content inside an iOS-style layered card with optional header.

    Usage:
        with ui.app_section("今日訓練", "已完成 3 次", icon="🏃"):
            st.metric(...)
    """
    container = st.container(border=True)
    with container:
        if title:
            st.markdown(
                f'<div class="app-section-head">'
                f'<div class="app-section-title">'
                f'{(icon + " ") if icon else ""}{escape(title)}'
                f'</div>'
                + (f'<div class="app-section-sub">{escape(subtitle)}</div>'
                   if subtitle else "")
                + '</div>',
                unsafe_allow_html=True,
            )
        yield


def section_header(title: str, *, icon: str = "") -> None:
    """Render a section eyebrow header."""
    st.markdown(
        f'<div class="section-hdr">{(icon + " ") if icon else ""}'
        f'{escape(title)}</div>',
        unsafe_allow_html=True,
    )


def inject_css() -> None:
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)
    pwa_script = (
        "<script>"
        "(function(){"
        "if(document.querySelector('link[rel=\"manifest\"]'))return;"
        "var l=document.createElement('link');"
        "l.rel='manifest';l.href='/app/static/manifest.json';"
        "document.head.appendChild(l);"
        "var tc=document.createElement('meta');"
        "tc.name='theme-color';tc.content='#007aff';"
        "document.head.appendChild(tc);"
        "var am=document.createElement('meta');"
        "am.name='apple-mobile-web-app-capable';am.content='yes';"
        "document.head.appendChild(am);"
        "var at=document.createElement('meta');"
        "at.name='apple-mobile-web-app-title';at.content='SmartRehab';"
        "document.head.appendChild(at);"
        "})();"
        "</script>"
    )
    st.markdown(pwa_script, unsafe_allow_html=True)


# ============================================================
# HTML 元件
# ============================================================
def hero(title: str, subtitle: str = "", chips: Optional[List[str]] = None,
         variant: str = "primary") -> None:
    cls = "hero hero-warm" if variant == "warm" else "hero"
    chip_html = ""
    if chips:
        chip_html = '<div class="badges">' + "".join(
            f'<span class="chip">{c}</span>' for c in chips
        ) + "</div>"
    st.markdown(
        f'<div class="{cls}"><h1>{title}</h1>'
        f'<p>{subtitle}</p>{chip_html}</div>',
        unsafe_allow_html=True,
    )


def stat_card(icon: str, label: str, value: str,
              delta: Optional[str] = None, delta_up: bool = True) -> None:
    delta_html = ""
    if delta:
        cls = "delta-up" if delta_up else "delta-down"
        arrow = "▲" if delta_up else "▼"
        delta_html = f'<div class="delta {cls}">{arrow} {delta}</div>'
    st.markdown(
        f'<div class="stat-card">'
        f'<div class="icon">{icon}</div>'
        f'<div class="value">{value}</div>'
        f'<div class="label">{label}</div>'
        f'{delta_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def streak_card(streak: int, label: str = "連續訓練天數") -> None:
    st.markdown(
        f'<div class="streak-card">'
        f'<div class="flame">🔥</div>'
        f'<div class="number">{streak}</div>'
        f'<div class="label">{label}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def goal_progress(current: int, goal: int, label: str) -> None:
    ratio = min(1.0, current / goal) if goal else 0.0
    pct = int(ratio * 100)
    st.markdown(
        f'<div class="goal-bar">'
        f'<div class="top">'
        f'<div class="title">{label}</div>'
        f'<div class="ratio">{current} / {goal} ({pct}%)</div>'
        f'</div>'
        f'<div class="track">'
        f'<div class="fill" style="width:{pct}%"></div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def big_score(score: float, label: str = "整體分數") -> None:
    st.markdown(
        f'<div class="score-display">'
        f'<div class="score-number">{score:.1f}</div>'
        f'<div class="score-label">{label}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def pb_banner(text: str) -> None:
    st.markdown(
        f'<div class="pb-banner">🏆 {text}</div>',
        unsafe_allow_html=True,
    )


# ============================================================
# 新元件：倒數、即時卡、心情、呼吸、五彩確彈、每日挑戰
# ============================================================
def countdown(seconds: int = 3, placeholder=None,
              go_text: str = "GO!") -> None:
    """阻塞式倒數計時動畫（適合在進入即時鏡頭前使用）。"""
    import time as _time
    holder = placeholder if placeholder is not None else st.empty()
    for i in range(seconds, 0, -1):
        holder.markdown(
            f'<div class="countdown-wrap">'
            f'<div class="countdown-circle">{i}</div></div>',
            unsafe_allow_html=True,
        )
        _time.sleep(1)
    holder.markdown(
        f'<div class="countdown-wrap">'
        f'<div class="countdown-circle go">{go_text}</div></div>',
        unsafe_allow_html=True,
    )
    _time.sleep(0.7)
    holder.empty()


def live_status_card(
    elapsed_s: float,
    score: float,
    phase: int,
    phase_total: int,
    fps: float,
    msgs: List[str] | None = None,
    guide: dict | None = None,
    character_key: str | None = None,
    voice_enabled: bool = False,
    lang: str = "zh",
) -> None:
    """即時鏡頭下方的 iOS 風暗色狀態卡。"""
    import coach as coach_mod
    mm = int(elapsed_s) // 60
    ss = int(elapsed_s) % 60
    score_cls = "ok" if score >= 80 else ("warn" if score >= 60 else "")
    char = coach_mod.get_character(character_key)
    name = char["name_zh"] if lang == "zh" else char["name_en"]
    avatar = _coach_avatar_html(char, mini=True)
    if msgs:
        assistant_msg = msgs[0]
    else:
        assistant_msg = (
            guide.get("voice", "動作很好，保持節奏。") if guide else "動作很好，保持節奏。"
            if lang == "zh" else "Good form. Keep the rhythm."
        )
    voice_html = (
        '<span class="voice-wave"><i></i><i></i><i></i></span>'
        if voice_enabled else ""
    )
    msg_html = ""
    if msgs:
        items = "".join(
            f'<div style="padding:.4rem 0;color:#ff453a;'
            f'font-weight:600;">• {m}</div>'
            for m in msgs[:3]
        )
        msg_html = (
            '<div style="margin-top:.8rem;'
            'border-top:1px solid rgba(255,255,255,.1);'
            'padding-top:.8rem;font-size:.95rem;">' + items + '</div>'
        )
    guide_html = ""
    if guide:
        pct = int(guide.get("percent", 0))
        guide_html = (
            '<div class="guide-panel">'
            f'<div class="guide-kicker">{"動作指導" if lang == "zh" else "Motion guide"}</div>'
            '<div class="guide-main">'
            f'<div class="guide-icon">{guide.get("icon", "•")}</div>'
            '<div>'
            f'<div class="guide-action">{guide.get("action", "")}</div>'
            f'<div class="guide-detail">{guide.get("detail", "")}</div>'
            '</div></div>'
            '<div class="guide-track">'
            f'<div class="guide-fill" style="width:{pct}%"></div>'
            '</div></div>'
        )
    st.markdown(
        f'<div class="live-card">'
        f'<div class="top-row">'
        f'<span class="badge-rec">LIVE 鏡頭指導</span>'
        f'<span class="timer">{mm:02d}:{ss:02d}</span>'
        f'</div>'
        f'<div class="stats-row">'
        f'<div class="stat"><div class="lbl">即時分數</div>'
        f'<div class="val {score_cls}">{score:.0f}</div></div>'
        f'<div class="stat"><div class="lbl">階段</div>'
        f'<div class="val">{phase + 1}/{phase_total}</div></div>'
        f'<div class="stat"><div class="lbl">FPS</div>'
        f'<div class="val">{fps:.1f}</div></div>'
        f'</div>{msg_html}{guide_html}'
        f'<div class="assistant-strip">'
        f'<div class="mini-avatar">{avatar}</div>'
        f'<div><div class="mini-title">{name} '
        f'{"語音提醒中" if voice_enabled and lang == "zh" else "Voice coach" if voice_enabled else "Silent coach"}'
        f'{voice_html}</div>'
        f'<div class="mini-msg">{assistant_msg}</div></div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


def video_call_title(
    title: str,
    meta: str,
) -> None:
    st.markdown(
        '<div class="video-call-title">'
        f'<div class="left"><span class="dot"></span>{escape(title)}</div>'
        f'<div class="meta">{escape(meta)}</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def live_prompt_panel(
    template: dict,
    guide: dict | None = None,
    phase: int = 0,
    phase_total: int = 1,
    msgs: List[str] | None = None,
    voice_enabled: bool = False,
    character_key: str | None = None,
    lang: str = "zh",
) -> None:
    """Clean live cue panel for the FaceTime-style realtime view."""
    import coach as coach_mod

    guide = guide or {}
    msgs = msgs or []
    char = coach_mod.get_character(character_key)
    name = char["name_zh"] if lang == "zh" else char["name_en"]
    cue = msgs[0] if msgs else guide.get("action") or template.get("cue", "")
    detail = guide.get("detail") or template.get("description", "")
    pct = int(guide.get("percent") or ((phase + 1) / max(1, phase_total) * 100))
    pct = max(0, min(100, pct))
    voice_text = (
        "人聲提示開啟" if voice_enabled and lang == "zh"
        else "Voice cues on" if voice_enabled
        else "語音關閉" if lang == "zh"
        else "Voice off"
    )
    wave = (
        '<span class="voice-wave"><i></i><i></i><i></i></span>'
        if voice_enabled else ""
    )
    st.markdown(
        '<div class="live-clean-panel">'
        f'<div class="kicker">{escape(name)} · {escape("即時提示" if lang == "zh" else "Live cue")}</div>'
        f'<div class="cue">{escape(str(cue))}</div>'
        f'<div class="detail">{escape(str(detail))}</div>'
        '<div class="bar">'
        f'<span style="width:{pct}%;background:{escape(char.get("color", "#007aff"))}"></span>'
        '</div>'
        f'<div class="voice">{escape(voice_text)}{wave}</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def live_session_stats(
    elapsed_s: float,
    score: float,
    phase: int,
    phase_total: int,
    fps: float,
    lang: str = "zh",
) -> None:
    mm = int(elapsed_s) // 60
    ss = int(elapsed_s) % 60
    labels = [
        ("時間" if lang == "zh" else "Time", f"{mm:02d}:{ss:02d}"),
        ("即時分數" if lang == "zh" else "Score", f"{score:.0f}"),
        ("階段" if lang == "zh" else "Phase", f"{phase + 1}/{phase_total}"),
        ("FPS", f"{fps:.1f}"),
    ]
    cells = "".join(
        '<div class="live-stat">'
        f'<div class="label">{escape(label)}</div>'
        f'<div class="value">{escape(value)}</div>'
        '</div>'
        for label, value in labels
    )
    st.markdown(
        '<div class="live-stats-panel">'
        f'<div class="kicker">{escape("狀態" if lang == "zh" else "Status")}</div>'
        f'<div class="live-stats-grid">{cells}</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def today_plan_panel(plan: dict, lang: str = "zh") -> None:
    goal = int(plan.get("daily_goal", 1))
    done = int(plan.get("completed_count", 0))
    pct = max(0, min(100, int(done / max(1, goal) * 100)))
    title = (
        f"今日復健 {done}/{goal}"
        if lang == "zh" else f"Today's rehab {done}/{goal}"
    )
    reminder = plan.get("reminder", "")
    task_html = ""
    for task in plan.get("tasks", []):
        cls = "today-task done" if task.get("completed") else "today-task"
        prefix = "完成" if task.get("completed") and lang == "zh" else "Done" if task.get("completed") else "下一步" if lang == "zh" else "Next"
        task_html += (
            f'<div class="{cls}">'
            f'<div class="name">{escape(prefix)} · {escape(str(task.get("name", "")))}</div>'
            f'<div class="desc">{escape(str(task.get("description", "")))}</div>'
            '</div>'
        )
    st.markdown(
        '<div class="today-plan-panel">'
        f'<div class="kicker">{escape("今日課表" if lang == "zh" else "Today plan")}</div>'
        f'<div class="title">{escape(title)}</div>'
        f'<div class="reminder">{escape(str(reminder))}</div>'
        '<div class="bar">'
        f'<span style="width:{pct}%"></span>'
        '</div>'
        f'{task_html}'
        '</div>',
        unsafe_allow_html=True,
    )


def live_companion_pip(
    template: dict,
    guide: dict | None = None,
    phase: int = 0,
    phase_total: int = 1,
    msgs: List[str] | None = None,
    voice_enabled: bool = False,
    character_key: str | None = None,
    lang: str = "zh",
) -> None:
    """視訊通話旁的教練提示牌：不顯示人偶，只顯示提示詞。"""
    import coach as coach_mod

    guide = guide or {}
    msgs = msgs or []
    char = coach_mod.get_character(character_key)
    name = char["name_zh"] if lang == "zh" else char["name_en"]
    avatar = _coach_avatar_html(char)
    style = (
        f"background:linear-gradient(135deg,{char['color']},{char['color_dark']});"
    )
    action = guide.get("action") or (
        "保持節奏" if lang == "zh" else "Keep the rhythm"
    )
    detail = (
        msgs[0] if msgs else guide.get("detail") or template.get("cue", "")
    )
    pct = int(guide.get("percent") or (
        (phase + 1) / max(1, phase_total) * 100
    ))
    audio = (
        "語音輸出中" if voice_enabled and lang == "zh"
        else "Audio output on" if voice_enabled
        else "語音未開啟" if lang == "zh"
        else "Audio off"
    )
    label = "教練提示牌" if lang == "zh" else "Coach cue"
    live = "LIVE"
    wave = (
        '<span class="voice-wave"><i></i><i></i><i></i></span>'
        if voice_enabled else ""
    )
    st.markdown(
        '<div class="coach-pip-card">'
        '<div class="pip-top">'
        f'<div class="pip-label">{escape(label)}</div>'
        f'<div class="pip-live">{escape(live)}</div>'
        '</div>'
        '<div class="pip-screen">'
        f'<div class="pip-coach-avatar" style="{style}">{avatar}</div>'
        '<div class="pip-board">'
        f'<div class="pip-board-k">{escape(name)}</div>'
        f'<div class="pip-board-v">{escape(str(action))}</div>'
        '</div></div>'
        f'<div class="pip-detail">{escape(str(detail))}</div>'
        '<div class="pip-progress">'
        f'<span style="width:{max(0, min(100, pct))}%"></span>'
        '</div>'
        f'<div class="pip-audio">🔊 {escape(audio)}{wave}</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def session_control_panel(
    exercise_name: str,
    voice_enabled: bool,
    pip_enabled: bool = True,
    scoring_enabled: bool = True,
    lang: str = "zh",
) -> None:
    voice_label = "已開啟" if voice_enabled and lang == "zh" else "On" if voice_enabled else "未開啟" if lang == "zh" else "Off"
    cue_label = "大字提示" if pip_enabled and lang == "zh" else "Large cues" if pip_enabled else "未開啟" if lang == "zh" else "Off"
    score_label = "即時分析" if scoring_enabled and lang == "zh" else "Live scoring" if scoring_enabled else "待啟動" if lang == "zh" else "Pending"
    st.markdown(
        '<div class="session-control">'
        '<div class="primary-tile">'
        f'<div class="eyebrow">{escape("LIVE REHAB")}</div>'
        f'<div class="title">{escape(exercise_name)}</div>'
        f'<div class="subtitle">{escape("像 FaceTime 一樣看著主相機，畫面只保留大字提示、節奏和語音。" if lang == "zh" else "A FaceTime-like camera view with large cues, rhythm, and voice.")}</div>'
        '</div>'
        '<div class="mini-tile">'
        f'<div class="mini-k">{escape("音訊" if lang == "zh" else "Audio")}</div>'
        f'<div class="mini-v">{escape(voice_label)}</div>'
        f'<div class="mini-d">{escape("短句、慢速、人聲提示" if lang == "zh" else "Short, slower spoken cues")}</div>'
        '</div>'
        '<div class="mini-tile">'
        f'<div class="mini-k">{escape("提示" if lang == "zh" else "Cue")}</div>'
        f'<div class="mini-v">{escape(cue_label)}</div>'
        f'<div class="mini-d">{escape("不顯示骨架、角度或教學人物" if lang == "zh" else "No skeleton, angles, or coach figure")}</div>'
        '</div>'
        '<div class="mini-tile">'
        f'<div class="mini-k">{escape("評估" if lang == "zh" else "Scoring")}</div>'
        f'<div class="mini-v">{escape(score_label)}</div>'
        f'<div class="mini-d">{escape("結束後產生分數與建議" if lang == "zh" else "Score and advice after session")}</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def audio_doctor(
    voice_enabled: bool,
    server_voice: bool,
    browser_voice: bool,
    lang: str = "zh",
) -> None:
    if lang == "zh":
        title = "音訊檢查"
        detail = (
            f"語音設定：{'開啟' if voice_enabled else '關閉'} · "
            f"系統語音：{'可用' if server_voice else '不可用'} · "
            f"瀏覽器音訊：{'可輸出 WAV' if browser_voice else '不可用'}"
        )
    else:
        title = "Audio check"
        detail = (
            f"Voice setting: {'On' if voice_enabled else 'Off'} · "
            f"System speech: {'Ready' if server_voice else 'Unavailable'} · "
            f"Browser audio: {'WAV ready' if browser_voice else 'Unavailable'}"
        )
    st.markdown(
        '<div class="audio-doctor">'
        f'<div class="title">🔊 {escape(title)}</div>'
        f'<div class="detail">{escape(detail)}</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def browser_speech_button(
    text: str,
    label: str,
    lang: str = "zh",
    height: int = 56,
) -> None:
    """Client-side Web Speech button. Useful when OS/server TTS is muted."""
    js_lang = "zh-TW" if lang == "zh" else "en-US"
    safe_text = text.replace("\\", "\\\\").replace("`", "\\`")
    safe_label = escape(label)
    components.html(
        f"""
        <button id="speakBtn" style="
          width:100%;height:44px;border:0;border-radius:14px;
          background:#0071e3;color:white;font-weight:800;
          font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
          cursor:pointer;box-shadow:0 8px 22px rgba(0,113,227,.22);">
          {safe_label}
        </button>
        <script>
        const btn = document.getElementById('speakBtn');
        btn.onclick = () => {{
          const msg = new SpeechSynthesisUtterance(`{safe_text}`);
          msg.lang = "{js_lang}";
          msg.rate = 0.92;
          msg.pitch = 1.0;
          window.speechSynthesis.cancel();
          window.speechSynthesis.speak(msg);
        }};
        </script>
        """,
        height=height,
    )


def prep_guide_cards(steps: List[dict], lang: str = "zh") -> None:
    if not steps:
        return
    items = []
    for step in steps:
        items.append(
            '<div class="prep-guide-card">'
            f'<div class="prep-icon">{step.get("icon", "•")}</div>'
            f'<div class="prep-title">{step.get("title", "")}</div>'
            f'<div class="prep-detail">{step.get("detail", "")}</div>'
            '</div>'
        )
    st.markdown(
        f'<div class="prep-guide-grid">{"".join(items)}</div>',
        unsafe_allow_html=True,
    )


def voice_instruction_card(
    steps: List[dict],
    cue: str = "",
    voice_enabled: bool = True,
    lang: str = "zh",
) -> None:
    """錄影前的口語教學摘要，和小人示範並排使用。"""
    if lang == "zh":
        kicker = "語音教練"
        headline = "先聽說明，再看教練提示牌"
        status = "已開啟語音提示" if voice_enabled else "語音尚未開啟"
        cue_title = "重點提醒"
    else:
        kicker = "Voice coach"
        headline = "Listen first, then follow the demo"
        status = "Voice cues enabled" if voice_enabled else "Voice cues disabled"
        cue_title = "Key cue"

    rows = [
        {
            "icon": "🔊" if voice_enabled else "🔇",
            "title": status,
            "detail": (
                "進入即時鏡頭時，系統會用簡短慢速句子提醒方向。"
                if lang == "zh"
                else "During live camera mode, concise spoken cues guide direction and rhythm."
            ),
        }
    ]
    rows.extend(steps[:3])
    if cue:
        rows.append({"icon": "✓", "title": cue_title, "detail": cue})

    item_html = ""
    for row in rows:
        item_html += (
            '<div class="voice-line">'
            f'<div class="voice-icon">{escape(str(row.get("icon", "•")))}</div>'
            '<div>'
            f'<div class="voice-title">{escape(str(row.get("title", "")))}</div>'
            f'<div class="voice-detail">{escape(str(row.get("detail", "")))}</div>'
            '</div></div>'
        )
    st.markdown(
        '<div class="voice-demo-panel">'
        f'<div class="kicker">{escape(kicker)}</div>'
        f'<div class="headline">{escape(headline)}</div>'
        f'{item_html}</div>',
        unsafe_allow_html=True,
    )


def breathing_orb(text: str = "深呼吸") -> None:
    st.markdown(
        f'<div class="breath-wrap">'
        f'<div class="breath-orb">{text}</div></div>',
        unsafe_allow_html=True,
    )


def confetti() -> None:
    """JS canvas-confetti 五彩確彈，用於慶祝個人新高/解鎖徽章。"""
    st.markdown(
        """
        <script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.9.2/dist/confetti.browser.min.js"></script>
        <script>
        (function(){
          var d = 2000, end = Date.now() + d;
          var colors = ['#007aff','#34c759','#ff9500','#ff2d55','#ffcc00','#5ac8fa'];
          (function frame(){
            confetti({particleCount:5, angle:60, spread:55, origin:{x:0}, colors:colors});
            confetti({particleCount:5, angle:120, spread:55, origin:{x:1}, colors:colors});
            if (Date.now() < end) requestAnimationFrame(frame);
          })();
        })();
        </script>
        """,
        unsafe_allow_html=True,
    )


_MOOD_LABELS = [
    ("😣", "很差"), ("🙁", "不好"), ("😐", "普通"),
    ("🙂", "不錯"), ("😄", "極佳"),
]


def mood_picker(state_key: str, lang: str = "zh") -> int:
    """5 段心情選擇器；回傳 1-5。"""
    if state_key not in st.session_state:
        st.session_state[state_key] = 3
    cur = int(st.session_state[state_key])
    cols = st.columns(5)
    en_lbls = ["Awful", "Bad", "OK", "Good", "Great"]
    for i, ((emoji, lbl), col) in enumerate(zip(_MOOD_LABELS, cols), 1):
        is_sel = i == cur
        bg = "#007aff" if is_sel else "white"
        fg = "white" if is_sel else "#1c1c1e"
        meta = "rgba(255,255,255,.85)" if is_sel else "#8e8e93"
        if col.button(
            emoji,
            key=f"mood_{state_key}_{i}",
            use_container_width=True,
        ):
            st.session_state[state_key] = i
            st.rerun()
        label = lbl if lang == "zh" else en_lbls[i - 1]
        col.markdown(
            f'<div style="text-align:center;color:{meta};'
            f'font-size:.75rem;margin-top:-.4rem;'
            f'background:{bg};color:{fg};border-radius:8px;'
            f'padding:.15rem 0;font-weight:600;">{label}</div>',
            unsafe_allow_html=True,
        )
    return cur


def daily_challenge_card(
    name: str, description: str, lang: str = "zh",
) -> None:
    label = "🎯 今日挑戰" if lang == "zh" else "🎯 Daily Challenge"
    st.markdown(
        f'<div class="challenge-card">'
        f'<div class="title-row"><span class="lbl">{label}</span></div>'
        f'<div class="name">{name}</div>'
        f'<div class="desc">{description}</div></div>',
        unsafe_allow_html=True,
    )


# ============================================================
# 卡通教練
# ============================================================
def _coach_avatar_html(char: dict, mini: bool = False) -> str:
    if char.get("avatar") == "starfish":
        return '<span class="starfish-core"></span>'
    return char["emoji"]


def coach_card(
    character_key: str | None = None,
    state: str = "greet",
    lang: str = "zh",
    message: str | None = None,
) -> None:
    """渲染卡通教練 + 對話框。

    character_key : doggo / kitty / bear / bunny
    state         : greet / ready / live / good / average / low / pb /
                    rest / streak / first_time
    message       : 直接覆蓋訊息（不傳則由 coach.message_for 隨機挑）
    """
    import coach as coach_mod
    char = coach_mod.get_character(character_key)
    msg = message or coach_mod.message_for(state, lang)
    name = char["name_zh"] if lang == "zh" else char["name_en"]
    style = (
        f"--coach-c1:{char['color']};"
        f"--coach-c2:{char['color_dark']};"
    )
    avatar_cls = "coach-avatar"
    if char.get("avatar") == "starfish":
        avatar_cls += " coach-avatar-starfish"
    avatar_html = _coach_avatar_html(char)
    st.markdown(
        f'<div class="coach-card" style="{style}">'
        f'<div class="{avatar_cls}">{avatar_html}</div>'
        f'<div class="coach-bubble">'
        f'<div class="coach-name">{name}</div>'
        f'<div class="coach-msg">{msg}</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


# ============================================================
# Apple 風視覺化提示卡（取代文字牆）
# ============================================================
def cue_grid(cues: list[dict], lang: str = "zh") -> None:
    """渲染一排方向提示卡。cue 來自 scoring.feedback_cues()。"""
    if not cues:
        return
    items = []
    for c in cues:
        sev = c.get("severity", "mid")
        joint = c.get("body_part", c["joint"])
        verb = c["verb"] if lang == "zh" else c.get("verb_en", c["verb"])
        delta = c["delta"]
        items.append(
            f'<div class="cue-card {sev}">'
            f'<div class="sev-bar"></div>'
            f'<div class="arrow">{c["icon"]}</div>'
            f'<div class="joint-name">{joint}</div>'
            f'<div class="verb-action">{verb}</div>'
            f'<div class="delta-num">{delta:.0f}°</div>'
            f'</div>'
        )
    st.markdown(
        f'<div class="cue-grid">{"".join(items)}</div>',
        unsafe_allow_html=True,
    )


def apple_hero(
    eyebrow: str, headline: str, sub: str = "",
) -> None:
    """蘋果產品頁式巨字 hero（極大標題 + 副標 + 小 eyebrow）。"""
    st.markdown(
        f'<div class="apple-hero">'
        f'<div class="eyebrow">{eyebrow}</div>'
        f'<div class="headline">{headline}</div>'
        f'<div class="sub">{sub}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def mega_score(
    score: float, verdict: str = "", denom: str = "/ 100",
) -> None:
    """巨型分數展示。"""
    if score >= 85:
        cls = ""
    elif score >= 70:
        cls = "warn"
    else:
        cls = "bad"
    st.markdown(
        f'<div class="mega-score {cls}">'
        f'<div class="num">{score:.1f}</div>'
        f'<div class="denom">{denom}</div>'
        f'<div class="verdict">{verdict}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def section_eyebrow(label: str) -> None:
    """蘋果風細線 + 居中標題的區段分隔。"""
    st.markdown(
        f'<div class="section-eyebrow">'
        f'<span class="label">{label}</span></div>',
        unsafe_allow_html=True,
    )


def demo_figure_card(
    template: dict,
    duration_s: float = 4.0,
    title: str | None = None,
    lang: str = "zh",
) -> None:
    """渲染小人示範動畫卡片（自動依範本動作節奏循環）。"""
    import demo_figure as df

    series = template.get("angle_series", {})
    accents = df.primary_joints_for(template)
    svg = df.stick_figure_svg(
        series, duration_s=duration_s,
        width=260, height=340,
        bg=COLORS["primary"],
        accent_joints=accents,
    )
    if not svg:
        return

    if title is None:
        title = "動作示範" if lang == "zh" else "DEMO"
    cue = template.get("cue", "")
    name = template.get("name", "")
    st.markdown(
        f'<div class="demo-card">'
        f'<div class="demo-eyebrow">{title}</div>'
        f'<div class="demo-name">{name}</div>'
        f'<div class="demo-svg">{svg}</div>'
        f'<div class="demo-cue">🔔 {cue}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def _image_data_uri(path: str) -> str:
    data = Path(path).read_bytes()
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:image/png;base64,{encoded}"


_REHAB_POSE_ASSET_BY_KEY = {
    "arm_raise": "arm_raise",
    "shoulder_abduction": "shoulder_abduction",
    "elbow_flexion": "elbow_flexion",
    "wall_pushup": "wall_pushup",
    "sit_to_stand": "sit_to_stand",
    "mini_squat": "mini_squat",
    "knee_extension": "knee_extension",
    "hip_abduction": "hip_abduction",
    "march_in_place": "march_in_place",
    "seated_march": "seated_march",
}


_REHAB_POSE_ASSET_BY_CATEGORY = {
    "upper": "shoulder_abduction",
    "lower": "mini_squat",
    "balance": "march_in_place",
}


def _demo_pose_asset(template: dict) -> Path:
    assets = Path(__file__).parent / "static" / "assets"
    key = str(template.get("key", ""))
    category = str(template.get("category", ""))
    pose_key = _REHAB_POSE_ASSET_BY_KEY.get(
        key, _REHAB_POSE_ASSET_BY_CATEGORY.get(category)
    )
    candidates: list[Path] = []
    if pose_key:
        candidates.append(assets / "rehab-poses" / f"{pose_key}.png")
    candidates.append(assets / "rehab-coach-3d.png")
    return next((path for path in candidates if path.exists()), candidates[-1])


def demo_figure_3d_video(
    template: dict,
    duration_s: float = 5.2,
    lang: str = "zh",
    height: int = 430,
) -> None:
    """Render a looped 3D teaching demo driven by the exercise key."""
    payload = {
        "key": template.get("key", ""),
        "category": template.get("category", "custom"),
        "name": template.get("name", ""),
        "cue": template.get("cue", ""),
        "duration": max(2.0, float(duration_s)),
        "lang": lang,
    }
    data = json.dumps(payload, ensure_ascii=False)
    title = "動作示範" if lang == "zh" else "Movement demo"
    video_label = "3D 教學影片" if lang == "zh" else "3D teaching video"
    play_label = "播放 / 暫停" if lang == "zh" else "Play / pause"
    coach_asset = _demo_pose_asset(template)
    coach_image = _image_data_uri(str(coach_asset)) if coach_asset.exists() else ""

    components.html(
        f"""
<div id="demo3dRoot">
  <div class="topbar">
    <div>
      <div class="eyebrow">{escape(video_label)}</div>
      <div class="title">{escape(title)}</div>
    </div>
    <button id="demoToggle" aria-label="{escape(play_label)}">Ⅱ</button>
  </div>
  <img id="coachImage" alt="{escape(video_label)}" src="{coach_image}" />
  <canvas id="demoCanvas" aria-label="{escape(video_label)}"></canvas>
  <div class="caption">
    <div class="name" id="demoName"></div>
    <div class="cue" id="demoCue"></div>
  </div>
  <div class="progress"><span id="demoProgress"></span></div>
</div>
<script>
const DEMO_DATA = {data};
</script>
<script src="https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.min.js"></script>
<script>
(function(){{
  const root = document.getElementById('demo3dRoot');
  const canvas = document.getElementById('demoCanvas');
  const btn = document.getElementById('demoToggle');
  const progress = document.getElementById('demoProgress');
  const coachImage = document.getElementById('coachImage');
  document.getElementById('demoName').textContent = DEMO_DATA.name || 'Demo';
  document.getElementById('demoCue').textContent = DEMO_DATA.cue ? 'Cue: ' + DEMO_DATA.cue : '';
  let playing = true;
  btn.onclick = () => {{
    playing = !playing;
    btn.textContent = playing ? 'Ⅱ' : '▶';
  }};

  function fallback2d(){{
    const ctx = canvas.getContext('2d');
    if (!ctx) {{ return; }}
    function size(){{
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.floor(rect.width * dpr));
      canvas.height = Math.max(1, Math.floor(rect.height * dpr));
      ctx.setTransform(dpr,0,0,dpr,0,0);
    }}
    size();
    requestAnimationFrame(size);
    setTimeout(size, 120);
    let start = performance.now();
    function draw(now){{
      if (!playing) {{
        requestAnimationFrame(draw);
        return;
      }}
      const rect = canvas.getBoundingClientRect();
      const t = ((now - start) / 1000 / DEMO_DATA.duration) % 1;
      const u = 0.5 - 0.5 * Math.cos(t * Math.PI * 2);
      ctx.clearRect(0,0,rect.width,rect.height);
      if (coachImage) {{
        const lift = Math.sin(t * Math.PI * 2) * 4;
        const sway = Math.sin(t * Math.PI * 2 + 0.8) * 1.2;
        coachImage.style.transform = `translate3d(-50%, ${{lift}}px, 0) rotate(${{sway}}deg)`;
      }}
      ctx.lineWidth = 10;
      ctx.lineCap = 'round';
      ctx.strokeStyle = '#1f2937';
      ctx.fillStyle = '#007aff';
      const cx = rect.width/2, base = rect.height*0.78;
      const arm = 58, leg = 66;
      const shoulderY = base - 150, hipY = base - 70;
      const raise = /arm_raise|shoulder_abduction/.test(DEMO_DATA.key);
      const armA = raise ? (-Math.PI/2 + u*Math.PI) : (Math.PI/2 - u*Math.PI*0.7);
      const lx = cx-48, rx = cx+48;
      function line(a,b,c,d){{ctx.beginPath();ctx.moveTo(a,b);ctx.lineTo(c,d);ctx.stroke();}}
      line(cx, shoulderY, cx, hipY);
      line(lx, shoulderY, rx, shoulderY);
      line(cx-28, hipY, cx+28, hipY);
      line(lx, shoulderY, lx + Math.cos(armA)*arm, shoulderY + Math.sin(armA)*arm);
      line(rx, shoulderY, rx - Math.cos(armA)*arm, shoulderY + Math.sin(armA)*arm);
      line(cx-24, hipY, cx-34-u*18, hipY+leg);
      line(cx+24, hipY, cx+34+u*18, hipY+leg);
      ctx.beginPath(); ctx.arc(cx, shoulderY-38, 24, 0, Math.PI*2); ctx.fill();
      progress.style.width = Math.round(t * 100) + '%';
      requestAnimationFrame(draw);
    }}
    window.addEventListener('resize', size);
    requestAnimationFrame(draw);
  }}

  if (!window.THREE) {{
    fallback2d();
    return;
  }}

  const probe = document.createElement('canvas');
  const hasWebgl = !!(probe.getContext('webgl2') || probe.getContext('webgl') || probe.getContext('experimental-webgl'));
  if (!hasWebgl) {{
    fallback2d();
    return;
  }}

  const THREE = window.THREE;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
  camera.position.set(0, 1.32, 4.28);
  camera.lookAt(0, 1.26, 0);
  let renderer;
  try {{
    renderer = new THREE.WebGLRenderer({{canvas, antialias:true, alpha:true}});
  }} catch (err) {{
    fallback2d();
    return;
  }}
  root.classList.add('is-3d');
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.shadowMap.enabled = true;
  renderer.setClearColor(0x000000, 0);

  const hemi = new THREE.HemisphereLight(0xffffff, 0xaeb9c8, 2.3);
  scene.add(hemi);
  const keyLight = new THREE.DirectionalLight(0xffffff, 1.6);
  keyLight.position.set(2.5, 4, 4);
  keyLight.castShadow = true;
  scene.add(keyLight);

  const floor = new THREE.Mesh(
    new THREE.CircleGeometry(1.8, 72),
    new THREE.MeshStandardMaterial({{color:0xe4eef8, roughness:0.86}})
  );
  floor.rotation.x = -Math.PI/2;
  floor.position.y = -0.02;
  floor.receiveShadow = true;
  scene.add(floor);

  const avatar = new THREE.Group();
  avatar.position.y = -0.15;
  avatar.scale.set(1.15, 1.15, 1.15);
  scene.add(avatar);
  const matSkin = new THREE.MeshStandardMaterial({{color:0xffc9a8, roughness:0.55}});
  const matShirt = new THREE.MeshStandardMaterial({{color:0x83d7df, roughness:0.58, metalness:0.02}});
  const matPants = new THREE.MeshStandardMaterial({{color:0x303947, roughness:0.62, metalness:0.02}});
  const matShoe = new THREE.MeshStandardMaterial({{color:0x263447, roughness:0.5, metalness:0.03}});
  const matHair = new THREE.MeshStandardMaterial({{color:0x20242b, roughness:0.72}});
  const matJoint = new THREE.MeshStandardMaterial({{color:0xffffff, roughness:0.5}});
  const yAxis = new THREE.Vector3(0, 1, 0);
  const segs = {{}};
  const joints = {{}};
  const segmentNames = [
    ['spine','hipC','chest'], ['neck','chest','neck'],
    ['shoulderBar','shoulderL','shoulderR'], ['hipBar','hipL','hipR'],
    ['upperArmL','shoulderL','elbowL'], ['lowerArmL','elbowL','wristL'],
    ['upperArmR','shoulderR','elbowR'], ['lowerArmR','elbowR','wristR'],
    ['thighL','hipL','kneeL'], ['shinL','kneeL','ankleL'],
    ['thighR','hipR','kneeR'], ['shinR','kneeR','ankleR']
  ];
  function materialFor(name){{
    if (/thigh|shin|hipBar/.test(name)) return matPants;
    if (/upperArm|lowerArm|neck/.test(name)) return matSkin;
    return matShirt;
  }}
  function radiusFor(name){{
    if (/thigh/.test(name)) return 0.09;
    if (/shin/.test(name)) return 0.075;
    if (/upperArm/.test(name)) return 0.068;
    if (/lowerArm/.test(name)) return 0.058;
    if (/spine|shoulderBar|hipBar/.test(name)) return 0.065;
    return 0.05;
  }}
  function jointMaterial(name){{
    if (/ankle/.test(name)) return matShoe;
    if (/hip|knee/.test(name)) return matPants;
    if (/shoulder/.test(name)) return matShirt;
    if (/elbow|wrist|neck/.test(name)) return matSkin;
    return matJoint;
  }}
  function jointRadius(name){{
    if (/ankle/.test(name)) return 0.09;
    if (/hip|knee/.test(name)) return 0.08;
    if (/wrist/.test(name)) return 0.065;
    return 0.075;
  }}
  function segment(name){{
    const r = radiusFor(name);
    const mesh = new THREE.Mesh(
      new THREE.CylinderGeometry(r, r, 1, 28),
      materialFor(name)
    );
    mesh.castShadow = true;
    avatar.add(mesh);
    segs[name] = mesh;
  }}
  segmentNames.forEach(([name]) => segment(name));
  ['hipC','chest','neck','shoulderL','shoulderR','elbowL','elbowR','wristL','wristR','hipL','hipR','kneeL','kneeR','ankleL','ankleR'].forEach((name) => {{
    const s = new THREE.Mesh(
      new THREE.SphereGeometry(jointRadius(name), 28, 18),
      jointMaterial(name)
    );
    s.castShadow = true;
    avatar.add(s);
    joints[name] = s;
  }});
  const torso = new THREE.Mesh(
    new THREE.CylinderGeometry(0.22, 0.29, 1, 36),
    matShirt
  );
  torso.castShadow = true;
  avatar.add(torso);
  const pelvis = new THREE.Mesh(new THREE.SphereGeometry(0.2, 32, 18), matPants);
  pelvis.scale.set(1.35, 0.5, 0.82);
  pelvis.castShadow = true;
  avatar.add(pelvis);
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.18, 32, 20), matSkin);
  head.castShadow = true;
  avatar.add(head);
  const hair = new THREE.Mesh(new THREE.SphereGeometry(0.18, 32, 16), matHair);
  hair.scale.set(1.05, 0.56, 0.9);
  hair.castShadow = true;
  avatar.add(hair);
  const eyeMat = new THREE.MeshBasicMaterial({{color:0x20242b}});
  const eyeL = new THREE.Mesh(new THREE.SphereGeometry(0.018, 12, 8), eyeMat);
  const eyeR = new THREE.Mesh(new THREE.SphereGeometry(0.018, 12, 8), eyeMat);
  avatar.add(eyeL, eyeR);
  const chestMark = new THREE.Mesh(
    new THREE.SphereGeometry(0.09, 32, 16),
    new THREE.MeshStandardMaterial({{color:0x34c759, roughness:0.4}})
  );
  chestMark.scale.set(1.35, 0.38, 0.22);
  avatar.add(chestMark);

  const v = (x,y,z=0) => new THREE.Vector3(x,y,z);
  const smooth = (x) => x*x*(3-2*x);
  const wave = (phase) => 0.5 - 0.5 * Math.cos(phase * Math.PI * 2);
  function basePose(){{
    return {{
      hipC:v(0,1.08,0), chest:v(0,1.83,0), neck:v(0,2.18,0),
      shoulderL:v(-0.44,2.02,0), shoulderR:v(0.44,2.02,0),
      elbowL:v(-0.48,1.45,0), elbowR:v(0.48,1.45,0),
      wristL:v(-0.48,0.93,0), wristR:v(0.48,0.93,0),
      hipL:v(-0.23,1.06,0), hipR:v(0.23,1.06,0),
      kneeL:v(-0.23,0.58,0.03), kneeR:v(0.23,0.58,0.03),
      ankleL:v(-0.23,0.08,0), ankleR:v(0.23,0.08,0)
    }};
  }}
  function setArm(p, side, mode, u){{
    const sh = side < 0 ? p.shoulderL : p.shoulderR;
    const L1 = 0.58, L2 = 0.52;
    let d1, d2;
    if (mode === 'abduct') {{
      const a = u * Math.PI * 0.55;
      d1 = v(side * Math.sin(a), -Math.cos(a), 0);
      d2 = d1.clone();
    }} else if (mode === 'raise') {{
      const a = u * Math.PI;
      d1 = v(side * 0.08 * Math.sin(a), -Math.cos(a), -0.24 * Math.sin(a));
      d2 = d1.clone();
    }} else if (mode === 'curl') {{
      d1 = v(0, -1, 0);
      const b = u * Math.PI * 0.82;
      d2 = v(0, -Math.cos(b), -0.28 * Math.sin(b));
    }} else if (mode === 'push') {{
      d1 = v(side * 0.12, -0.22 + u*0.08, -0.98);
      d2 = v(-side * 0.1, -0.28 + u*0.2, -0.86);
    }} else {{
      d1 = v(0, -1, 0); d2 = v(0, -1, 0);
    }}
    const elbow = sh.clone().add(d1.normalize().multiplyScalar(L1));
    const wrist = elbow.clone().add(d2.normalize().multiplyScalar(L2));
    if (side < 0) {{ p.elbowL = elbow; p.wristL = wrist; }}
    else {{ p.elbowR = elbow; p.wristR = wrist; }}
  }}
  function poseAt(phase){{
    const u = smooth(wave(phase));
    const p = basePose();
    const key = DEMO_DATA.key || DEMO_DATA.category || '';
    if (/shoulder_abduction/.test(key)) {{
      setArm(p, -1, 'abduct', u); setArm(p, 1, 'abduct', u);
    }} else if (/arm_raise/.test(key)) {{
      setArm(p, -1, 'raise', u); setArm(p, 1, 'raise', u);
    }} else if (/elbow_flexion/.test(key)) {{
      setArm(p, -1, 'curl', u); setArm(p, 1, 'curl', u);
    }} else if (/wall_pushup/.test(key)) {{
      p.chest.z = -0.2 * u; p.hipC.z = -0.08 * u; p.neck.z = -0.24 * u;
      p.shoulderL.z = p.shoulderR.z = -0.22 * u;
      setArm(p, -1, 'push', u); setArm(p, 1, 'push', u);
    }} else if (/sit_to_stand/.test(key)) {{
      const down = 1-u;
      p.hipC.y -= 0.34*down; p.chest.y -= 0.24*down; p.neck.y -= 0.2*down;
      p.hipL.y = p.hipR.y = p.hipC.y - 0.02;
      p.kneeL.z = p.kneeR.z = 0.28*down; p.kneeL.y = p.kneeR.y = 0.58 + 0.06*down;
      p.ankleL.z = p.ankleR.z = 0.12*down;
      setArm(p, -1, 'raise', down*0.35); setArm(p, 1, 'raise', down*0.35);
    }} else if (/mini_squat/.test(key)) {{
      p.hipC.y -= 0.24*u; p.chest.y -= 0.2*u; p.neck.y -= 0.16*u;
      p.hipL.y = p.hipR.y = p.hipC.y - 0.02;
      p.kneeL.z = p.kneeR.z = 0.22*u; p.kneeL.x -= 0.04*u; p.kneeR.x += 0.04*u;
      setArm(p, -1, 'raise', 0.22 + 0.2*u); setArm(p, 1, 'raise', 0.22 + 0.2*u);
    }} else if (/knee_extension/.test(key)) {{
      p.hipC.y = 1.02; p.chest.y = 1.75; p.neck.y = 2.08;
      p.hipL.y = p.hipR.y = 1.0;
      p.kneeL = v(-0.23,0.72,0.35); p.kneeR = v(0.23,0.72,0.35);
      p.ankleL = v(-0.23,0.24 + 0.3*u,0.72 - 0.52*u);
      p.ankleR = v(0.23,0.24 + 0.3*u,0.72 - 0.52*u);
      setArm(p, -1, 'curl', 0.12); setArm(p, 1, 'curl', 0.12);
    }} else if (/hip_abduction/.test(key)) {{
      p.hipC.x += 0.06*u; p.chest.x += 0.04*u; p.neck.x += 0.03*u;
      p.kneeL.x = -0.23 - 0.34*u; p.ankleL.x = -0.23 - 0.58*u;
      p.kneeL.y = 0.6 + 0.04*u; p.ankleL.y = 0.1 + 0.06*u;
      setArm(p, -1, 'abduct', 0.18); setArm(p, 1, 'abduct', 0.18);
    }} else if (/seated_march/.test(key)) {{
      const left = Math.max(0, Math.sin(phase*Math.PI*2));
      const right = Math.max(0, -Math.sin(phase*Math.PI*2));
      p.hipC.y = 0.98; p.chest.y = 1.72; p.neck.y = 2.05;
      p.kneeL = v(-0.23,0.68 + left*0.2,0.38-left*0.15);
      p.ankleL = v(-0.23,0.18 + left*0.24,0.66-left*0.18);
      p.kneeR = v(0.23,0.68 + right*0.2,0.38-right*0.15);
      p.ankleR = v(0.23,0.18 + right*0.24,0.66-right*0.18);
    }} else if (/march_in_place|balance/.test(key)) {{
      const left = Math.max(0, Math.sin(phase*Math.PI*2));
      const right = Math.max(0, -Math.sin(phase*Math.PI*2));
      p.kneeL.y += left*0.34; p.kneeL.z += left*0.32; p.ankleL.y += left*0.23; p.ankleL.z += left*0.22;
      p.kneeR.y += right*0.34; p.kneeR.z += right*0.32; p.ankleR.y += right*0.23; p.ankleR.z += right*0.22;
      setArm(p, -1, 'curl', right*0.32); setArm(p, 1, 'curl', left*0.32);
    }} else {{
      setArm(p, -1, 'raise', u*0.7); setArm(p, 1, 'raise', u*0.7);
    }}
    p.shoulderL.y = p.shoulderR.y = p.chest.y + 0.19;
    p.shoulderL.x += p.chest.x; p.shoulderR.x += p.chest.x;
    return p;
  }}
  function updateSeg(mesh, a, b){{
    const mid = a.clone().add(b).multiplyScalar(0.5);
    const dir = b.clone().sub(a);
    const len = dir.length();
    mesh.position.copy(mid);
    mesh.quaternion.setFromUnitVectors(yAxis, dir.normalize());
    mesh.scale.set(1, len, 1);
  }}
  function applyPose(p){{
    segmentNames.forEach(([name,a,b]) => updateSeg(segs[name], p[a], p[b]));
    Object.keys(joints).forEach((name) => joints[name].position.copy(p[name]));
    updateSeg(torso, p.hipC.clone().add(v(0,0.03,0)), p.neck.clone().add(v(0,-0.08,0)));
    pelvis.position.copy(p.hipC).add(v(0,-0.02,0));
    head.position.copy(p.neck).add(v(0,0.3,0));
    hair.position.copy(head.position).add(v(0,0.08,-0.015));
    eyeL.position.copy(head.position).add(v(-0.065,0.025,0.155));
    eyeR.position.copy(head.position).add(v(0.065,0.025,0.155));
    chestMark.position.copy(p.chest).add(v(0,0.04,-0.08));
  }}
  function resize(){{
    const rect = canvas.getBoundingClientRect();
    const w = Math.max(1, rect.width);
    const h = Math.max(1, rect.height);
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }}
  resize();
  requestAnimationFrame(resize);
  setTimeout(resize, 120);
  window.addEventListener('resize', resize);
  let elapsed = 0;
  let lastTick = performance.now();
  function frame(now){{
    if (playing) {{
      elapsed += Math.max(0, (now - lastTick) / 1000);
    }}
    lastTick = now;
    const phase = (elapsed / DEMO_DATA.duration) % 1;
    applyPose(poseAt(phase));
    if (coachImage && !root.classList.contains('is-3d')) {{
      const lift = Math.sin(phase * Math.PI * 2) * 4;
      const sway = Math.sin(phase * Math.PI * 2 + 0.8) * 1.2;
      coachImage.style.transform = `translate3d(-50%, ${{lift}}px, 0) rotate(${{sway}}deg)`;
    }}
    scene.rotation.y = Math.sin(now * 0.00035) * 0.12;
    progress.style.width = Math.round(phase * 100) + '%';
    renderer.render(scene, camera);
    requestAnimationFrame(frame);
  }}
  requestAnimationFrame(frame);
}})();
</script>
<style>
html,body {{
  margin:0;
  background:transparent;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
}}
#demo3dRoot {{
  position:relative;
  min-height:430px;
  border:1px solid rgba(0,0,0,.08);
  border-radius:8px;
  overflow:hidden;
  background:linear-gradient(180deg,#f7fbff 0%,#eef6ff 100%);
  box-shadow:0 14px 32px rgba(20,45,80,.12);
}}
#coachImage {{
  position:absolute;
  left:50%;
  top:58px;
  width:min(84%, 360px);
  height:336px;
  object-fit:contain;
  object-position:center bottom;
  transform:translate3d(-50%,0,0);
  z-index:1;
  filter:drop-shadow(0 18px 22px rgba(35,54,80,.16));
  transition:filter .2s ease;
}}
.is-3d #coachImage {{
  left:auto;
  right:14px;
  top:70px;
  width:76px;
  height:102px;
  transform:none;
  z-index:4;
  opacity:.24;
  border-radius:8px;
  border:1px solid rgba(20,32,51,.12);
  background:rgba(255,255,255,.72);
  box-shadow:0 10px 24px rgba(20,45,80,.12);
  filter:none;
}}
#demoCanvas {{
  position:absolute;
  left:0;
  right:0;
  top:58px;
  z-index:2;
  width:100%;
  height:330px;
  display:block;
  pointer-events:none;
  opacity:1;
}}
.topbar {{
  position:relative;
  z-index:5;
  height:58px;
  padding:12px 14px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  box-sizing:border-box;
}}
.eyebrow {{
  font-size:11px;
  line-height:1.1;
  letter-spacing:.08em;
  text-transform:uppercase;
  color:#5f6f86;
  font-weight:800;
}}
.title {{
  margin-top:3px;
  font-size:19px;
  line-height:1.1;
  color:#142033;
  font-weight:800;
}}
#demoToggle {{
  width:40px;
  height:40px;
  border:0;
  border-radius:50%;
  background:#007aff;
  color:white;
  font-size:16px;
  font-weight:900;
  cursor:pointer;
  box-shadow:0 8px 18px rgba(0,122,255,.28);
}}
.caption {{
  position:absolute;
  z-index:6;
  left:14px;
  right:14px;
  bottom:16px;
  padding:12px 14px;
  border-radius:8px;
  color:#142033;
  background:rgba(255,255,255,.84);
  backdrop-filter:blur(14px);
  border:1px solid rgba(255,255,255,.68);
}}
.caption .name {{
  font-size:16px;
  line-height:1.25;
  font-weight:800;
}}
.caption .cue {{
  margin-top:4px;
  font-size:12px;
  line-height:1.35;
  color:#536174;
  font-weight:650;
}}
.progress {{
  position:absolute;
  left:0;
  right:0;
  bottom:0;
  height:4px;
  background:rgba(20,32,51,.08);
}}
.progress span {{
  display:block;
  height:100%;
  width:0;
  background:#34c759;
}}
</style>
        """,
        height=height,
    )


def coach_picker(
    current_key: str | None,
    on_select_key: str = "coach_pick",
    lang: str = "zh",
) -> str | None:
    """教練選擇器。回傳新的 character_key 或 None（沒換）。"""
    import coach as coach_mod
    chars = list(coach_mod.CHARACTERS.values())
    cols = st.columns(len(chars))
    chosen: str | None = None
    for col, c in zip(cols, chars):
        is_cur = current_key == c["key"]
        name = c["name_zh"] if lang == "zh" else c["name_en"]
        with col:
            st.markdown(
                f'<div class="coach-pick'
                f'{" selected" if is_cur else ""}">'
                f'<div class="ava">{_coach_avatar_html(c)}</div>'
                f'<div class="nm">{name}</div></div>',
                unsafe_allow_html=True,
            )
            label = ("✓ 已選" if is_cur else "選擇") if lang == "zh" \
                else ("✓ Selected" if is_cur else "Choose")
            if st.button(
                label,
                key=f"{on_select_key}_{c['key']}",
                use_container_width=True,
                type="primary" if is_cur else "secondary",
            ):
                chosen = c["key"]
    return chosen


def badge_grid(badges: List[tuple]) -> None:
    """badges: [(icon, name, desc), ...]"""
    if not badges:
        return
    items = "".join(
        f'<div class="badge-tile">'
        f'<div class="b-icon">{icon}</div>'
        f'<div class="b-name">{name}</div>'
        f'<div class="b-desc">{desc}</div>'
        f'</div>'
        for icon, name, desc in badges
    )
    st.markdown(
        f'<div style="display:flex;flex-wrap:wrap;justify-content:center;">'
        f'{items}</div>',
        unsafe_allow_html=True,
    )


# ============================================================
# Plotly 圖表
# ============================================================
def _layout_base(height: int = 320) -> dict:
    return dict(
        height=height,
        margin=dict(l=10, r=10, t=30, b=10),
        plot_bgcolor="white",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="sans-serif", color=COLORS["text"]),
    )


def plot_score_trend(sessions: List[Dict], window: int = 5):
    """Plotly 分數趨勢圖（含 N 次滾動平均）。"""
    if not PLOTLY_OK or not sessions:
        return None
    sorted_s = sorted(sessions, key=lambda s: s["ts"])
    times = [datetime.fromtimestamp(s["ts"]) for s in sorted_s]
    scores = [s["score"] for s in sorted_s]
    rolling = []
    for i in range(len(scores)):
        start = max(0, i - window + 1)
        rolling.append(sum(scores[start:i + 1]) / (i - start + 1))

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=times, y=scores, mode="markers+lines",
        name="單次分數",
        line=dict(color=COLORS["primary"], width=2),
        marker=dict(size=8, color=COLORS["primary"],
                    line=dict(color="white", width=1.5)),
        hovertemplate="%{x|%m-%d %H:%M}<br>分數 %{y:.1f}<extra></extra>",
    ))
    if len(scores) >= 2:
        fig.add_trace(go.Scatter(
            x=times, y=rolling, mode="lines",
            name=f"{window} 次滾動平均",
            line=dict(color=COLORS["accent"], width=3, dash="dot"),
            hovertemplate="平均 %{y:.1f}<extra></extra>",
        ))
    fig.update_layout(
        **_layout_base(340),
        yaxis=dict(range=[0, 105], gridcolor="#eef2f7", title="分數"),
        xaxis=dict(gridcolor="#eef2f7"),
        legend=dict(orientation="h", y=1.12, x=0),
        hovermode="x unified",
    )
    return fig


def plot_joint_radar(joint_scores: Dict[str, Dict[str, float]],
                     threshold: float = 15.0):
    """各關節最大偏差雷達圖；門檻畫成參考圈。"""
    if not PLOTLY_OK or not joint_scores:
        return None
    joints = list(joint_scores.keys())
    devs = [joint_scores[j]["max_dev"] for j in joints]
    max_r = max(max(devs), threshold) * 1.25

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=[threshold] * len(joints) + [threshold],
        theta=joints + [joints[0]],
        name=f"警示門檻 {threshold:.0f}°",
        line=dict(color=COLORS["primary"], dash="dash", width=2),
        fill="toself",
        fillcolor="rgba(0,184,148,.08)",
    ))
    fig.add_trace(go.Scatterpolar(
        r=devs + [devs[0]], theta=joints + [joints[0]],
        name="最大偏差",
        line=dict(color=COLORS["accent"], width=2.5),
        fill="toself",
        fillcolor="rgba(253,121,168,.25)",
        hovertemplate="%{theta}<br>偏差 %{r:.1f}°<extra></extra>",
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, max_r],
                            tickfont=dict(size=10), gridcolor="#eef2f7"),
            angularaxis=dict(tickfont=dict(size=12), gridcolor="#eef2f7"),
            bgcolor="white",
        ),
        height=380,
        margin=dict(l=20, r=20, t=20, b=10),
        showlegend=True,
        legend=dict(orientation="h", y=-0.1),
    )
    return fig


def plot_activity_calendar(sessions: List[Dict], weeks: int = 14):
    """GitHub 風格活動熱圖（最近 N 週）。"""
    if not PLOTLY_OK:
        return None

    today = datetime.now().date()
    days_back = weeks * 7 - 1
    start = today - timedelta(days=days_back)
    start = start - timedelta(days=(start.weekday() + 1) % 7)  # 週日對齊

    counts: Dict = {}
    for s in sessions:
        d = datetime.fromtimestamp(s["ts"]).date()
        counts[d] = counts.get(d, 0) + 1

    n_weeks = (today - start).days // 7 + 1
    grid = [[None] * n_weeks for _ in range(7)]
    text = [[""] * n_weeks for _ in range(7)]
    for col in range(n_weeks):
        for row in range(7):
            d = start + timedelta(days=col * 7 + row)
            if d > today:
                continue
            cnt = counts.get(d, 0)
            grid[row][col] = cnt
            text[row][col] = f"{d.isoformat()}<br>{cnt} 次訓練"

    fig = go.Figure(data=go.Heatmap(
        z=grid, text=text, hoverinfo="text",
        colorscale=[
            [0.0, "#ebedf0"],
            [0.25, "#9be9a8"],
            [0.5, "#40c463"],
            [0.75, "#30a14e"],
            [1.0, "#216e39"],
        ],
        showscale=False, xgap=3, ygap=3, zmin=0, zmax=3,
    ))
    weekdays = ["日", "一", "二", "三", "四", "五", "六"]
    fig.update_layout(
        height=180,
        margin=dict(l=30, r=10, t=10, b=10),
        xaxis=dict(showticklabels=False, showgrid=False, zeroline=False),
        yaxis=dict(
            tickmode="array", tickvals=list(range(7)),
            ticktext=weekdays, showgrid=False, zeroline=False,
            autorange="reversed",
        ),
        plot_bgcolor="white",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def plot_pain_change(sessions: List[Dict], lookback: int = 10):
    """訓練前後疼痛分數對照（取最近 N 次）。"""
    if not PLOTLY_OK or not sessions:
        return None
    recent = [s for s in sessions[-lookback:]
              if "pain_before" in s and "pain_after" in s]
    if not recent:
        return None
    labels = [
        datetime.fromtimestamp(s["ts"]).strftime("%m-%d") for s in recent
    ]
    before = [s["pain_before"] for s in recent]
    after = [s["pain_after"] for s in recent]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=labels, y=before, name="訓練前",
        marker_color=COLORS["danger"],
    ))
    fig.add_trace(go.Bar(
        x=labels, y=after, name="訓練後",
        marker_color=COLORS["primary"],
    ))
    fig.update_layout(
        **_layout_base(280),
        barmode="group",
        yaxis=dict(range=[0, 10], gridcolor="#eef2f7", title="疼痛分數 (0-10)"),
        legend=dict(orientation="h", y=1.15),
    )
    return fig


# ============================================================
# Apple Activity Rings & Level Badge
# ============================================================
def activity_rings(done: int, goal: int, streak: int, color: str = "#007aff", lang: str = "zh") -> None:
    """3 concentric animated rings: activity completion, streak, and score."""
    size = 140
    center = size / 2
    radius_activity = 45
    radius_streak = 60
    radius_score = 75

    stroke_width = 10

    activity_pct = min(1.0, done / goal) if goal > 0 else 0
    streak_pct = min(1.0, streak / 7)
    score_pct = min(1.0, done / 100) if goal == 100 else activity_pct

    def ring_path(r: float, pct: float, color_ring: str) -> str:
        circumference = 2 * 3.14159 * r
        offset = circumference * (1 - pct)
        return (
            f'<circle cx="{center}" cy="{center}" r="{r}" fill="none" '
            f'stroke="{color_ring}" stroke-width="{stroke_width}" '
            f'stroke-dasharray="{circumference}" '
            f'stroke-dashoffset="{offset}" '
            f'stroke-linecap="round" '
            f'style="transition: stroke-dashoffset 0.6s cubic-bezier(0.2,0.8,0.2,1);" />'
        )

    colors = {
        "activity": color,
        "streak": "#FF9500",
        "score": "#34C759",
    }

    svg = f'''
    <svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" style="filter: drop-shadow(0 2px 8px rgba(0,0,0,0.08));">
        <!-- Background circle for rings -->
        <circle cx="{center}" cy="{center}" r="{radius_activity}" fill="none" stroke="rgba(0,0,0,0.08)" stroke-width="{stroke_width}" />
        <circle cx="{center}" cy="{center}" r="{radius_streak}" fill="none" stroke="rgba(0,0,0,0.08)" stroke-width="{stroke_width}" />
        <circle cx="{center}" cy="{center}" r="{radius_score}" fill="none" stroke="rgba(0,0,0,0.08)" stroke-width="{stroke_width}" />

        <!-- Activity ring -->
        {ring_path(radius_activity, activity_pct, colors['activity'])}

        <!-- Streak ring -->
        {ring_path(radius_streak, streak_pct, colors['streak'])}

        <!-- Score ring -->
        {ring_path(radius_score, score_pct, colors['score'])}

        <!-- Center text -->
        <text x="{center}" y="{center - 8}" text-anchor="middle" font-size="28" font-weight="800" fill="#1c1c1e" letter-spacing="-0.02em">
            {done}
        </text>
        <text x="{center}" y="{center + 18}" text-anchor="middle" font-size="12" font-weight="600" fill="#8e8e93">
            / {goal}
        </text>
    </svg>
    '''

    stats_html = f'''
    <div style="flex: 1;">
        <div style="margin-bottom: 12px; font-size: 13px; color: #8e8e93; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">
            {'今日進度' if lang == 'zh' else 'Today'}
        </div>
        <div style="margin-bottom: 10px; font-size: 14px; color: #666;">
            <span style="color: {color}; font-weight: 700;">{done}/{goal}</span> {'完成' if lang == 'zh' else 'completed'}
        </div>
        <div style="margin-bottom: 10px; font-size: 14px; color: #666;">
            <span style="color: #FF9500; font-weight: 700;">{streak}</span> {'連續天' if lang == 'zh' else 'day streak'}
        </div>
        <div style="font-size: 14px; color: #666;">
            <span style="color: #34C759; font-weight: 700;">{int(score_pct * 100)}%</span> {'本週進度' if lang == 'zh' else 'week progress'}
        </div>
    </div>
    '''

    st.markdown(
        f'<div class="activity-rings-container">'
        f'<div class="activity-rings-svg">{svg}</div>'
        f'{stats_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def level_badge(level_info: Dict, lang: str = "zh") -> None:
    """Display XP level with progress bar to next level."""
    level_num = level_info.get("level", 0)
    level_name = level_info.get("name_zh", "初學者") if lang == "zh" else level_info.get("name_en", "Beginner")
    level_icon = level_info.get("icon", "🥉")
    current_xp = level_info.get("current_xp", 0)
    xp_for_next = level_info.get("xp_for_next", 100)
    total_xp = level_info.get("total_xp", 0)

    progress_pct = min(100, int((current_xp / xp_for_next * 100))) if xp_for_next > 0 else 0

    badge_html = f'''
    <div class="level-badge-container">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
            <div style="font-size: 32px;">{level_icon}</div>
            <div>
                <div class="level-badge-text">{level_name}</div>
                <div style="font-size: 13px; opacity: 0.85;">Lv. {level_num}</div>
            </div>
        </div>
        <div style="background: rgba(255,255,255,0.2); border-radius: 10px; padding: 8px; margin-bottom: 8px;">
            <div style="font-size: 12px; margin-bottom: 6px; opacity: 0.9;">{current_xp} / {xp_for_next} XP</div>
            <div class="xp-progress">
                <div class="xp-progress-bar" style="width: {progress_pct}%;"></div>
            </div>
        </div>
        <div style="font-size: 12px; opacity: 0.85; text-align: center;">
            {('總計' if lang == 'zh' else 'Total')} {total_xp} XP
        </div>
    </div>
    '''

    st.markdown(badge_html, unsafe_allow_html=True)


def xp_toast(xp_amount: int) -> None:
    """Show XP gain notification with animation."""
    toast_html = f'''
    <div style="position: fixed; bottom: 80px; right: 20px; background: rgba(52, 199, 89, 0.95);
                color: white; padding: 12px 20px; border-radius: 14px; font-weight: 700;
                font-size: 16px; box-shadow: 0 8px 24px rgba(0,0,0,0.2);
                backdrop-filter: blur(20px); z-index: 9999;
                animation: slideUp 0.4s cubic-bezier(0.2,0.8,0.2,1);
                animation-fill-mode: forwards;">
        +{xp_amount} XP
    </div>
    <style>
        @keyframes slideUp {{
            from {{ opacity: 0; transform: translateY(20px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
    </style>
    '''
    st.markdown(toast_html, unsafe_allow_html=True)
