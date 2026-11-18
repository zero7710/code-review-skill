# 输出给运行程序的结果

交付一个符合 [result.schema.json](result.schema.json) 的 JSON 对象。会话内可先给简短的人读结论。供运行程序消费时单独交出 JSON。文档中的示例是虚构夹具。实际输出只使用本次可观察的源码、工具结果和调用方交付的历史。

交接前可在 Skill 目录用 `python scripts/validate_result.py result.json` 检查结构、意见引用、图节点和行号区间。校验器使用 Python 的 `jsonschema` 4.x，传入 `-` 可从标准输入读取。证据是否与实际源码一致仍由审查和复核确认。

## 共同字段

- `schema_version` 固定为整数 1。`kind` 取 `review` 或 `explanation`。结果保持为一次调用的内容，便于跨项目复用。
- `snapshot` 是被审查或讲解的版本。已提交代码填 `git:<完整提交 SHA>`。含未提交文件时填 `worktree:<实际快照标识>`，优先复用运行程序的快照。本地可用所读文件的路径及内容哈希生成标识并注明覆盖范围。只有保存了对应文件内容或可还原的补丁时，才能承诺日后回放。本地快照用于本次定位，不能拼成 GitHub 提交链接。
- 源码位置用仓库相对路径和从 1 开始的行号。区间的 `end_line` 大于等于 `line`。`side` 默认 `head`，删除的行明确标为 `base` 并提供审查比较基准。核对文件、版本和位置确实存在后再引用。

## 审查结果

| 字段 | 填写规则 |
| --- | --- |
| `round`、`base` | PR 填本次审查轮号及实际比较基准。第 3 轮的基准是上次**已完成审查**的版本。开发前置检查、基线或无 PR 的手动任务用 `round: null`。审阅单一快照时可用 `base: null` |
| `coverage` | `scope` 填整次改动、仅新增差异、存量基线或手动范围对应的枚举值。`checked` 列实际覆盖的模块或路径，`gaps` 列未覆盖处、原因和影响 |
| `checks` | 分别记录实际做过的缺陷发现、独立安全审查、逐条复核及运行的验证。给出真实工具或命令、返回结论、缺少的能力。无独立复核时保留候选为待核实。需要的审查层缺失而影响结论时返回 `incomplete` |
| `candidates` | 每个疑点有本次结果内唯一的 `local_key`。记录独立复核采信、驳回、待核实或并入同根因的理由。`duplicate_of` 指向本次候选 key 或输入已给出的旧意见引用 |
| `findings` | 仅列本轮新确认、可交给调用方发布的意见。每项的 `candidate_key` 必须对应 `verified` 候选，一项根因写一次，列全已核实位置。写明触发条件、错误后果、模块、来源和严重度。`verification` 写独立复核的支持与异议及代码或测试依据。`pre_existing` 是既有问题的来源标签，可与严重度并存 |
| `updates` | 每条交给本轮验证的旧意见各一项。`prior_ref` 复用输入给出的后端编号、原评论引用或可追溯的上轮本地意见引用。同根因的新位置追加在旧意见中。`still_present`、`verified_fixed` 分别写重验结果。`not_checked` 写未覆盖原因，保留原处理状态。`closed_with_reason` 须有已确认的关闭决定和理由。`attempted_fix` 写已尝试的实际修复 |
| `risk`、`next_action` | 有放行或交接判断时填风险档次、依据、需要谁决定什么。用 `unknown` 表示依据不足。`risk` 是本轮评估。代码平台的审批、CI 与实际门禁由运行程序同步 |

**本轮如何结束。** `clear` 表示审查范围已覆盖、零条新确认意见且已交付的旧意见均验证修复或附理由关闭。前两轮有待处理意见时用 `needs_fix`。需要负责人介入或第 3 轮仍有未决意见时用 `needs_human`，在 `next_action` 列出未决项、已尝试的修复、接手人和需要作出的决定。执行失败、对比版本缺失、关键范围或复核缺失而无法给出本轮正式结论时用 `incomplete`，注明缺口和恢复条件。这种尝试不占新轮次。`clear` 的含义止于 AI 审查，不能代填平台审批或表示已合并。

