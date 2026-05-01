"""
Lightweight vector database for similarity search.

Storage tiers (auto-selected by what's installed):
1. sqlite-vec — best: columnar, ANN, sqlite-native
2. FAISS — fallback: in-memory + index file persistence
3. numpy — last resort: brute-force cosine, fine for ≤100k vectors

Use cases:
- Find similar past sessions for a patient
- Retrieve relevant clinical knowledge for AI chat (RAG)
- Match free-text exercise descriptions to template library
- Semantic search across notes/journal entries

Each entry: {id, vector, payload, namespace, user_id?}
Namespaces: "sessions", "exercises", "knowledge", "journal", "templates"
"""
from __future__ import annotations
import json
import math
import hashlib
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import numpy as np


@dataclass
class VectorEntry:
    id: str
    vector: np.ndarray
    payload: Dict[str, Any]
    namespace: str
    user_id: Optional[str] = None
    created_at: Optional[str] = None


# ============================================================
# Backend selection
# ============================================================
def _detect_backend() -> str:
    """Pick best available backend."""
    try:
        import sqlite_vec  # noqa: F401
        return "sqlite-vec"
    except ImportError:
        pass
    try:
        import faiss  # noqa: F401
        return "faiss"
    except ImportError:
        pass
    return "numpy"


_BACKEND = _detect_backend()


# ============================================================
# Numpy backend (always available)
# ============================================================
class NumpyVectorStore:
    """Brute-force cosine similarity. Fine for ≤100k vectors."""

    def __init__(self, dim: int, persist_path: Optional[str] = None):
        self.dim = dim
        self.persist_path = persist_path
        self._vectors: Dict[str, np.ndarray] = {}
        self._payloads: Dict[str, Dict] = {}
        self._namespaces: Dict[str, str] = {}
        self._users: Dict[str, Optional[str]] = {}
        self._lock = threading.RLock()

    def upsert(self, entry: VectorEntry) -> None:
        with self._lock:
            v = entry.vector.astype(np.float32)
            n = np.linalg.norm(v)
            if n > 1e-9:
                v = v / n
            self._vectors[entry.id] = v
            self._payloads[entry.id] = entry.payload
            self._namespaces[entry.id] = entry.namespace
            self._users[entry.id] = entry.user_id
            self._persist()

    def query(self, vector: np.ndarray, top_k: int = 5,
              namespace: Optional[str] = None,
              user_id: Optional[str] = None,
              filter_fn: Optional[Callable[[Dict], bool]] = None
              ) -> List[Tuple[VectorEntry, float]]:
        with self._lock:
            if not self._vectors:
                return []

            q = vector.astype(np.float32)
            qn = np.linalg.norm(q)
            if qn > 1e-9:
                q = q / qn

            results = []
            for vid, v in self._vectors.items():
                if namespace and self._namespaces.get(vid) != namespace:
                    continue
                if user_id and self._users.get(vid) != user_id:
                    continue
                if filter_fn and not filter_fn(self._payloads.get(vid, {})):
                    continue

                sim = float(np.dot(q, v))
                results.append((vid, sim))

            results.sort(key=lambda x: -x[1])
            top = results[:top_k]

            return [
                (
                    VectorEntry(
                        id=vid,
                        vector=self._vectors[vid],
                        payload=self._payloads[vid],
                        namespace=self._namespaces[vid],
                        user_id=self._users.get(vid),
                    ),
                    sim,
                )
                for vid, sim in top
            ]

    def delete(self, entry_id: str) -> bool:
        with self._lock:
            removed = self._vectors.pop(entry_id, None) is not None
            self._payloads.pop(entry_id, None)
            self._namespaces.pop(entry_id, None)
            self._users.pop(entry_id, None)
            if removed:
                self._persist()
            return removed

    def delete_namespace(self, namespace: str) -> int:
        with self._lock:
            ids = [vid for vid, ns in self._namespaces.items()
                   if ns == namespace]
            for vid in ids:
                self.delete(vid)
            return len(ids)

    def count(self, namespace: Optional[str] = None) -> int:
        with self._lock:
            if namespace is None:
                return len(self._vectors)
            return sum(1 for ns in self._namespaces.values() if ns == namespace)

    def save(self, path: str) -> None:
        with self._lock:
            data = {
                "dim": self.dim,
                "vectors": {k: v.tolist() for k, v in self._vectors.items()},
                "payloads": self._payloads,
                "namespaces": self._namespaces,
                "users": self._users,
            }
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, default=str)

    def load(self, path: str) -> bool:
        if not Path(path).exists():
            return False
        with self._lock:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._vectors = {k: np.array(v, dtype=np.float32)
                            for k, v in data.get("vectors", {}).items()}
            self._payloads = data.get("payloads", {})
            self._namespaces = data.get("namespaces", {})
            self._users = data.get("users", {})
            return True

    def _persist(self) -> None:
        if not self.persist_path:
            return
        try:
            self.save(self.persist_path)
        except Exception:
            pass


