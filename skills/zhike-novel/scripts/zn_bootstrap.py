#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
import json

# 避免在技能目录生成 __pycache__（影响打包与分发）
sys.dont_write_bytecode = True


CONFIG_FILE_NAME = "zhike-novel.config.json"
DEFAULT_CONFIG: dict = {
    "version": 1,
    "files": {
        "project_intro": "项目介绍.md",
        "setting": "Setting.md",
        "timeline": "Timeline.md",
        "outline": "outline.md",
        "map": "map.md",
        "status": "项目状态记录.md",
    },
    "dirs": {
        "entries": "词条",
        "chapter_outlines": "细纲",
        "chapters": "正文",
    },
}


def _exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def _safe_mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _safe_write_new(path: Path, content: str) -> bool:
    """
    只在文件不存在时创建；不覆盖已有内容。
    返回：是否创建成功。
    """
    if _exists(path):
        return False
    path.write_text(content, encoding="utf-8")
    return True


def _read_asset(skill_root: Path, rel: str) -> str:
    p = skill_root / "assets" / rel
    if not _exists(p):
        raise FileNotFoundError(f"缺少资源模板：{p}")
    return p.read_text(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="zn_bootstrap.py",
        description="zhike-novel：初始化目录与空模板（只创建缺失项，不覆盖已有文件）。",
    )
    parser.add_argument("--root", default=".", help="小说项目根目录（默认：.）")
    parser.add_argument("--config", help=f"配置文件路径（默认：{CONFIG_FILE_NAME}）")
    return parser.parse_args()


def _path_within_root(root: Path, target: Path) -> bool:
    try:
        root_resolved = root.resolve()
        target_resolved = target.resolve()
        return root_resolved == target_resolved or root_resolved in target_resolved.parents
    except OSError:
        return False


def _write_json_if_missing(path: Path, obj: dict) -> bool:
    if _exists(path):
        return False
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def _load_config(root: Path, config_path: Path) -> tuple[dict, list[str], list[str]]:
    created: list[str] = []
    skipped: list[str] = []

    if _write_json_if_missing(config_path, DEFAULT_CONFIG):
        created.append(config_path.name)
    else:
        skipped.append(config_path.name)

    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        cfg = DEFAULT_CONFIG.copy()

    if not isinstance(cfg, dict):
        cfg = DEFAULT_CONFIG.copy()

    # 兜底补齐关键字段（不回写，避免覆盖用户配置）
    if not isinstance(cfg.get("files"), dict):
        cfg["files"] = DEFAULT_CONFIG["files"]
    if not isinstance(cfg.get("dirs"), dict):
        cfg["dirs"] = DEFAULT_CONFIG["dirs"]

    # 安全：禁止越界路径（发现越界则回退到默认值）
    for k, v in list(cfg["files"].items()):
        p = root / str(v)
        if not _path_within_root(root, p):
            cfg["files"][k] = DEFAULT_CONFIG["files"].get(k, str(v))
    for k, v in list(cfg["dirs"].items()):
        p = root / str(v)
        if not _path_within_root(root, p):
            cfg["dirs"][k] = DEFAULT_CONFIG["dirs"].get(k, str(v))

    return cfg, created, skipped


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    if not _exists(root) or not root.is_dir():
        sys.stderr.write(f"[ERROR] root 不是有效目录：{root}\n")
        return 2

    # 技能目录：scripts/zn_bootstrap.py 所在目录的上一级
    skill_root = Path(__file__).resolve().parent.parent

    config_path = Path(args.config).resolve() if args.config else (root / CONFIG_FILE_NAME)
    if not _path_within_root(root, config_path):
        sys.stderr.write(f"[ERROR] config 路径越界：{config_path}\n")
        return 2

    cfg, created, skipped = _load_config(root, config_path)
    files = cfg["files"]
    dirs = cfg["dirs"]

    # 根目录基础文档（仅创建空壳，避免和你自定义结构冲突）
    base_files = {
        files["setting"]: "# Setting\n\n> 背景设定（最小可用）。\n",
        files["timeline"]: "# Timeline\n\n> 时间线（先写关键节点）。\n",
        files["outline"]: "# outline\n\n> 故事大纲（总纲/分卷/主支线）。\n",
        files["map"]: "# map\n\n> 地图/地点/势力分布（最小可用）。\n",
        files["project_intro"]: "# 项目简介\n\n> 填写项目定位、受众与创作要求（推荐）。\n",
    }

    for rel_name, content in base_files.items():
        name = str(rel_name)
        if _safe_write_new(root / name, content):
            created.append(name)
        else:
            skipped.append(name)

    # 进度文档：使用 assets 模板
    try:
        status_template = _read_asset(skill_root, "project_status_template.md")
    except Exception as exc:
        sys.stderr.write(f"[ERROR] 无法读取进度模板：{exc}\n")
        return 2

    status_name = str(files["status"])
    if _safe_write_new(root / status_name, status_template):
        created.append(status_name)
    else:
        skipped.append(status_name)

    for key in ("entries", "chapter_outlines", "chapters"):
        d = str(dirs[key])
        p = root / d
        if not _exists(p):
            _safe_mkdir(p)
            created.append(f"{d}/")
        else:
            skipped.append(f"{d}/")

    sys.stdout.write(f"项目根目录：{root}\n")
    sys.stdout.write(f"配置文件：{config_path}\n\n")
    sys.stdout.write("=== 创建结果（仅创建缺失项）===\n")
    for item in created:
        sys.stdout.write(f"[CREATE] {item}\n")
    for item in skipped:
        sys.stdout.write(f"[SKIP] {item}\n")

    sys.stdout.write("\n下一步建议：运行校验脚本确认门禁与格式。\n")
    validate_script = skill_root / "scripts" / "zn_validate.py"
    sys.stdout.write(f'  python3 "{validate_script}" --root .\n')
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        sys.stderr.write(f"[ERROR] 脚本异常：{exc}\n")
        raise SystemExit(2)
