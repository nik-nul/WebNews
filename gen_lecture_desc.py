import argparse
import json
import sqlite3
import sys


def gen_description(ld, include_series=False):
    parts = []

    series = ld.get("series", {}) or {}
    series_name = str(series.get("name", "") or "").strip()
    series_number = str(series.get("number", "") or "").strip()
    if include_series and (series_name or series_number):
        line = ""
        if series_name:
            line += series_name
        if series_number:
            line += " " + series_number
        parts.append(line)

    sched = ld.get("schedule", {}) or {}
    date = str(sched.get("date", "") or "")
    start = str(sched.get("start_time", "") or "")
    if date or start:
        line = "时间："
        if date:
            _y, m, d = date.split("-")
            line += f"{int(m)}月{int(d)}日"
        if start:
            line += " " + start
        parts.append(line)

    venue = str(ld.get("venue", "") or "").strip()
    if venue:
        parts.append("地点：" + venue)

    speaker_strs = []
    for s in ld.get("speakers", []) or []:
        name = str(s.get("name", "") or "").strip()
        title = str(s.get("title", "") or "").strip()
        if name or title:
            speaker_strs.append((name + (" " + title if title else "")) if name else " " + title)
    if speaker_strs:
        parts.append("主讲人：" + "、".join(speaker_strs))

    mod = ld.get("moderator") or {}
    mod_name = str(mod.get("name", "") or "").strip()
    mod_title = str(mod.get("title", "") or "").strip()
    if mod_name or mod_title:
        parts.append("主持人：" + ((mod_name + (" " + mod_title if mod_title else ""))
                                   if mod_name else " " + mod_title))

    audience = str(ld.get("target_audience", "") or "").strip()
    if audience:
        parts.append("面向" + audience)

    online = str(ld.get("online_access", "") or "").strip()
    if online:
        parts.append("线上参与方式：" + online)

    if str(ld.get("registration", "") or "").strip():
        parts.append("报名方法见原文")

    return "\n".join(parts)


def main(argv=None):
    ap = argparse.ArgumentParser(description="从 lecture_data JSON 生成讲座 description")
    ap.add_argument("entry_id", nargs="?", help="entries.id，从 database.db 读取")
    ap.add_argument("--json", dest="json_str", default=None, help="直接给出 JSON 字符串")
    ap.add_argument("--stdin", action="store_true", help="从 stdin 读 JSON")
    ap.add_argument("--include-series", action="store_true",
                    help="输出首行系列（与网页按钮完全一致；默认不输出）")
    ap.add_argument("--db", default="database.db", help="数据库路径")
    args = ap.parse_args(argv)

    if args.json_str is not None:
        ld = json.loads(args.json_str)
    elif args.stdin:
        ld = json.load(sys.stdin)
    elif args.entry_id is not None:
        db = sqlite3.connect(args.db)
        row = db.execute("SELECT lecture_data FROM entries WHERE id=?", (args.entry_id,)).fetchone()
        db.close()
        if not row or not row[0]:
            print(f"entry {args.entry_id} 无 lecture_data", file=sys.stderr)
            return 1
        ld = json.loads(row[0])
    else:
        ap.print_help()
        return 2

    print(gen_description(ld, include_series=args.include_series))
    return 0


if __name__ == "__main__":
    sys.exit(main())
