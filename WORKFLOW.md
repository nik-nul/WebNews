# 报纸刊发系统 · 撰稿工作流（给新 session 的 LLM）

工作目录：`/home/nik_nul/project/news_dev`，数据库 `database.db` 表 `entries`。
Flask 应用跑在 80 端口，但撰稿**不需要登录网页**：直接按“网页提交”等价语义写库即可（见 §8）。
**撰写完成后不要刊发**（`publish_date` 保持 NULL，留待审核/刊发环节）。

## 1. 数据模型与状态机

`entries` 关键列（按 select * 顺序）：
`id, uploader, upload_time, title, link, description, describer, reviewer, due_time,
status, type, locked_by, lock_time, use_image, publish_date, tag, short_title,
lecture_data, priority`

- 目标输入：`publish_date IS NULL AND status='pending'`（未刊发且未撰写）。
- 撰写后：`status='described'`，`publish_date` 保持 NULL。
- 无效/重复：`status='described'` + `publish_date='1970-01-01 00:00:00'`（此后不再出现在待办和刊发候选中）。
- `type` 固定 `"活动预告"`；`use_image` 写 0；写库时清掉 `locked_by/lock_time`。
- `describer`：bot 经网站写入时如实记为 `nik_nul_bot`（不要手改；审稿人与撰稿人不同，
  天然满足“不可通过自己所写的内容”规则）。
- **入库禁止直写 DB**，一律走 §10-5 的 `web_write.py`（网站 mediated）。SQL 只读不写。

查待办：
```sql
SELECT id,upload_time,title,link FROM entries
WHERE publish_date IS NULL AND status='pending' ORDER BY upload_time ASC;
```

## 2. 分类标准（tag 五选一）

- `讲座`：讲座、研讨会、学术报告、分享会、论坛、工作坊、读书会、读书分享、求职/选调/推免经验分享等**学术型/分享型报告**。**冲突时优先判讲座**（如“面向某书院但本质是分享会”仍判讲座）。
- `院级活动`：仅面向某个学院/书院/专业少数同学（如“计算机学院全体师生”“历史学院本科生”“四院学生及教职工”）。
- `社团活动`：学生社团或民间组织主办、以爱好或娱乐为主（如剧本杀、油画疗愈、开放麦、音乐会）。
- `招聘升学宣讲`：企业/单位招聘宣讲会、考研/保研/留学/升学宣讲、招生宣讲等**招生招聘型宣讲**。经验分享型（如求职经验分享会）仍按冲突规则判`讲座`。
- `校级活动`：面向全校不特定多数人可参加，或通知范围不是某个学院（如全校双选会、外交部/商务部宣讲、全校性大赛、全校通知）。

刊发分区映射（`main.py` publish 逻辑）：`讲座→lecture`，`院级活动→college`，
`社团活动→club`，`招聘升学宣讲→career`（末分区，社团活动之后），
其他（含`校级活动`）→`other`。tag 只能取这五者之一，
**禁止** `学术报告` 等自定义值。

## 3. 标题规范（精简、中立、反映内容）

- 去掉前缀：`活动预告|`、`讲座预告|`、`赛事预告丨`、`宣讲信息丨`、`【讲座预告】`、
  `小南帮推｜`、`征集令｜`、`报名开启|`、`10月9日` 等日期前缀。
- **讲座标题只写 talk 本身**：不要系列名和编号（如“潘菽心理学论坛第107期：”去掉），
  不要主讲人前缀（如“张双鼓：”“彭沁沁：”“赵新侃：”“朱佳木：”“孙圣民 | ”去掉，
  只留冒号后的标题）。英文 talk 保留英文。
- 例：`张双鼓：积极参与全球治理…` → `积极参与全球治理、助力构建人类命运共同体`；
  `潘菽心理学论坛第107期：Use of social robots…` → `Use of social robots in educational settings`；
  `“诚计划”第221期：不忘初心…` → `不忘初心牢记使命——中国共产党百年奋斗和经验`。

## 4. 正文（description）规范：精简

非讲座只保留关键信息，每行一条，例如：
```
活动时间：6月14日（周日）16:30
活动地点：仙林校区第十食堂
请扫码报名并加群
```
```
报名截止日期：6月6日晚24：00
```

