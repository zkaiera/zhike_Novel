# Zhike Novel（Codex Skills 源仓库）

本仓库用于分发 Codex Skills：把技能目录放在 `skills/<skill-name>/` 下，其他人即可通过 Codex 的 `skill-installer` 从 GitHub 直接安装。

## 已包含技能

- `zhike-novel`：小说创作工作流（SOP 推进 + 校验/初始化脚本）

## 仓库结构约定（给维护者）

- 一个技能 = 一个目录：`skills/<skill-name>/`
- 技能入口文档：`skills/<skill-name>/SKILL.md`（需包含 YAML frontmatter：`name` / `description`）
- 技能内部资源保持自包含（`scripts/`、`references/`、`assets/` 等）

