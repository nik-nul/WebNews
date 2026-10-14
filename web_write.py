"""经网站 mediated 写库：bot 登录后调 /describe /upload /admin/publish，不直写 DB。

用法：
    export NEWS_BOT_PASSWORD=...   # nik_nul_bot 的密码（或 --password，或交互输入）
    python3 web_write.py --dir desc/<日期>/ [--dry-run] [--base http://127.0.0.1]

输入：validate_desc.py 全绿的 JSON 文件（一 id 一文件；拆分行带 split_from；
标重复行形如 {"id": N, "invalid": true, "title": "【重复】…"}）。
含 dup_suspect/fetch_failed 的文件一律拒绝（主 agent 先裁决）。

动作：
  普通行       → POST /describe/<id>（全字段；非讲座不发 lecture_data→NULL；
                 图片条目自动 use_image=on，以 /api/query 读到的现 link 为准）
  split_from 行 → POST /upload（带 parent 的 link，format=json 取新 id）
  invalid 行    → POST /describe（改标题/tag/desc）+ POST /admin/publish
                 publish_time=1970-01-01（需 editor 权限，nik_nul_bot 已在列）
每写完一行都用 /api/query 回查（status/describer/publish_date），对不上即报错退出。
"""
import argparse
import getpass
import glob
import json
import os
import sys

import requests

ALLOWED_IMG = {"png", "jpg", "jpeg", "webp"}


def is_image_link(link):
    return bool(link) and "." in link and link.rsplit(".", 1)[1].lower() in ALLOWED_IMG


def login(base, username, password):
    s = requests.Session()
    r = s.post(base + "/login", data={"username": username, "password": password},
               allow_redirects=True, timeout=30)
    # 未登录会被 login_required 踢回 /login；登录成功进 /（200）
    if r.status_code != 200 or 'name="username"' in r.text and "刊载" not in r.text:
        # 更可靠的判定：GET / 看是否跳转到登录页
        probe = s.get(base + "/", allow_redirects=False, timeout=30)
        if probe.status_code in (301, 302, 303) and "/login" in probe.headers.get("Location", ""):
            raise SystemExit("登录失败：用户名或密码不对")
    return s


def api_row(s, base, entry_id):
    r = s.get(base + "/api/query", params={"id": int(entry_id)}, timeout=30)
    r.raise_for_status()
    rows = r.json()
    if not rows:
        raise SystemExit(f"entry {entry_id} 在库里不存在")
    return rows[0]


def post_describe(s, base, entry_id, fields, dry):
    # 列序见 WORKFLOW §1：0id 3title 4link 5desc 6describer 8due 9status 10type
    # 13use_image 14publish_date 15tag 16short 17lecture_data 18priority
    data = {
        "title": fields["title"],
        "entry_type": "活动预告",
        "description": fields["description"],
        "due_time": fields["due_time"] or "",
        "tag": fields.get("tag") or "",
        "short_title": fields.get("short_title") or fields["title"],
        "priority": str(fields.get("priority", 0)),
    }
    if fields.get("tag") == "讲座":
        data["lecture_data"] = fields["lecture_data"] if isinstance(
            fields.get("lecture_data"), str) else json.dumps(
            fields.get("lecture_data"), ensure_ascii=False)
    if dry:
        print(f"  DRY describe {entry_id}: {fields['title'][:30]}")
        return
    cur = api_row(s, base, entry_id)
    if is_image_link(cur[4]):
        data["use_image"] = "on"
    r = s.post(f"{base}/describe/{entry_id}", data=data, allow_redirects=False, timeout=60)
    if r.status_code not in (301, 302, 303):
        raise SystemExit(f"describe {entry_id} 失败：HTTP {r.status_code} {r.text[:200]}")
    row = api_row(s, base, entry_id)
    if row[9] != "described" or row[3] != fields["title"]:
        raise SystemExit(f"describe {entry_id} 回查不一致：{row[9]} / {row[3][:30]}")
    print(f"OK describe {entry_id} {fields['title'][:34]}")