以下用一套虚构的任务队列演示第 3 轮复查。调用方已经给上一轮的问题分配了编号 Q-12。

```json
{
  "schema_version": 1,
  "kind": "review",
  "snapshot": "worktree:fixture-after-fix",
  "base": "worktree:fixture-previous-review",
  "round": 3,
  "coverage": {"scope": "new_diff", "checked": ["src/queue.py 中单条与批量入队的改动及原问题的触发条件"], "gaps": []},
  "checks": [
    {"name": "缺陷与安全审查", "status": "passed", "detail": "两个独立检查均已完成。本次增量没有新候选。"},
    {"name": "原意见复核", "status": "passed", "detail": "复核组沿批量入口追踪到无条件追加任务的分支。"}
  ],
  "candidates": [],
  "findings": [],
  "updates": [{
    "prior_ref": "Q-12", "status": "still_present",
    "reason": "批量重试会将同一个任务再次入队，消费者因而重复执行。",
    "locations": [{"path": "src/queue.py", "line": 48}],
    "attempted_fix": "单条入队时已按任务 ID 去重。"
  }],
  "outcome": "needs_human",
  "summary": "0 条新发现，1 条未解决。第 3 轮结束。",
  "next_action": "交给负责人决定两个入队入口如何共用去重逻辑。"
}
```

## 代码讲解结果

`nodes` 中每个节点对应一句可从该版本核对的行为和代码位置。`edges` 中的 `from`、`to` 引用本结果内唯一的节点 ID，`label` 说明读取、调用、分支条件等实际关系。分享指定步骤时在 `selected_node` 保留其节点 ID。单个位置就能回答问题时给一个节点、空关系数组。`open_questions` 可记录从本次材料中仍无法确认的设计原因。若连被讲解的代码都无法定位，先报告缺失输入，勿造节点凑成讲解。

```json
{
  "schema_version": 1,
  "kind": "explanation",
  "snapshot": "worktree:fixture-queue",
  "question": "为什么消费者会先取较早入队的任务？",
  "answer": "生产者在队尾追加任务，消费者从队首取出下一项。",
  "nodes": [
    {"id": "append", "label": "在队尾追加任务", "location": {"path": "src/queue.py", "line": 26}},
    {"id": "consume", "label": "读取并移除队首任务", "location": {"path": "src/worker.py", "line": 11}}
  ],
  "edges": [{"from": "append", "to": "consume", "label": "消费者从共享队列取任务"}]
}
```

## 接入项目后台

运行程序校验 Skill 返回的 JSON，再由项目决定是否存档或上报。在结果对象之外记录项目、用途、运行与事件编号、时间，以及本次**实际安装的 Skill 提交 SHA**、项目规则版本、提示词、模型和工具版本。安装版本可由可核实的版本锁或安装记录取得，来源不明时标为未知。`schema_version` 描述输出格式，`snapshot` 定位目标项目的源码，这两个值都不能还原 Skill 的版本。

PR 审查还需关联改动意图、PR、已审提交和轮次。运行程序为首次发布的意见保存稳定编号和原讨论引用，再交给下一轮。重试上报复用事件编号，接收方按编号去重。迟到的结果归入对应提交和轮次。项目从代码平台同步作者反馈、CI 和人工审批等事实，自行决定谁能查看。未接后台时，调用者可直接读取本地结果。

| 视图举例 | 可读取的数据 |
| --- | --- |
| 版本比较 | 汇合[历史案例评测](evaluation.md)的逐次结果、评分与作者反馈，按实际审查器版本比较。 |
| 项目问题分布 | 按用途筛选正式意见，用稳定编号跨轮计数。复发要关联前次修复及此次再现的两份证据。 |
| PR 时间线 | 按提交、轮次和原意见串接验证证据与平台回执。本轮未验证的意见保留原处理状态。 |
| 代码讲解 | 按 `nodes` 和 `edges` 绘图，点击节点定位到 `snapshot` 中的源码行。无需关联 PR。 |
