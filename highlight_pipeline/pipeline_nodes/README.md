# Pipeline Nodes

这里放的是高光自动化链路的可导入节点配置。当前本地工程没有发现现成的生产 pipeline 编排文件，因此这里先提供一个标准 Agent 节点定义，方便迁移到外部 pipeline 平台。

## Agent 节点

配置文件：

```text
pipeline_nodes/highlight_agent_node.json
```

提示词文件：

```text
highlight_agent_prompt.md
```

节点输入：

```text
workspace/agent_input/highlight_agent_input.json
```

节点输出：

```text
workspace/plan/highlight_plan.json
```

## 推荐编排

1. `N01/N02 构建素材池`

```bash
python3 scripts/build_segment_pool.py "<node_outputs_json_url>" --out-dir workspace/pool
```

2. `N03 高光 Agent`

把 `pipeline_nodes/highlight_agent_node.json` 导入现有 pipeline 的 Agent 节点。

Agent 执行时：

- system/user prompt 使用 `highlight_agent_prompt.md`
- input JSON 使用 `workspace/agent_input/highlight_agent_input.json`
- 外部 API 推荐直接消费 `agent_query` 字段
- output JSON 写入 `workspace/plan/highlight_plan.json`

3. `N04 生成回捞时间线`

```bash
python3 scripts/build_timeline.py workspace/plan/highlight_plan.json workspace/pool/full_segment_pool.json --out workspace/plan/highlight_timeline.json
```

4. `N05 下载并拼接`

```bash
python3 scripts/download_and_concat.py workspace/plan/highlight_timeline.json --workspace workspace --output output/highlight_01.mp4
```

## 一键入口

如果现有 pipeline 只支持调用脚本，可以用：

```bash
python3 scripts/run_highlight_pipeline.py "<node_outputs_json_url>"
```

这个命令会生成素材池，然后停在 Agent 接入点。

Agent 输出 `workspace/plan/highlight_plan.json` 后，继续：

```bash
python3 scripts/run_highlight_pipeline.py "<node_outputs_json_url>" --agent-plan workspace/plan/highlight_plan.json
```
