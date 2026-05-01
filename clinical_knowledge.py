"""
Clinical knowledge base: curated rehab content + semantic search.

Loaded into the vector store so the AI chat / agentic AI can retrieve
relevant snippets per question.

Content categories:
- exercises: technique notes, target muscles, progression, contraindications
- conditions: stroke, hip replacement, knee surgery, frozen shoulder, etc.
- safety: red flags, when to stop, when to call doctor
- biomech: ROM norms, common compensations, asymmetry causes
- nutrition: recovery-relevant tips, hydration, micronutrients
- sleep: recovery dependence on sleep quality

Each entry: id, category, lang, title, body, tags, source_attribution.

Seed dataset is bilingual (zh/en) and ships in this file. Therapists can
add more via add_entry().
"""
from __future__ import annotations
import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np

from db import execute_query, execute_update


@dataclass
class KnowledgeEntry:
    id: str
    category: str  # exercise / condition / safety / biomech / nutrition / sleep
    lang: str      # zh / en
    title: str
    body: str
    tags: List[str] = field(default_factory=list)
    source: str = "internal"


# ============================================================
# Seed dataset
# ============================================================
SEED_ENTRIES: List[KnowledgeEntry] = [
    # Exercises
    KnowledgeEntry(
        id="ex_arm_raise_zh",
        category="exercise", lang="zh",
        title="肩前舉動作要領",
        body="坐姿或站姿，雙手自然下垂。慢慢將手臂向前抬起，"
             "保持手肘伸直，抬至耳朵旁停留 1 秒再緩慢放下。"
             "每組 10-15 下，2-3 組。注意：避免聳肩、軀幹後仰。"
             "正常活動範圍 0-180°，肩夾擠症候群者上限為 90°。",
        tags=["arm_raise", "shoulder", "upper_body"],
    ),
    KnowledgeEntry(
        id="ex_mini_squat_zh",
        category="exercise", lang="zh",
        title="迷你蹲動作要領",
        body="雙腳與肩同寬。膝蓋對齊腳尖，緩慢屈膝 30-45°，"
             "保持背部直立、重心於足跟。膝關節屈曲 60° 內，"
             "膝部不要超過腳尖。每組 10-15 下。"
             "髖膝置換術後 2 週內請避免。",
        tags=["mini_squat", "knee", "lower_body"],
    ),
    KnowledgeEntry(
        id="ex_sit_to_stand_zh",
        category="exercise", lang="zh",
        title="坐到站動作要領",
        body="坐於椅前 2/3，雙腳平踏地面。身體前傾，"
             "雙手交叉於胸前，膝蓋彎曲約 90°。"
             "用大腿力量站起，至完全伸直再緩慢坐下。"
             "膝關節屈曲 ROM 至少 90°。每組 5-10 下。",
        tags=["sit_to_stand", "knee", "hip", "functional"],
    ),
    # Conditions
    KnowledgeEntry(
        id="cond_stroke_zh",
        category="condition", lang="zh",
        title="中風後復健",
        body="重點在於受影響側的關節活動度與肌力恢復。"
             "強調：1) 早期被動 ROM，2) 主動輔助，3) 主動 ROM，"
             "4) 阻力訓練。注意肌肉張力 (spasticity) 與痙攣。"
             "每日 30-60 分鐘，逐步增加。",
        tags=["stroke", "hemiparesis", "neurological"],
    ),
    KnowledgeEntry(
        id="cond_knee_replacement_zh",
        category="condition", lang="zh",
        title="膝關節置換術後",
        body="術後 0-2 週：被動屈膝 90°、伸直 0°。"
             "2-6 週：主動屈膝 110°、強化股四頭肌。"
             "6-12 週：功能性訓練（坐到站、上下樓）。"
             "禁忌：劇烈衝擊運動 3 個月內、深蹲 90° 以下。",
        tags=["knee_replacement", "tka", "post_surgery"],
    ),
    KnowledgeEntry(
        id="cond_frozen_shoulder_zh",
        category="condition", lang="zh",
        title="五十肩 / 沾黏性關節囊炎",
        body="分三期：1) 凍結期（疼痛主導，輕柔 ROM），"
             "2) 凍結完全（活動受限，加強伸展），"
             "3) 解凍期（恢復，加重訓練）。"
             "急性期避免劇烈伸展，每日鐘擺運動 + 牆爬。",
        tags=["frozen_shoulder", "shoulder", "capsulitis"],
    ),
    # Safety / red flags
    KnowledgeEntry(
        id="safety_red_flags_zh",
        category="safety", lang="zh",
        title="運動中需立即停止的徵兆",
        body="1) 胸悶、胸痛、呼吸困難 → 停止並就醫\n"
             "2) 頭暈、視力模糊 → 坐下休息\n"
             "3) 關節劇痛或腫脹 → 冰敷並聯絡治療師\n"
             "4) 心跳超過 (220-年齡) × 0.85 → 降低強度\n"
             "5) 動作中突然麻木或刺痛 → 停止並評估",
        tags=["safety", "red_flag", "emergency"],
    ),
    KnowledgeEntry(
        id="safety_pain_scale_zh",
        category="safety", lang="zh",
        title="疼痛量表使用",
        body="0-3 分：可接受，繼續訓練\n"
             "4-6 分：減半強度或範圍\n"
             "7-10 分：停止訓練，記錄並聯絡治療師\n"
             "訓練後疼痛應在 1 小時內回到基準線；"
             "若持續超過 2 小時表示強度過高。",
        tags=["pain", "rpe", "borg"],
    ),
    # Biomechanics
    KnowledgeEntry(
        id="biomech_rom_zh",
        category="biomech", lang="zh",
        title="關節正常活動範圍",
        body="肩關節：屈曲 0-180°、伸直 0-60°、外展 0-180°、內外旋 0-90°\n"
             "肘關節：屈曲 0-150°\n"
             "髖關節：屈曲 0-120°、伸直 0-30°、外展 0-45°\n"
             "膝關節：屈曲 0-135°\n"
             "踝關節：背屈 0-20°、蹠屈 0-50°",
        tags=["rom", "norms", "anatomy"],
    ),
    KnowledgeEntry(
        id="biomech_compensation_zh",
        category="biomech", lang="zh",
        title="常見代償動作",
        body="1) 蹲下時膝外翻：髖外展肌無力\n"
             "2) 走路骨盆下降：對側臀中肌無力\n"
             "3) 抬臂時聳肩：肩袖肌群弱\n"
             "4) 站起時軀幹過度前傾：股四頭肌弱或膝痛\n"
             "5) 雙側不對稱 >15°：肌力或活動度不平衡",
        tags=["compensation", "dysfunction", "asymmetry"],
    ),
    # Nutrition / sleep
    KnowledgeEntry(
        id="nutr_recovery_zh",
        category="nutrition", lang="zh",
        title="復健期飲食原則",
        body="蛋白質：每公斤體重 1.2-1.6g/日（肌肉修復）\n"
             "Omega-3：抗發炎，鮭魚、亞麻仁籽\n"
             "鈣 + 維生素 D：骨骼修復，1000mg/日 + 600 IU\n"
             "水：每公斤 30-35 ml/日\n"
             "避免：過量酒精、高糖飲食（影響睡眠與發炎）",
        tags=["nutrition", "protein", "recovery"],
    ),
    KnowledgeEntry(
        id="sleep_recovery_zh",
        category="sleep", lang="zh",
        title="睡眠對恢復的影響",
        body="深度睡眠期間，生長激素分泌達峰值，促進組織修復。"
             "建議 7-9 小時 / 夜。睡眠不足將：\n"
             "- 增加肌肉痛覺敏感度 (+25%)\n"
             "- 降低肌肉合成 (-18%)\n"
             "- 延長傷後恢復時間\n"
             "策略：固定就寢時間、訓練後 4 小時內補充蛋白質。",
        tags=["sleep", "recovery", "growth_hormone"],
    ),
]