讲座严格按顺序（以撰写/审核页“根据结构化内容生成描述”按钮逻辑为准，
description 须与 lecture_data JSON 字段严格对应，JSON 里没有的不写，
系列名只进 JSON 的 series，不进正文；**摘要不进 description，只进 JSON**）：
```
时间：M月D日 HH:MM（24小时制，只写开始时间，不写结束时间）
地点：具体地点
主讲人：姓名 单位职称、姓名 单位职称
主持人：姓名 单位职称（如有；与谈人/邀请人只进 JSON，不进正文）
[面向XXX]（仅明确限定时写，无冒号，直接“面向”加内容）
[线上参与方式：XXX]（如有）
[报名方法见原文]（JSON 中 registration 非空时写固定此句，不写具体报名内容）
```
正文不要手写：用仓库根 `python3 gen_lecture_desc.py` 从 lecture_data JSON 生成
（与页面按钮同逻辑，默认不含系列行；`--include-series` 可打出按钮原样）。
入库后用它重跑对比，逐字一致才算合格。
示例见 `latest.json` 中 lecture 条目。

## 5. lecture_data（讲座必填，非讲座必须为空）

讲座行必须提供合法 JSON 字符串；非讲座 `lecture_data` 置 NULL（网页端 tag 非讲座时该字段为空）。
Schema：
```json
{
  "series": {"name": "系列名", "number": "如第107期"},
  "title": {"primary": "cleaned标题（必须等于title列）", "secondary": "英文标题或空"},
  "schedule": {"date": "2026-MM-DD", "start_time": "HH:MM", "end_time": "HH:MM或空"},
  "venue": "地点",
  "organizer": "主办方（未知可空）",
  "speakers": [{"name": "", "title": "单位职称", "biography": "简介可空"}],
  "discussants": [],
  "inviter": {"name": "", "title": ""},
  "moderator": {"name": "", "title": ""},
  "abstract": "2-4句提炼，可空",
  "target_audience": "仅限定时填",
  "registration": "报名方式，无则空",
  "online_access": "线上方式，无则空"
}
```
年份一律 2026，日期应在 10 月前后（合理性检查）。`sync_entry_to_platform`
会用它同步到讲座平台，故时间地点人物尽量准确。

填写时套用撰写页“复制提示词”按钮的模板（`templates/describe.html` `copyPrompt()`，
`review.html` 同文），把示例换成真实值、空字段留空字符串/空数组：

```text
请帮我从给定的图片或链接中提取讲座信息，并按照JSON格式返回：

    JSON格式示例：
    {
        "series": {
            "name": "系列名",
            "number": "系列编号，如第143期"
        },
        "title": {
            "primary": "主标题",
            "secondary": "其他语言标题"
        },
        "schedule": {
            "date": "yyyy-mm-dd",
            "start_time": "hh:mm",
            "end_time": "hh:mm"
        },
        "venue": "讲座地点",
        "organizer": "主办方",
        "speakers": [
            {
                "name": "主讲人姓名",
                "title": "单位和职称，如南京大学计算机学院教授",
                "biography": "简介"
            }
        ],
        "discussants": [
            {
                "name": "与谈人姓名",
                "title": "单位和职称，如南京大学计算机学院教授",
                "biography": "简介"
            }
        ],
        "inviter": {
            "name": "邀请人姓名",
            "title": "单位和职称，如南京大学计算机学院教授",
            "biography": "简介"
        },
        "moderator": {
            "name": "主持人姓名",
            "title": "单位和职称，如南京大学计算机学院教授",
            "biography": "简介"
        },
        "abstract": "讲座摘要",
        "target_audience": "面向人群，除非特定了仅有特定人群可以参加才填写，一般情况下请留空",
        "registration": "报名方式，无需报名留空",
        "online_access": "线上参与方法，如腾讯会议号，Zoom链接，没有则留空"
    }
```

注意：`title.primary` 必须等于 `title` 列；`discussants`/`moderator`/`inviter`
必须是对象（或对象数组），不许写成字符串；`number` 用字符串。违反的同步会失败。

## 6. DDL（due_time + short_title）：有举办时间必须写

- `due_time`：`yyyy-mm-dd`（**不要带时分**）。讲座 = 举办日；比赛/征集 = 举办日或截止日；
  多阶段活动取首场或报名截止（按性质， Stern： Kom 保持一致即可）。
- `short_title`（DDL 表格用）：**讲座照抄全标题**（cleaned 后的）；
  **非讲座要精简、反映性质**，如“四院中秋游园会”，`第三届“政管杯”…`（去“南京大学”）、
  `港澳台学生中华文化知识大赛`（去冗长定语）、`AI Poster交流展`、`黄山地理体验活动`。
- `priority`：讲座默认 4，其他默认 0。

## 7. 去重（仅凭标题）

