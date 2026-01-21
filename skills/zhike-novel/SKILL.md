---
name: zhike-novel
description: 小说创作工作流（zhike_novel）：按SOP推进 Setting/Timeline/outline/map、细纲/正文/词条的创建与更新，并用内置脚本校验项目阶段、文档格式、命名规范、交叉引用与进度传递。
---

# Zhike Novel 小说创作技能

## 快速开始（强制）

> 提示：如果你尚未安装到 Codex，而是在本仓库内直接运行脚本，可把 `SKILL_DIR` 设为 `./skills/zhike-novel`。

1. 先做一次项目状态扫描（只读校验）：

   ```bash
   SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/zhike-novel"
   python3 "$SKILL_DIR/scripts/zn_validate.py" --root .
   ```

   如果希望把 SOP/模板文档也纳入“引用断链”扫描：

   ```bash
   SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/zhike-novel"
   python3 "$SKILL_DIR/scripts/zn_validate.py" --root . --include-sop
   ```

2. 如果需要校验“是否满足进入某一步”的前置条件（进度传递/卡点排查）：

   ```bash
   # 目标可选：background / outline / chapter-outline / drafting
   SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/zhike-novel"
   python3 "$SKILL_DIR/scripts/zn_validate.py" --root . --target outline
   ```

3. 如果项目还是“仅有SOP文件”的状态，可用引导式初始化（只创建缺失目录/空模板，不改已有文件）：

   ```bash
   SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/zhike-novel"
   python3 "$SKILL_DIR/scripts/zn_bootstrap.py" --root .
   ```

   该命令会在根目录创建 `zhike-novel.config.json`（若不存在），后续校验/进度定位将以它为准。

4. 需要让 Agent 100% 幂等定位进度（机器可读输出）：

   ```bash
   SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/zhike-novel"
   python3 "$SKILL_DIR/scripts/zn_validate.py" --root . --format json
   ```

## 工作方式（执行顺序）

1. 开始任何新会话/新任务前：先运行一次 `zn_validate.py`，明确当前阶段、缺失产物、引用断链、命名问题。
2. 决定接下来要跑哪一个SOP步骤时：用 `--target` 做门禁校验（只检查“输入是否齐全”）。
3. 进行任何写作/更新时：严格遵循“最小化原则”和“引用规范”，并在会话结束前更新 `项目状态记录.md`。
4. 遇到冲突：只报告与给方案，不擅自改动冲突处；等待用户确认后再改。

## 需要加载的参考（按需）

- 流程与调用关系：阅读 `references/workflow-map.md`
- 文档规范与校验点：阅读 `references/doc-spec.md`

## 约束（必须遵守）

- 本技能只认“标准结构 + 可选配置”：结构由 `zhike-novel.config.json` 决定；没有配置则使用默认（见 `references/doc-spec.md`）。
- 一切“自动修复/生成”只做“创建缺失项”，不覆盖、不重写、不批量修改既有内容。
- 词条/细纲/正文中出现 `【详见：[xxx.md]】` 必须可解析到真实文件；否则视为断链。
- 每次会话结束前，至少在 `项目状态记录.md` 追加一条“最近更新”，并同步调整任务状态（脚本会对“未更新的进度文档”发出警告）。

## 资源

### scripts/（可直接运行）

- `scripts/zn_validate.py`：阶段探测 + 格式/命名/引用/进度传递校验（只读）
- `scripts/zn_bootstrap.py`：初始化目录与空模板（只创建缺失项）

### references/（按需加载）

- `references/workflow-map.md`：阶段→输入→输出→更新规则→SOP调用关系
- `references/doc-spec.md`：文件/目录命名、必含结构、引用格式与脚本校验清单

### assets/（脚本用模板）

- `assets/project_status_template.md`：`项目状态记录.md` 的模板
