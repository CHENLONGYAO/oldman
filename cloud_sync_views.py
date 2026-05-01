"""
Cloud sync UI: backup creation, restore, provider config.
"""
import streamlit as st
import pandas as pd
from pathlib import Path

from auth import get_session_user
from cloud_sync import (
    create_backup, restore_backup, apply_restore,
    list_backups, delete_backup,
    upload_to_drive, upload_to_s3, upload_to_webdav,
    schedule_auto_backup,
    BACKUP_DIR,
)


def view_cloud_sync():
    """Cloud sync / backup view."""
    user = get_session_user()
    if not user:
        st.error("請先登入")
        return

    lang = st.session_state.get("settings", {}).get("lang", "zh")
    user_id = user["user_id"]

    st.title("☁️ " + ("雲端備份" if lang == "zh" else "Cloud Backup"))

    auto = schedule_auto_backup(user_id, interval_days=7)
    if auto["due"]:
        st.warning(
            "⏰ 建議建立備份（距離上次超過 7 天）" if lang == "zh"
            else "⏰ Backup recommended (over 7 days since last)"
        )
    elif auto.get("next_in_days") is not None:
        st.info(
            f"✓ 下次自動備份將在 {auto['next_in_days']} 天後" if lang == "zh"
            else f"✓ Next auto-backup in {auto['next_in_days']} days"
        )

    tab_create, tab_restore, tab_providers = st.tabs([
        "📥 " + ("建立備份" if lang == "zh" else "Create Backup"),
        "📤 " + ("還原備份" if lang == "zh" else "Restore"),
        "🌐 " + ("雲端提供者" if lang == "zh" else "Cloud Providers"),
    ])

    with tab_create:
        _render_create_tab(user_id, lang)

    with tab_restore:
        _render_restore_tab(user_id, lang)

    with tab_providers:
        _render_providers_tab(user_id, lang)


def _render_create_tab(user_id: str, lang: str) -> None:
    st.subheader("🔐 " + ("加密備份" if lang == "zh" else "Encrypted Backup"))
    st.caption(
        "備份會以您的密碼加密。請妥善保管 — 遺失將無法還原。"
        if lang == "zh" else
        "Backups are encrypted with your passphrase. Keep it safe — "
        "lost passphrase = lost data."
    )

    passphrase = st.text_input(
        "密碼" if lang == "zh" else "Passphrase",
        type="password",
        key="backup_pass",
        help="至少 8 個字元" if lang == "zh" else "At least 8 characters",
    )

    confirm = st.text_input(
        "確認密碼" if lang == "zh" else "Confirm Passphrase",
        type="password",
        key="backup_pass_confirm",
    )

    if st.button(
        "🚀 " + ("立即建立備份" if lang == "zh" else "Create Backup Now"),
        type="primary",
        use_container_width=True,
        disabled=not (passphrase and len(passphrase) >= 8),
    ):
        if passphrase != confirm:
            st.error("密碼不一致" if lang == "zh" else "Passphrases don't match")
        else:
            with st.spinner("加密並建立備份..." if lang == "zh"
                            else "Encrypting and creating backup..."):
                path, meta = create_backup(user_id, passphrase)
            st.success(
                f"✓ 備份成功 ({meta['size_kb']} KB)" if lang == "zh"
                else f"✓ Backup created ({meta['size_kb']} KB)"
            )

            with open(path, "rb") as f:
                st.download_button(
                    "💾 " + ("下載備份檔" if lang == "zh"
                             else "Download Backup File"),
                    data=f.read(),
                    file_name=path.name,
                    mime="application/octet-stream",
                )

            with st.expander("詳細資訊" if lang == "zh" else "Details"):
                df = pd.DataFrame(
                    [{"table": k, "rows": v} for k, v in meta["tables"].items()]
                )
                st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("📁 " + ("本地備份" if lang == "zh" else "Local Backups"))

    backups = list_backups(user_id)
    if not backups:
        st.info("尚無備份" if lang == "zh" else "No backups yet")
        return

    df = pd.DataFrame(backups)
    st.dataframe(df, use_container_width=True, hide_index=True)

    to_delete = st.selectbox(
        "刪除備份" if lang == "zh" else "Delete backup",
        options=[""] + [b["filename"] for b in backups],
    )
    if to_delete and st.button(
        "🗑️ " + ("確認刪除" if lang == "zh" else "Confirm Delete"),
        type="secondary",
    ):
        if delete_backup(to_delete):
            st.success("已刪除" if lang == "zh" else "Deleted")
            st.rerun()