- 同一批 pending 内标题明显同一内容：保留**先上传**（id 小），后上传的标重复。
- 与库中已撰写/已刊发同内容（如同 talk 不同链接：mp vs 学院站）：新来的标重复。
- 标重复的方法（与历史惯例一致，统一在 §10-5 经网站执行，不要直接 SQL）：
  准备 `{"id": N, "invalid": true, "title": "【重复】"+原标题}` 文件，
  `web_write.py` 会先调 `/describe` 改标题/tag/desc，再调 `/admin/publish`
  把 `publish_date` 置 `1970-01-01 00:00:00`（`tag=''`，`description='None'`，
  short/due 保持原样，一般为 NULL）。
- 写完新闻后**不需要刊发**重复条目（publish_date 已置 1970 即排除）。

## 8. 一链多讲座：拆分为多个 id

若一个链接对应多场讲座（如系列讲座含 10/13、10/14、10/16 三场），不要合并：
保留原 id 放第一场，**新增行**放后续各场（`web_write.py` 遇到带 `split_from` 的文件
会自动调 `/upload` 新建：同 `link`、新 `upload_time=now`，其余字段取文件内容），
各有独立 title/description/lecture_data/due。
非讲座同理（如同一推送含上下午两场活动）。

## 9. 原文抓取

- 用 `webfetch` 读原文链接全文；微信推文信息常在**图片**里，要结合多模态看图
  提取时间、地点、人物、主办方、报名方式；nju.edu.cn 站点多为 HTML 正文，直接解析。
- `job.nju.edu.cn` 是 Vue3 空壳站：页面 HTML 只有 `<div id="app">`，正文走 JSON API，
  页面抓出来只有“南京大学就业门户”不代表死链，必须走 API 取数：
  1. 专场宣讲详情 `GET https://job.nju.edu.cn/api/career/job/fair/specifics/{id}`
     （id 取页面 URL 尾段），200 即正文（theme/company/intro/campus/startAt/endAt/venue）；
     若 404（`专场招聘会不存在`），不要直接判死——先查列表
     `GET https://job.nju.edu.cn/api/career/job/fair/specifics?page=N&size=100`（约 9 页），
     用 URL id 做前缀匹配找完整 id，再取详情（URL 里的 id 可能缺尾段）。
  2. 双选会同理：列表 `GET .../mutual-selections?page=&size=`，
     详情 `GET .../mutual-selections/{id}`（时间地点在 startAt/endAt/address，
     参会细节在 invitationContent，需剥 HTML 标签）。
  3. 只有列表里也查无此条，才算真正下线。前车之鉴：H 组曾因 subagent 只试了
     缺 `/job/fair` 段的错误端点而误判整组死链，实际 6 条俱在。
  实在需要渲染 JS 时，环境里有 chromium + python playwright 可用（仓库根目录有现成的
  `spa_probe.py`，拦截 XHR 找 API），但优先直接调 API。
- 抓取失败时可基于标题合理推断，但优先抓取成功；年份 2026。

## 10. 标准执行流程（已验证，可照做）

> **铁律：禁止直写 DB。** 所有入库一律经网站 mediated（bot 登录调
> `/describe`、`/upload`、`/admin/publish`），用 `web_write.py` 执行。
> SQL 只读不写（查待办、验证计数）。

1. 查 pending（§1 SQL），先读标题做去重（§7），**只记重复清单，不写库**
   （标重复统一在第 5 步经网站执行）。
2. 读几个比较新的已撰写报道（`status='described' ORDER BY id DESC`）确认格式，
   把要求整理进 subagent prompt。