# English translations for the same entries
SEED_ENTRIES_EN: List[KnowledgeEntry] = [
    KnowledgeEntry(
        id="ex_arm_raise_en", category="exercise", lang="en",
        title="Arm Raise — Form Notes",
        body="Sitting or standing, arms relaxed at sides. Slowly raise "
             "arms forward keeping elbows straight, hold 1 second at "
             "ear level, lower slowly. 10-15 reps × 2-3 sets. Avoid "
             "shoulder shrug or trunk extension. Normal ROM 0-180°; "
             "with shoulder impingement cap at 90°.",
        tags=["arm_raise", "shoulder", "upper_body"],
    ),
    KnowledgeEntry(
        id="cond_knee_replacement_en", category="condition", lang="en",
        title="Post-TKA (Knee Replacement) Rehab",
        body="Weeks 0-2: passive flexion to 90°, full extension. "
             "Weeks 2-6: active flexion to 110°, quad strengthening. "
             "Weeks 6-12: functional (sit-to-stand, stairs). "
             "Avoid: high-impact for 3 months, deep squat <90°.",
        tags=["knee_replacement", "tka", "post_surgery"],
    ),
    KnowledgeEntry(
        id="safety_red_flags_en", category="safety", lang="en",
        title="Stop-and-Seek-Care Signs",
        body="1) Chest pain/pressure or trouble breathing — stop, call doctor\n"
             "2) Dizziness or vision changes — sit down\n"
             "3) Sharp joint pain or swelling — ice, contact therapist\n"
             "4) HR > (220 - age) × 0.85 — reduce intensity\n"
             "5) Sudden numbness/tingling — stop and assess",
        tags=["safety", "red_flag", "emergency"],
    ),
    KnowledgeEntry(
        id="biomech_rom_en", category="biomech", lang="en",
        title="Normal Joint ROM Reference",
        body="Shoulder: flex 0-180°, ext 0-60°, abd 0-180°, rot 0-90°\n"
             "Elbow: flexion 0-150°\n"
             "Hip: flex 0-120°, ext 0-30°, abd 0-45°\n"
             "Knee: flexion 0-135°\n"
             "Ankle: dorsiflex 0-20°, plantarflex 0-50°",
        tags=["rom", "norms", "anatomy"],
    ),
]