def _render_restore_tab(user_id: str, lang: str) -> None:
    st.subheader("📥 " + ("還原備份" if lang == "zh" else "Restore Backup"))
    st.warning(
        "還原會將備份中的資料合併到目前帳戶。"
        if lang == "zh" else
        "Restore merges backup data into your current account."
    )

    backups = list_backups(user_id)
    source = st.radio(
        "來源" if lang == "zh" else "Source",
        ["local", "upload"],
        format_func=lambda s: (
            "本地備份" if s == "local" and lang == "zh" else
            "Local Backup" if s == "local" else
            "上傳檔案" if lang == "zh" else "Upload File"
        ),
        horizontal=True,
    )

    selected_path = None
    if source == "local":
        if not backups:
            st.info("無本地備份" if lang == "zh" else "No local backups")
            return
        chosen = st.selectbox(
            "選擇備份" if lang == "zh" else "Select backup",
            options=[b["filename"] for b in backups],
        )
        if chosen:
            selected_path = Path(BACKUP_DIR) / chosen
    else:
        uploaded = st.file_uploader(
            "上傳 .enc 檔案" if lang == "zh" else "Upload .enc file",
            type=["enc"],
        )
        if uploaded:
            tmp_path = BACKUP_DIR / f"_tmp_restore_{user_id[:8]}.enc"
            tmp_path.write_bytes(uploaded.read())
            selected_path = tmp_path

    if selected_path:
        passphrase = st.text_input(
            "解密密碼" if lang == "zh" else "Decryption Passphrase",
            type="password",
            key="restore_pass",
        )

        overwrite = st.checkbox(
            "覆寫現有資料 (危險)" if lang == "zh"
            else "Overwrite existing data (DANGER)",
            value=False,
        )

        if st.button(
            "🔓 " + ("還原" if lang == "zh" else "Restore"),
            type="primary",
            disabled=not passphrase,
        ):
            with st.spinner("解密中..." if lang == "zh" else "Decrypting..."):
                data = restore_backup(selected_path, passphrase)

            if not data:
                st.error(
                    "解密失敗 — 檢查密碼是否正確"
                    if lang == "zh"
                    else "Decryption failed — check passphrase"
                )
            else:
                with st.spinner("套用資料..." if lang == "zh"
                                else "Applying data..."):
                    counts = apply_restore(data, user_id, overwrite=overwrite)

                st.success("✓ " + ("還原完成" if lang == "zh" else "Restored"))
                df = pd.DataFrame(
                    [{"table": k, "rows_restored": v} for k, v in counts.items()]
                )
                st.dataframe(df, use_container_width=True, hide_index=True)


def _render_providers_tab(user_id: str, lang: str) -> None:
    st.subheader("🌐 " + ("雲端提供者" if lang == "zh" else "Cloud Providers"))
    st.caption(
        "上傳已建立的本地備份檔到雲端服務。"
        if lang == "zh" else
        "Upload existing local backup files to cloud services."
    )

    backups = list_backups(user_id)
    if not backups:
        st.info(
            "請先建立備份" if lang == "zh"
            else "Create a backup first"
        )
        return

    chosen = st.selectbox(
        "選擇備份" if lang == "zh" else "Select backup",
        options=[b["filename"] for b in backups],
        key="cloud_select",
    )
    chosen_path = Path(BACKUP_DIR) / chosen if chosen else None

    provider = st.radio(
        "提供者" if lang == "zh" else "Provider",
        ["drive", "s3", "webdav"],
        format_func=lambda p: {
            "drive": "Google Drive", "s3": "S3", "webdav": "WebDAV"
        }[p],
        horizontal=True,
    )

    if provider == "drive":
        folder_id = st.text_input(
            "資料夾 ID (選填)" if lang == "zh" else "Folder ID (optional)",
        )
        if st.button("☁️ Upload to Drive", type="primary",
                     disabled=not chosen_path):
            with st.spinner("上傳中..." if lang == "zh" else "Uploading..."):
                fid = upload_to_drive(chosen_path, folder_id or None)
            if fid:
                st.success(f"✓ Uploaded — file ID: `{fid}`")
            else:
                st.error(
                    "失敗 — 確認 google_media 已設定"
                    if lang == "zh"
                    else "Failed — ensure google_media is configured"
                )

    elif provider == "s3":
        bucket = st.text_input("S3 Bucket")
        key = st.text_input("Key (optional)", placeholder=chosen)
        if st.button("☁️ Upload to S3", type="primary",
                     disabled=not (chosen_path and bucket)):
            with st.spinner("上傳中..." if lang == "zh" else "Uploading..."):
                ok = upload_to_s3(chosen_path, bucket, key or None)
            if ok:
                st.success("✓ Uploaded to S3")
            else:
                st.error(
                    "失敗 — 確認 boto3 已安裝且憑證有效"
                    if lang == "zh"
                    else "Failed — ensure boto3 installed & credentials set"
                )

    elif provider == "webdav":
        url = st.text_input("WebDAV URL")
        webdav_user = st.text_input(
            "使用者" if lang == "zh" else "User"
        )
        webdav_pass = st.text_input(
            "密碼" if lang == "zh" else "Password",
            type="password",
        )
        if st.button("☁️ Upload to WebDAV", type="primary",
                     disabled=not (chosen_path and url and webdav_user)):
            with st.spinner("上傳中..." if lang == "zh" else "Uploading..."):
                ok = upload_to_webdav(chosen_path, url, webdav_user,
                                      webdav_pass)
            if ok:
                st.success("✓ Uploaded to WebDAV")
            else:
                st.error("Failed")