# ============================================================
# SQLite-vec backend (best when available)
# ============================================================
class SqliteVecStore:
    """Native SQLite vector backend. Persistent, ANN-capable."""

    def __init__(self, db_path: str = "vector_store.db", dim: int = 768):
        self.dim = dim
        self.db_path = db_path
        self._lock = threading.RLock()

        try:
            import sqlite_vec
        except ImportError:
            raise RuntimeError("sqlite-vec not available")

        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.enable_load_extension(True)
        sqlite_vec.load(self._conn)
        self._conn.enable_load_extension(False)
        self._init_tables()

    @staticmethod
    def _stable_rowid(entry_id: str) -> int:
        digest = hashlib.sha256(entry_id.encode("utf-8")).hexdigest()[:16]
        return int(digest, 16) % (2 ** 63 - 1) + 1

    def _init_tables(self) -> None:
        with self._lock:
            self._conn.executescript(f"""
                CREATE TABLE IF NOT EXISTS vec_entries (
                    id TEXT PRIMARY KEY,
                    vector_rowid INTEGER UNIQUE,
                    namespace TEXT NOT NULL,
                    user_id TEXT,
                    payload TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_ns_user
                    ON vec_entries(namespace, user_id);
                CREATE VIRTUAL TABLE IF NOT EXISTS vec_index
                    USING vec0(embedding float[{self.dim}]);
            """)
            existing = {
                row[1]
                for row in self._conn.execute("PRAGMA table_info(vec_entries)")
            }
            if "vector_rowid" not in existing:
                self._conn.execute(
                    "ALTER TABLE vec_entries ADD COLUMN vector_rowid INTEGER"
                )
                self._conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_vec_entries_rowid "
                    "ON vec_entries(vector_rowid)"
                )
                # Old builds used Python hash() as rowid, which is process-random.
                # The existing vec_index rows cannot be joined reliably, so the
                # next upsert/reindex should repopulate them with stable rowids.
                self._conn.execute("DELETE FROM vec_index")
                for (entry_id,) in self._conn.execute(
                    "SELECT id FROM vec_entries WHERE vector_rowid IS NULL"
                ).fetchall():
                    self._conn.execute(
                        "UPDATE vec_entries SET vector_rowid = ? WHERE id = ?",
                        (self._stable_rowid(entry_id), entry_id),
                    )
            self._conn.commit()

    def upsert(self, entry: VectorEntry) -> None:
        with self._lock:
            v = entry.vector.astype(np.float32).tolist()
            rowid = self._stable_rowid(entry.id)
            self._conn.execute(
                "INSERT OR REPLACE INTO vec_entries "
                "(id, vector_rowid, namespace, user_id, payload) "
                "VALUES (?, ?, ?, ?, ?)",
                (entry.id, rowid, entry.namespace, entry.user_id,
                 json.dumps(entry.payload, ensure_ascii=False, default=str)),
            )
            self._conn.execute("DELETE FROM vec_index WHERE rowid = ?",
                              (rowid,))
            self._conn.execute(
                "INSERT INTO vec_index(rowid, embedding) VALUES (?, ?)",
                (rowid, json.dumps(v)),
            )
            self._conn.commit()

    def query(self, vector: np.ndarray, top_k: int = 5,
              namespace: Optional[str] = None,
              user_id: Optional[str] = None,
              filter_fn: Optional[Callable[[Dict], bool]] = None
              ) -> List[Tuple[VectorEntry, float]]:
        with self._lock:
            v = vector.astype(np.float32).tolist()
            cur = self._conn.execute(
                """
                SELECT e.id, e.namespace, e.user_id, e.payload,
                       e.created_at, vec_distance_l2(vec_index.embedding, ?)
                       AS dist
                FROM vec_index
                JOIN vec_entries e ON e.vector_rowid = vec_index.rowid
                ORDER BY dist
                LIMIT ?
                """,
                (json.dumps(v), top_k * 4),
            )
            results = []
            for row in cur.fetchall():
                if namespace and row[1] != namespace:
                    continue
                if user_id and row[2] != user_id:
                    continue
                payload = json.loads(row[3]) if row[3] else {}
                if filter_fn and not filter_fn(payload):
                    continue
                sim = 1.0 / (1.0 + float(row[5]))
                entry = VectorEntry(
                    id=row[0], vector=np.array(v, dtype=np.float32),
                    payload=payload, namespace=row[1],
                    user_id=row[2], created_at=row[4],
                )
                results.append((entry, sim))
                if len(results) >= top_k:
                    break
            return results

    def delete(self, entry_id: str) -> bool:
        with self._lock:
            self._conn.execute(
                "DELETE FROM vec_index WHERE rowid = ?",
                (self._stable_rowid(entry_id),),
            )
            cur = self._conn.execute(
                "DELETE FROM vec_entries WHERE id = ?", (entry_id,)
            )
            self._conn.commit()
            return cur.rowcount > 0

    def delete_namespace(self, namespace: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id FROM vec_entries WHERE namespace = ?",
                (namespace,),
            )
            ids = [row[0] for row in cur.fetchall()]
            for vid in ids:
                self.delete(vid)
            return len(ids)

    def count(self, namespace: Optional[str] = None) -> int:
        with self._lock:
            if namespace:
                cur = self._conn.execute(
                    "SELECT COUNT(*) FROM vec_entries WHERE namespace = ?",
                    (namespace,),
                )
            else:
                cur = self._conn.execute("SELECT COUNT(*) FROM vec_entries")
            return cur.fetchone()[0]


# ============================================================
# Public store factory
# ============================================================
_STORE_INSTANCES: Dict[str, Any] = {}


def get_store(dim: int = 768, backend: Optional[str] = None,
              path: str = "data/vector_store.db") -> Any:
    """Get a vector store instance (singleton per backend, dim, and path)."""
    backend = backend or _BACKEND
    cache_key = f"{backend}_{dim}_{Path(path).resolve()}"

    if cache_key in _STORE_INSTANCES:
        return _STORE_INSTANCES[cache_key]

    if backend == "sqlite-vec":
        try:
            store = SqliteVecStore(path, dim=dim)
        except Exception:
            json_path = path.replace(".db", "_np.json")
            store = NumpyVectorStore(dim=dim, persist_path=json_path)
            store.load(json_path)
    else:
        json_path = path.replace(".db", "_np.json")
        store = NumpyVectorStore(dim=dim, persist_path=json_path)
        try:
            store.load(json_path)
        except Exception:
            pass

    _STORE_INSTANCES[cache_key] = store
    return store


def get_backend() -> str:
    """Return name of currently active backend."""
    return _BACKEND


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    a = a.astype(np.float32)
    b = b.astype(np.float32)
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return float(np.dot(a, b) / (na * nb))
