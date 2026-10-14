"""撰写 JSON 格式审查：供 subagent 自查、主 agent 复核。

每个条目一个 JSON 文件（文件名 `{id}.json`；拆分行用 `{parent_id}x.json`/`{parent_id}b.json`…，
内容里带 `"split_from": <parent_id>`）。规则见 WORKFLOW.md §2–§6。

用法：
    python3 validate_desc.py a.json b.json ...   # 逐个审查
    python3 validate_desc.py --dir desc/2026-10-14/   # 整目录审查
    python3 validate_desc.py --dir D --summary        # 一览表（主 agent 复核用）

输出每行：PASS | WARN | ERROR <文件>: <说明>。
WARN（dup_suspect/fetch_failed/note 标记）需主 agent 定夺，不计入失败；
ERROR 必须清零。退出码 = ERROR 条数（0 表示通过）。
"""
import glob
import json
import os
import re
import sys

TAGS = {"讲座", "院级活动", "社团活动", "招聘升学宣讲", "校级活动"}
REQUIRED_KEYS = {"series", "title", "schedule", "venue", "organizer", "speakers",
                 "discussants", "inviter", "moderator", "abstract",
                 "target_audience", "registration", "online_access"}
TOP_KEYS = {"id", "title", "short_title", "description", "tag",
            "due_time", "priority", "lecture_data"}
FLAG_KEYS = {"dup_suspect", "fetch_failed", "note", "split_from"}

# 与 gen_lecture_desc.py 同逻辑（默认不含系列行），就地复用不另写一份
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_lecture_desc import gen_description


def check_file(path):
    errors, warns = [], []

    try:
        with open(path, encoding="utf-8") as f:
            it = json.load(f)
    except Exception as e:
        return [f"JSON 解析失败：{e}"], []
    if not isinstance(it, dict):
        return ["顶层必须是单个对象（一 id 一文件）"], []

    unknown = set(it) - TOP_KEYS - FLAG_KEYS
    if unknown:
        errors.append(f"未知键（入库脚本不认）：{sorted(unknown)}")

    iid = it.get("id")
    if it.get("split_from") is not None:
        if iid is not None:
            errors.append("split_from 与 id 互斥：拆分行 id 必须为 null")
        try:
            int(it["split_from"])
        except (TypeError, ValueError):
            errors.append("split_from 必须是父条目 id 整数")
    elif not isinstance(iid, int) or isinstance(iid, bool):
        errors.append("id 必须是整数（拆分行填 null 并给 split_from）")

    for k in ("title", "short_title"):
        if not isinstance(it.get(k), str) or not it.get(k, "").strip():
            errors.append(f"{k} 必须是非空字符串")
    if not isinstance(it.get("description"), str) or not it.get("description", "").strip():
        errors.append("description 必须是非空字符串")

    if it.get("tag") not in TAGS:
        errors.append(f"tag 非法：{it.get('tag')!r}，只能是 {sorted(TAGS)}")

    due = it.get("due_time")
    if due is not None and not re.fullmatch(r"2026-\d{2}-\d{2}", str(due)):
        errors.append(f"due_time 非法：{due!r}（要 yyyy-mm-dd、无时分，或 null）")

    pri = it.get("priority")
    if not isinstance(pri, int) or isinstance(pri, bool):
        errors.append(f"priority 必须是整数：{pri!r}")

    raw_ld = it.get("lecture_data")
    ld = None
    if it.get("tag") == "讲座":
        if isinstance(raw_ld, str):
            try:
                ld = json.loads(raw_ld)
            except Exception as e:
                errors.append(f"lecture_data 字符串解析失败：{e}")
                ld = None
        else:
            ld = raw_ld
        if not isinstance(ld, dict):
            errors.append("讲座 lecture_data 必须是完整对象，不能是空串")
            ld = None
        else:
            missing = REQUIRED_KEYS - set(ld.keys())
            if missing:
                errors.append(f"lecture_data 缺键：{sorted(missing)}")
            extra = set(ld.keys()) - REQUIRED_KEYS
            if extra:
                errors.append(f"lecture_data 多余键：{sorted(extra)}")
            for k in ("discussants",):
                v = ld.get(k, [])
                if not isinstance(v, list) or any(not isinstance(x, dict) for x in v):
                    errors.append("discussants 必须是对象数组")
                else:
                    for x in v:
                        if not isinstance(x.get("name"), str) or not isinstance(x.get("title"), str):
                            errors.append("discussants 元素须含字符串 name/title")
                            break
            for k in ("moderator", "inviter"):
                v = ld.get(k)
                if not isinstance(v, dict) or not isinstance(v.get("name"), str) \
                        or not isinstance(v.get("title"), str):
                    errors.append(f"{k} 必须是含字符串 name/title 的对象")
            num = (ld.get("series", {}) or {}).get("number", "")
            if not isinstance(num, str):
                errors.append("series.number 必须用字符串")
            title = ld.get("title", {}) or {}
            if title.get("primary") != it.get("title"):
                errors.append("lecture_data.title.primary 必须等于 title 列")
            if ld is not None and not errors:
                canon = gen_description(ld)
                if canon != (it.get("description") or ""):
                    errors.append("description 与 gen_lecture_desc.py 从 JSON 生成的不一致，"
                                  "用脚本重算覆盖（不要手写）")
    else:
        if raw_ld not in ("", None):
            errors.append("非讲座 lecture_data 必须为空（\"\" 或 null）")

    if it.get("dup_suspect"):
        warns.append(f"dup_suspect：{it.get('note', '')}")
    if it.get("fetch_failed"):
        warns.append(f"fetch_failed：{it.get('note', '')}")

    return errors, warns


def main(argv=None):
    args = list(argv if argv is not None else sys.argv[1:])
    summary = False
    if "--summary" in args:
        summary = True
        args.remove("--summary")
    paths = []
    if "--dir" in args:
        i = args.index("--dir")
        try:
            d = args[i + 1]
        except IndexError:
            print("ERROR: --dir 缺目录", file=sys.stderr)
            return 2
        paths += sorted(glob.glob(os.path.join(d, "*.json")))
        del args[i:i + 2]
    paths += args
    if not paths:
        print("用法：validate_desc.py [--dir 目录] [--summary] <file.json ...>", file=sys.stderr)
        return 2

    n_err = 0
    for p in paths:
        errors, warns = check_file(p)
        base = os.path.basename(p)
        if summary:
            try:
                it = json.load(open(p, encoding="utf-8"))
                one = (f"{base} tag={it.get('tag')} due={it.get('due_time')} "
                       f"pri={it.get('priority')} {str(it.get('title'))[:34]}")
            except Exception:
                one = f"{base} <读不出>"
            tags = []
            if errors:
                tags.append(f"ERROR×{len(errors)}")
            for w in warns:
                tags.append("WARN:" + w[:60])
            print(("OK  " if not errors and not warns else "!!  ") + one
                  + ("  [" + "; ".join(tags) + "]" if tags else ""))
        else:
            if not errors and not warns:
                print(f"PASS {base}")
            for e in errors:
                print(f"ERROR {base}: {e}")
            for w in warns:
                print(f"WARN {base}: {w}")
        n_err += len(errors)
    return min(n_err, 125)


if __name__ == "__main__":
    sys.exit(main())