# ============================================================
# Index management
# ============================================================
_INDEXED = False


def init_knowledge_base(force_reindex: bool = False) -> int:
    """Index seed entries into the vector store. Returns count indexed."""
    global _INDEXED
    if _INDEXED and not force_reindex:
        return 0

    from vector_db import get_store, VectorEntry
    from embeddings import get_service

    service = get_service()
    store = get_store(dim=service.text_dim)

    if force_reindex:
        store.delete_namespace("knowledge")

    all_entries = SEED_ENTRIES + SEED_ENTRIES_EN
    db_entries = _load_custom_entries()
    all_entries.extend(db_entries)

    if not all_entries:
        return 0

    texts = [f"{e.title}\n{e.body}\n{' '.join(e.tags)}" for e in all_entries]
    embeddings = service.embed_texts(texts)

    for entry, vec in zip(all_entries, embeddings):
        store.upsert(VectorEntry(
            id=f"kb:{entry.id}",
            vector=vec,
            payload=asdict(entry),
            namespace="knowledge",
        ))

    _INDEXED = True
    return len(all_entries)


def search(query: str, top_k: int = 5,
            category: Optional[str] = None,
            lang: Optional[str] = None) -> List[Dict]:
    """Semantic search across the knowledge base."""
    from vector_db import get_store
    from embeddings import get_service

    if not _INDEXED:
        init_knowledge_base()

    service = get_service()
    store = get_store(dim=service.text_dim)

    q_vec = service.embed_text(query)

    def filter_fn(payload: Dict) -> bool:
        if category and payload.get("category") != category:
            return False
        if lang and payload.get("lang") != lang:
            return False
        return True

    results = store.query(
        q_vec,
        top_k=top_k,
        namespace="knowledge",
        filter_fn=filter_fn,
    )

    return [
        {
            **entry.payload,
            "similarity": round(score, 3),
        }
        for entry, score in results
    ]


def add_entry(entry: KnowledgeEntry, persist: bool = True) -> bool:
    """Add a custom knowledge entry. Persists to DB if requested."""
    from vector_db import get_store, VectorEntry
    from embeddings import get_service

    service = get_service()
    store = get_store(dim=service.text_dim)

    text = f"{entry.title}\n{entry.body}\n{' '.join(entry.tags)}"
    vec = service.embed_text(text)

    store.upsert(VectorEntry(
        id=f"kb:{entry.id}",
        vector=vec,
        payload=asdict(entry),
        namespace="knowledge",
    ))

    if persist:
        try:
            execute_update(
                """
                INSERT OR REPLACE INTO offline_cache
                (user_id, cache_type, data_json, expires_at)
                VALUES ('_kb', ?, ?, datetime('now', '+10 years'))
                """,
                (
                    f"kb_entry_{entry.id}",
                    json.dumps(asdict(entry), ensure_ascii=False),
                ),
            )
        except Exception:
            pass

    return True


def _load_custom_entries() -> List[KnowledgeEntry]:
    """Load admin-added entries from DB."""
    try:
        rows = execute_query(
            """
            SELECT data_json FROM offline_cache
            WHERE user_id = '_kb' AND cache_type LIKE 'kb_entry_%'
            """,
            (),
        )
    except Exception:
        return []

    entries = []
    for row in rows:
        try:
            data = json.loads(row["data_json"])
            entries.append(KnowledgeEntry(**data))
        except Exception:
            continue
    return entries


def get_categories() -> List[str]:
    return ["exercise", "condition", "safety", "biomech",
            "nutrition", "sleep"]


def kb_stats() -> Dict:
    """Quick stats."""
    from vector_db import get_store
    from embeddings import get_service
    store = get_store(dim=get_service().text_dim)
    return {
        "indexed": _INDEXED,
        "total_entries": store.count("knowledge"),
        "seed_entries": len(SEED_ENTRIES) + len(SEED_ENTRIES_EN),
    }