def post_upload_split(s, base, fields, dry):
    if dry:
        print(f"  DRY upload split_from={fields['split_from']}: {fields['title'][:30]}")
        return None
    parent = api_row(s, base, fields["split_from"])
    data = {
        "title": fields["title"],
        "description": fields["description"],
        "due_time": fields["due_time"] or "",
        "entry_type": "活动预告",
        "tag": fields.get("tag") or "",
        "short_title": fields.get("short_title") or fields["title"],
        "priority": str(fields.get("priority", 0)),
        "link": parent[4] or "",
        "format": "json",
    }
    if fields.get("tag") == "讲座":
        data["lecture_data"] = fields["lecture_data"] if isinstance(
            fields.get("lecture_data"), str) else json.dumps(
            fields.get("lecture_data"), ensure_ascii=False)
    r = s.post(base + "/upload", data=data, timeout=60)
    try:
        new_id = r.json()["id"]
    except Exception:
        raise SystemExit(f"upload split 失败：HTTP {r.status_code} {r.text[:200]}")
    row = api_row(s, base, new_id)
    if row[9] != "described":
        raise SystemExit(f"upload 回查不一致：new_id={new_id} status={row[9]}")
    print(f"OK upload split_from={fields['split_from']} -> {new_id} {fields['title'][:30]}")
    # 拆分行的 lecture_data 经 /upload 落盘（新版 upload 已支持），无需二次 describe
    return new_id


def post_mark_invalid(s, base, entry_id, title, dry):
    if dry:
        print(f"  DRY invalid {entry_id}: {title[:30]}")
        return
    s.post(f"{base}/describe/{entry_id}", data={
        "title": title, "entry_type": "活动预告", "description": "None",
        "due_time": "", "tag": "", "short_title": title, "priority": "0",
    }, allow_redirects=False, timeout=60)
    r = s.post(f"{base}/admin/publish",
               data={"entry_ids": str(entry_id), "publish_time": "1970-01-01"},
               allow_redirects=False, timeout=60)
    if r.status_code not in (301, 302, 303):
        raise SystemExit(f"admin_publish {entry_id} 失败：HTTP {r.status_code} {r.text[:200]}")
    row = api_row(s, base, entry_id)
    if not str(row[14] or "").startswith("1970"):
        raise SystemExit(f"invalid 回查不一致：publish_date={row[14]}")
    print(f"OK invalid {entry_id} {title[:34]}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="经网站写库（bot mediated）")
    ap.add_argument("--dir", required=True, help="final JSON 目录")
    ap.add_argument("--base", default="http://127.0.0.1", help="站点根地址")
    ap.add_argument("--user", default="nik_nul_bot")
    ap.add_argument("--password", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    password = args.password or os.environ.get("NEWS_BOT_PASSWORD")
    if not password and not args.dry_run:
        password = getpass.getpass("bot password: ")
    if not password and not args.dry_run:
        raise SystemExit("缺密码：--password 或 NEWS_BOT_PASSWORD")

    paths = sorted(glob.glob(os.path.join(args.dir, "*.json")))
    if not paths:
        raise SystemExit(f"目录无 JSON：{args.dir}")
    items = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            items.append((p, json.load(f)))
    for p, it in items:
        if it.get("dup_suspect") or it.get("fetch_failed"):
            raise SystemExit(f"{p} 带未裁决标记，先由主 agent 处理（dup/重抓），不入库")

    s = login(args.base, args.user, password or "x") if not args.dry_run else None
    if not args.dry_run:
        print(f"logged in as {args.user}")
    for p, it in items:
        base = os.path.basename(p)
        if it.get("invalid"):
            if not isinstance(it.get("id"), int):
                raise SystemExit(f"{base} invalid 行必须带整数 id")
            post_mark_invalid(s, args.base, it["id"], it.get("title", ""), args.dry_run)
        elif it.get("split_from") is not None:
            post_upload_split(s, args.base, it, args.dry_run)
        else:
            if not isinstance(it.get("id"), int):
                raise SystemExit(f"{base} 缺整数 id（拆分行需 split_from）")
            post_describe(s, args.base, it["id"], it, args.dry_run)
    print(f"done: {len(items)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