3. 将剩余条目分组（每组 4–7 条），并行开 `subagent(general)` 撰写。
   prompt 必须完备，直接套用以下模板（只把【条目列表】换成 `id | 原标题 | 链接` 行，
   只把【输出目录】换成 `desc/<日期>/`，其余一字不删；
   纯单类批次可在首段注明 tag 写死什么值）：
   ```text
   你在 /home/nik_nul/project/news_dev 为南哪小报撰写条目。用 webfetch 读链接全文
   （微信推文信息常在图片里，结合多模态看图提取时间、地点、人物、主办方、报名方式；
   job.nju.edu.cn 走 §9 的 API 方法，不要只抓页面就判死链）。
   每个条目写成一个 JSON 文件到【输出目录】（文件名 `{id}.json`；
   一链多场的后几场用 `{id}b.json`、`{id}c.json`…，内容里 `"id": null` 并加
   `"split_from": <原id>`）。写完自己运行 `python3 validate_desc.py --dir 【输出目录】`
   把 ERROR 清零再返回；只返回一句话汇总（各 id 的 tag/标题/due），不要贴全文。
   【条目列表】
   分类（tag 五选一）：讲座（学术型/分享型报告，含读书会/工作坊/论坛/求职经验分享，
   冲突时优先判讲座）/ 院级活动（仅面向某学院少数人）/ 社团活动（社团主办爱好娱乐）/
   招聘升学宣讲（企业招聘宣讲、升学招生宣讲、双选会/专场招聘会；与求职“经验分享”冲突时判讲座）/
   校级活动（面向全校或全校通知）。
   标题：精简中立去前缀（活动预告|/丨、赛事预告、宣讲信息、邀请函、会议议程、讲座预告、
   影展征集、日期前缀等）；讲座只写 talk 本身（去系列名期数、主讲人前缀，英文保留英文）。
   非讲座正文：只留关键信息，每行一条（时间/地点/报名）。
   讲座正文：按 `gen_lecture_desc.py` 的逻辑从 JSON 生成（时间只写开始时间、面向无冒号、
   报名写固定句“报名方法见原文”、系列只进 JSON 不进正文，摘要不进正文），不要手写手拼。
   lecture_data：讲座必填合法 JSON，非讲座取 ""。键必须齐全
   （series/title/schedule/venue/organizer/speakers/discussants/inviter/moderator/
   abstract/target_audience/registration/online_access），discussants/moderator/inviter
   必须是对象（或对象数组）不许是字符串，number 用字符串，title.primary 必须等于 title 列。
   填写要求与示例见 §5（含页面“复制提示词”模板）。
   short_title：讲座照抄全标题；非讲座精简反映性质。
   due_time：举办日 yyyy-mm-dd 无时分（年份 2026）；多阶段取首场或报名截止（按性质）。
   priority：讲座 4，其他 0，可为负数降权。
   一链多场拆分按上文文件规则返回；疑似与已刊发同内容的加 "dup_suspect": true 并说明。
   实在抓不到的返回占位并加 "fetch_failed": true，不要编造时间地点人物。
   每项键为 {id,title,short_title,description,tag,due_time,priority,lecture_data}，
   另可带 split_from/dup_suspect/fetch_failed/note。
   ```
4. 主 agent 通读：跑 `python3 validate_desc.py --dir <输出目录> --summary` 看一览表
   （不要逐个读文件全文），重点做机器做不了的事：
   - 跨文件去重（标题相近的即便是不同链接，如 mp vs 学院站同 talk）：命中者在文件里加
     `"dup_suspect": true` + note，或直接判重复；
   - 一链多场、一推多活动的拆分是否干净；
   - 高频问题抽查：tag 非法值、非讲座带 lecture_data、due_time 带时分、
     title.primary 对齐、标题残留前缀、short 过长；
   - 把 `dup_suspect` 裁决为重复的，改写成标重复文件 `{"id": N, "invalid": true,
     "title": "【重复】…原标题…"}`；`fetch_failed` 的重抓或留待办。
   改完重跑校验，ERROR 必须为 0（WARN 只许剩已裁决的，入库前清掉）。
5. 入库（经网站，不直写 DB）：
   ```bash
   export NEWS_BOT_PASSWORD=...   # nik_nul_bot 的密码
   python3 web_write.py --dir <输出目录>
   ```
   脚本用 bot 登录，普通行调 `/describe/<id>`，`split_from` 行调 `/upload`
   （自动带 parent 的 link 并取回新 id），`invalid` 行调 `/describe` +
   `/admin/publish`（publish_date 置 1970）。每行写完都用 `/api/query` 回查，
   对不上即停。注意：bot 写入的 `describer` 为 `nik_nul_bot`（如实记录；
   正好与审稿人不同，天然满足不可自审规则）。
6. 验证：
```sql
SELECT COUNT(*) FROM entries WHERE publish_date IS NULL AND status='pending'; -- 应为 0
-- 抽查几行：tag/标题/due 符合预期；讲座抽一条用 gen_lecture_desc.py 重算对比
```

## 11. 常见坑

- 微信标题与正文年份不一致时以正文为准（如标题“2026年度”正文“2027年度考录”取后者）。
- 同系列同时间同地点多链接（如 mp 与学院站同 talk）只留最早 id。
- `short_title`/`due_time` 为 NULL 的一般是重复/无效行，属正常，不要“修复”它们。
- 不要创建多余文件；撰写工作文件放仓库下 `desc/<日期>/`（不在 `/tmp`，重启不丢），
  全部刊发验证后可删；不要删库里原有目录。
- 基础设施（仓库根）：`validate_desc.py`（格式审查，subagent 自查＋主 agent 复核）、
  `gen_lecture_desc.py`（讲座正文 canonical 生成器）、`web_write.py`（bot 经网站入库）、
  `spa_probe.py`（SPA 渲染找 API）。改了 `main.py` 要重启服务才生效（无 sudo 免密，
  请用户执行 `restart.sh`）。
