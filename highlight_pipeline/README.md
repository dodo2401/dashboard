# Highlight Pipeline

这是一个基于现有 `node_outputs.json` 的高光视频自动化链路。目标是：从已生成的分集、分句、视频、音频素材里，先让高光 Agent 选出一条高光方案，再按分句 ID 回捞原视频片段，最后本地下载并拼接。

## 节点流程

1. `N01 读取任务 JSON`
   - 输入：`node_outputs.json` URL。
   - 输出：任务基础信息、分集 `debug_data_url` 列表。

2. `N02 构建素材池`
   - 输入：`node_outputs.json`、所有分集 `debug_data_url`。
   - 输出：`light_segment_pool.json` 和 `full_segment_pool.json`。
   - 说明：`light` 给高光 Agent 使用，字段轻；`full` 给回捞使用，保留视频、音频、关键帧 URL。

3. `N03 高光 Agent`
   - 输入：`light_segment_pool.json`。
   - 输出：`highlight_plan.json`。
   - 说明：只需要控制绑定多少条分句，不需要单独控制每条视频时长。
   - 提示词：见 `highlight_agent_prompt.md`。
   - 节点配置：见 `pipeline_nodes/highlight_agent_node.json`。

4. `N04 回捞时间线`
   - 输入：`highlight_plan.json`、`full_segment_pool.json`。
   - 输出：`highlight_timeline.json`。
   - 说明：按 `global_segment_id` 精确找回 `merged_video_url`，缺失时回退到 `video_url`。

5. `N05 本地下载与拼接`
   - 输入：`highlight_timeline.json`。
   - 输出：本地 clips、`concat_list.txt`、最终 `highlight_01.mp4`。
   - 说明：需要本机安装 `ffmpeg`。没有 `ffmpeg` 时脚本会先下载并生成 concat 清单，然后提示下一步。

## 快速跑通

在本目录执行：

```bash
cd /Users/jiazhuo/Documents/Playground/pipeline_dashboard/highlight_pipeline
```

## 外部 API 手动桥接

如果外部 Agent API 暂时不能直接调用，可以先只生成 Agent 输入：

```bash
python3 scripts/prepare_agent_input.py "https://anim-res.youku.com/yk/ai-animation/animate_video/narration_final_process_3590cd31_515d8942/node_outputs.json"
```

会输出两个文件：

```text
workspace/agent_input/highlight_agent_input.json
workspace/agent_input/highlight_agent_input.txt
```

推荐把 `highlight_agent_input.txt` 全文复制到外部 Agent 页面；如果外部 API 只能填 JSON 字段，则使用 `highlight_agent_input.json` 中的 `agent_query` 字段。
默认会输出全部分集，并按 `第1集 -> 第N集` 顺序排列；如外部 Agent 输入长度受限，再手动加 `--candidate-scenes 10` 做候选压缩。

新版手动输入已经精简为：

```text
1-1. 对应文本
1-2. 对应文本
```

外部 Agent 只需要返回：

```json
{
  "title": "高光标题",
  "reason": "选择理由",
  "shots": [
    {
      "episode": 1,
      "sentence": 1,
      "text": "原文句子"
    }
  ]
}
```

外部 Agent 返回后，先保存到任意文本文件，例如：

```text
workspace/plan/manual_agent_output.txt
```

再校验并转成标准回捞方案：

```bash
python3 scripts/save_agent_output.py workspace/plan/manual_agent_output.txt --out workspace/plan/highlight_plan.json
```

最后继续回捞时间线：

```bash
python3 scripts/run_highlight_pipeline.py "https://anim-res.youku.com/yk/ai-animation/animate_video/narration_final_process_3590cd31_515d8942/node_outputs.json" --agent-plan workspace/plan/highlight_plan.json
```

一键接入入口：

```bash
python3 scripts/run_highlight_pipeline.py "https://anim-res.youku.com/yk/ai-animation/animate_video/narration_final_process_9ca3f6a1_10b20aff/node_outputs.json"
```

这会先生成 `workspace/pool/light_segment_pool.json` 和 `workspace/agent_input/highlight_agent_input.json`，然后停在高光 Agent 接入点。Agent 优先读取 `highlight_agent_input.json` 中的 `agent_query`，输出 `workspace/plan/highlight_plan.json` 后，继续执行：

```bash
python3 scripts/run_highlight_pipeline.py "https://anim-res.youku.com/yk/ai-animation/animate_video/narration_final_process_9ca3f6a1_10b20aff/node_outputs.json" --agent-plan workspace/plan/highlight_plan.json
```

如果已经有外部 Agent API，直接用 API 模式：

```bash
python3 scripts/run_highlight_pipeline.py "https://anim-res.youku.com/yk/ai-animation/animate_video/narration_final_process_9ca3f6a1_10b20aff/node_outputs.json" --agent-api "https://aistudio.alibaba-inc.com/api/aiapp/run/OYuXGejqqIU/1.0.0"
```

如果 API 返回结果包在某个字段里，例如 `data.output`，加：

```bash
--agent-unwrap-field data.output
```

如果只是烟测整条链路，可以用 demo 模式：

```bash
python3 scripts/run_highlight_pipeline.py "https://anim-res.youku.com/yk/ai-animation/animate_video/narration_final_process_9ca3f6a1_10b20aff/node_outputs.json" --demo --demo-count 12
```

构建素材池：

```bash
python3 scripts/build_segment_pool.py "https://anim-res.youku.com/yk/ai-animation/animate_video/narration_final_process_9ca3f6a1_10b20aff/node_outputs.json" --out-dir workspace/pool
```

先用 demo 高光方案验证链路：

```bash
python3 scripts/make_demo_highlight_plan.py workspace/pool/light_segment_pool.json --out workspace/plan/highlight_plan.json --count 12
```

生成回捞时间线：

```bash
python3 scripts/build_timeline.py workspace/plan/highlight_plan.json workspace/pool/full_segment_pool.json --out workspace/plan/highlight_timeline.json
```

下载并拼接：

```bash
python3 scripts/download_and_concat.py workspace/plan/highlight_timeline.json --workspace workspace --output output/highlight_01.mp4
```

小样验证可以加 `--limit 3`，只下载前 3 个片段。

## 高光 Agent 标准输入

文件：`workspace/agent_input/highlight_agent_input.json`

关键字段：

- `source_json_url`：原始任务 URL。
- `run_id`：任务 ID。
- `summary.episode_count`：分集数量。
- `summary.segment_count`：分句数量。
- `highlight_target.preferred_segment_count`：建议绑定分句数。
- `agent_query`：外部 Agent API 推荐直接消费的完整任务文本。
- `episodes[*].segments[*].global_segment_id`：回捞主键。
- `episodes[*].segments[*].scene_index`：所属分集。
- `episodes[*].segments[*].segment_index`：分集内分句序号。
- `episodes[*].segments[*].absolute_index`：全文顺序。
- `episodes[*].segments[*].text`：原文分句。
- `episodes[*].segments[*].emotion`：情绪。
- `episodes[*].segments[*].duration_sec`：已有片段时长。

## 高光 Agent 标准输出

文件：`workspace/plan/highlight_plan.json`

```json
{
  "task_type": "single_highlight_plan",
  "source_run_id": "narration_final_process_xxx",
  "highlight": {
    "highlight_id": "highlight_01",
    "title": "高光标题",
    "selling_point": "投放卖点",
    "hook": "开头钩子",
    "selected_segment_count": 72,
    "blocks": [
      {
        "block_id": "block_01",
        "function": "hook",
        "summary": "这一段为什么入选",
        "scene_index": 1,
        "start_global_segment_id": "scene_001_seg_000",
        "end_global_segment_id": "scene_001_seg_008",
        "segment_count": 9,
        "priority": "must_keep"
      }
    ],
    "shots": [
      {
        "order": 1,
        "global_segment_id": "scene_001_seg_000",
        "scene_index": 1,
        "segment_index": 0,
        "source_text": "对应原文分句",
        "highlight_function": "hook",
        "reason": "强钩子/反转/冲突",
        "priority": "must_keep"
      }
    ]
  }
}
```

## 回捞输出字段

文件：`workspace/plan/highlight_timeline.json`

- `timeline[*].preferred_video_url`：优先拼接的视频，通常是已带字幕/已对轨的 merged 视频。
- `timeline[*].fallback_video_url`：备用原视频。
- `timeline[*].audio_url`：对应音频。
- `timeline[*].keyframe_url`：对应关键帧图。
- `timeline[*].local_filename`：本地下载后的顺序文件名。
- `missing`：无法回捞的分句列表。

## 接入现有 Pipeline 的方式

- 把 `build_segment_pool.py` 放在高光 Agent 前，作为素材池准备节点。
- 高光 Agent 只读 `light_segment_pool.json`，输出 `highlight_plan.json`。
- 后续节点不再让 Agent 重新匹配素材，直接用 `build_timeline.py` 做确定性回捞。
- 本地或服务端都可以跑 `download_and_concat.py`，如果线上环境不适合处理大文件，可以只输出 `highlight_timeline.json` 给本地执行。
