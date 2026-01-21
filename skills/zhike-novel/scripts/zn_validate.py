#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import json

# 避免在技能目录生成 __pycache__（影响打包与分发）
sys.dont_write_bytecode = True


BASE_IGNORE_DIR_NAMES = {
    ".git",
    "node_modules",
    "dist",
    "build",
    ".venv",
    "venv",
    "__pycache__",
    "skills",  # 避免把技能自身当作“小说项目文档”
}

ENTRY_NAME_RE = re.compile(r"^(角色|场景|势力|其他)-.+\\.md$")
CHAPTER_OUTLINE_NAME_RE = re.compile(r"^第\\d+章\\.md$")
CHAPTER_NAME_RE = re.compile(r"^第\\d+章\\s+.+\\.md$")

REF_RE = re.compile(r"【详见：\[(?P<ref>[^\]]+)\]】")

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


@dataclass(frozen=True)
class Issue:
    level: str  # "ERROR" | "WARN"
    message: str
    path: Path | None = None

    def format(self) -> str:
        where = f" ({self.path})" if self.path else ""
        return f"[{self.level}] {self.message}{where}"


def _safe_read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _iter_project_md_files(root: Path, *, include_sop: bool) -> list[Path]:
    files: list[Path] = []
    for p in root.rglob("*.md"):
        if any(part in BASE_IGNORE_DIR_NAMES for part in p.parts):
            continue
        if not include_sop:
            # SOP/模板文件经常包含“示例引用”，默认不参与断链校验；需要时可用 --include-sop 纳入扫描。
            if any("SOP" in part for part in p.parts) or "SOP" in p.name:
                continue
        files.append(p)
    return sorted(files)


def _exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def _non_empty_file(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _path_within_root(root: Path, target: Path) -> bool:
    try:
        root_resolved = root.resolve()
        target_resolved = target.resolve()
        return root_resolved == target_resolved or root_resolved in target_resolved.parents
    except OSError:
        return False


@dataclass(frozen=True)
class ProjectPaths:
    config_path: Path
    project_intro: Path
    setting: Path
    timeline: Path
    outline: Path
    map: Path
    status: Path

    entries_dir: Path
    chapter_outlines_dir: Path
    chapters_dir: Path


def _load_config(root: Path, config_path: Path | None) -> tuple[dict, ProjectPaths, list[Issue]]:
    issues: list[Issue] = []
    path = config_path or (root / CONFIG_FILE_NAME)

    cfg: dict
    if _exists(path):
        try:
            cfg = json.loads(_safe_read_text(path))
        except Exception as exc:
            cfg = DEFAULT_CONFIG.copy()
            issues.append(Issue("ERROR", f"配置文件解析失败，将退回默认配置：{exc}", path))
    else:
        cfg = DEFAULT_CONFIG.copy()
        issues.append(Issue("WARN", f"未发现配置文件，将使用默认结构：{CONFIG_FILE_NAME}", path))

    if not isinstance(cfg, dict):
        cfg = DEFAULT_CONFIG.copy()
        issues.append(Issue("ERROR", "配置文件内容不是 JSON object，将退回默认配置", path))

    files = cfg.get("files") if isinstance(cfg.get("files"), dict) else DEFAULT_CONFIG["files"]
    dirs = cfg.get("dirs") if isinstance(cfg.get("dirs"), dict) else DEFAULT_CONFIG["dirs"]

    def rel_file(key: str) -> Path:
        rel = str(files.get(key, DEFAULT_CONFIG["files"][key]))
        p = (root / rel)
        if not _path_within_root(root, p):
            issues.append(Issue("ERROR", f"配置越界：files.{key} 指向了项目根目录之外", path))
            return root / DEFAULT_CONFIG["files"][key]
        return p

    def rel_dir(key: str) -> Path:
        rel = str(dirs.get(key, DEFAULT_CONFIG["dirs"][key]))
        p = (root / rel)
        if not _path_within_root(root, p):
            issues.append(Issue("ERROR", f"配置越界：dirs.{key} 指向了项目根目录之外", path))
            return root / DEFAULT_CONFIG["dirs"][key]
        return p

    paths = ProjectPaths(
        config_path=path,
        project_intro=rel_file("project_intro"),
        setting=rel_file("setting"),
        timeline=rel_file("timeline"),
        outline=rel_file("outline"),
        map=rel_file("map"),
        status=rel_file("status"),
        entries_dir=rel_dir("entries"),
        chapter_outlines_dir=rel_dir("chapter_outlines"),
        chapters_dir=rel_dir("chapters"),
    )

    return cfg, paths, issues


def _placeholder_score(text: str) -> int:
    """
    只做非常粗糙的“占位符”检测：用于给出“可能未填写完”的提示，不作为硬性失败条件。
    """
    patterns = [
        r"\[YYYY\-MM\-DD\]",
        r"\[0%~100%\]",
        r"\[小说名称\]",
        r"\[核心故事线\]",
        r"\[目标受众群体\]",
        r"\[任务\d+\]",
        r"\[.*?xx.*?\]",
        r"\[.*?XX.*?\]",
    ]
    score = 0
    for pat in patterns:
        score += len(re.findall(pat, text))
    return score


def _check_required_headings(path: Path, text: str, headings: list[str]) -> list[Issue]:
    issues: list[Issue] = []
    for h in headings:
        if h not in text:
            issues.append(Issue("ERROR", f"缺少必要标题：{h}", path))
    return issues


def validate_entries(entry_dir: Path) -> list[Issue]:
    issues: list[Issue] = []
    if not _exists(entry_dir):
        issues.append(Issue("WARN", f"词条目录不存在：{entry_dir}（后续将无法进行引用/出场记录管理）", entry_dir))
        return issues

    for p in sorted(entry_dir.glob("*.md")):
        if not ENTRY_NAME_RE.match(p.name):
            issues.append(Issue("ERROR", "词条文件命名不符合：必须以 角色-/场景-/势力-/其他- 开头", p))
            continue
        text = _safe_read_text(p)
        first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
        if not first_line.startswith("# "):
            issues.append(Issue("ERROR", "词条文件首个非空行应以“# ”开头作为标题", p))
        issues.extend(
            _check_required_headings(
                p,
                text,
                headings=["## 基本信息", "## 关联信息", "## 出场记录"],
            )
        )
    return issues


def validate_chapter_outlines(chapter_outlines_dir: Path) -> tuple[list[Issue], int]:
    issues: list[Issue] = []
    if not _exists(chapter_outlines_dir):
        issues.append(Issue("WARN", f"未发现细纲目录：{chapter_outlines_dir}（细纲创作/正文创作可能尚未开始）", chapter_outlines_dir))
        return issues, 0

    required = [
        "## 爽点设计",
        "## 剧情承接",
        "## 出场要素",
        "## 剧情大纲",
        "## 转场设计",
        "## 新要素标记",
    ]
    count = 0
    for p in sorted(chapter_outlines_dir.glob("*.md")):
        if not CHAPTER_OUTLINE_NAME_RE.match(p.name):
            continue
        count += 1
        text = _safe_read_text(p)
        first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
        if not first_line.startswith("# 第"):
            issues.append(Issue("ERROR", "细纲文件首个非空行应形如“# 第XX章 章节标题”", p))
        issues.extend(_check_required_headings(p, text, required))
    return issues, count


def validate_chapters(chapters_dir: Path, chapter_outlines_dir: Path) -> tuple[list[Issue], int]:
    issues: list[Issue] = []
    if not _exists(chapters_dir):
        issues.append(Issue("WARN", f"未发现正文目录：{chapters_dir}（正文创作可能尚未开始）", chapters_dir))
        return issues, 0

    count = 0
    for p in sorted(chapters_dir.glob("*.md")):
        if CHAPTER_NAME_RE.match(p.name):
            count += 1
            m = re.match(r"^第(\\d+)章\\s+.+\\.md$", p.name)
            if m and _exists(chapter_outlines_dir):
                outline_file = chapter_outlines_dir / f"第{m.group(1)}章.md"
                if not _exists(outline_file):
                    issues.append(Issue("WARN", f"对应细纲缺失：{outline_file.name}", p))
            continue
        # 允许正文目录中存在其他 md（例如“写作计划.md”），但给出提示便于清理/归档
        issues.append(Issue("WARN", "正文目录中存在不符合章节命名的 md（建议移出或重命名为：第X章 章节标题.md）", p))
    return issues, count


def validate_references(root: Path, *, include_sop: bool, candidates: list[Path]) -> list[Issue]:
    issues: list[Issue] = []
    md_files = _iter_project_md_files(root, include_sop=include_sop)
    for f in md_files:
        text = _safe_read_text(f)
        for m in REF_RE.finditer(text):
            ref = m.group("ref").strip()
            found = False
            for base in candidates:
                if not _exists(base):
                    continue
                target = (base / ref) if base.is_dir() else (base.parent / ref)
                if _exists(target):
                    found = True
                    break
            if not found:
                issues.append(Issue("ERROR", f"引用断链：{ref}", f))
    return issues


def _parse_declared_stage_from_progress(text: str) -> str | None:
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("-"):
            continue
        # 兼容中文/英文冒号
        if "所处阶段" in s:
            parts = s.split("：", 1)
            if len(parts) == 2:
                v = parts[1].strip()
            else:
                parts = s.split(":", 1)
                v = parts[1].strip() if len(parts) == 2 else ""
            if not v:
                return None
            # 去掉括号
            if v.startswith("[") and v.endswith("]"):
                v = v[1:-1].strip()
            return v or None
    return None


def _normalize_declared_stage(stage_text: str | None) -> str | None:
    """
    将进度文档里的中文阶段映射到脚本内部阶段。
    无法识别或明显是占位符时返回 None。
    """
    if not stage_text:
        return None
    s = stage_text.strip()
    if not s or "/" in s:
        return None
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1].strip()
    mapping = {
        "未开始": "init",
        "背景设定": "background",
        "大纲创作": "outline",
        "细纲创作": "chapter-outline",
        "正文创作": "drafting",
        "质量检查": "qa",
    }
    return mapping.get(s)


def validate_progress_doc(progress_path: Path, *, root: Path) -> list[Issue]:
    issues: list[Issue] = []
    if not _exists(progress_path):
        issues.append(Issue("WARN", "未发现项目进度文档：项目状态记录.md（建议创建并在每次会话结束前更新）"))
        return issues

    text = _safe_read_text(progress_path)
    issues.extend(
        _check_required_headings(
            progress_path,
            text,
            headings=["# 项目状态记录", "## 当前阶段", "## 任务状态", "## 最近更新", "## 注意事项"],
        )
    )

    placeholders = _placeholder_score(text)
    if placeholders >= 3:
        issues.append(Issue("WARN", f"项目状态记录.md 仍包含较多占位符（计数={placeholders}），可能尚未填写/更新", progress_path))

    try:
        newest = max((p.stat().st_mtime for p in _iter_project_md_files(root, include_sop=False)), default=None)
        if newest and progress_path.stat().st_mtime + 300 < newest:
            issues.append(Issue("WARN", "项目状态记录.md 的修改时间早于其他文档，可能忘记在会话结束前同步进度", progress_path))
    except OSError:
        pass

    return issues


def _is_meaningful_doc(path: Path) -> bool:
    """
    幂等进度定位的“客观证据”之一：文件存在且不像空模板。
    规则尽量保守：宁愿认为“未完成”，也不轻易跳到更后阶段。
    """
    if not _exists(path):
        return False
    try:
        text = _safe_read_text(path)
    except OSError:
        return False
    stripped = text.strip()
    if len(stripped) < 80:
        return False
    non_empty_lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(non_empty_lines) < 5:
        return False
    # 明显占位符太多时，倾向认为仍未填写完
    if _placeholder_score(text) >= 3 and len(stripped) < 400:
        return False
    return True


def infer_stage(paths: ProjectPaths) -> tuple[str, dict]:
    """
    目标：在“任意仓库状态/新会话”下，尽可能稳定地定位当前进度。
    规则优先级：客观产物（文件/目录）> 进度文档声明（可能过期）> 兜底推断。
    """
    counters: dict[str, int] = {"entries": 0, "chapter_outlines": 0, "chapters": 0}

    if _exists(paths.entries_dir):
        counters["entries"] = len(list(paths.entries_dir.glob("*.md")))
    if _exists(paths.chapter_outlines_dir):
        counters["chapter_outlines"] = len([p for p in paths.chapter_outlines_dir.glob("*.md") if CHAPTER_OUTLINE_NAME_RE.match(p.name)])
    if _exists(paths.chapters_dir):
        counters["chapters"] = len([p for p in paths.chapters_dir.glob("*.md") if CHAPTER_NAME_RE.match(p.name)])

    has_any_base = any(_exists(p) for p in (paths.setting, paths.timeline, paths.outline, paths.map))
    has_any_dirs = any(_exists(d) for d in (paths.entries_dir, paths.chapter_outlines_dir, paths.chapters_dir))
    if not has_any_base and not has_any_dirs:
        return "init", counters

    # 正文阶段（只要章节文件出现）
    if counters["chapters"] > 0:
        return "drafting", counters

    # 细纲阶段（只要章细纲出现）
    if counters["chapter_outlines"] > 0:
        return "chapter-outline", counters

    # 大纲阶段：outline “有内容”才认为进入
    if _is_meaningful_doc(paths.outline):
        return "outline", counters

    # 背景设定阶段：Setting “有内容”才认为进入
    if _is_meaningful_doc(paths.setting):
        return "background", counters

    return "init", counters


def _stage_label(stage: str) -> str:
    labels = {
        "init": "init（未建立项目基础产物）",
        "background": "background（背景设定）",
        "outline": "outline（大纲创作）",
        "chapter-outline": "chapter-outline（细纲创作）",
        "drafting": "drafting（正文创作）",
        "qa": "qa（质量检查）",
    }
    return labels.get(stage, stage)


def gate_check(paths: ProjectPaths, target: str) -> list[Issue]:
    issues: list[Issue] = []

    def need_file(p: Path, msg: str) -> None:
        if not _exists(p):
            issues.append(Issue("ERROR", msg, p))

    def need_meaningful(p: Path, msg: str) -> None:
        if not _is_meaningful_doc(p):
            issues.append(Issue("ERROR", msg, p))

    def need_dir(p: Path, msg: str) -> None:
        if not _exists(p):
            issues.append(Issue("ERROR", msg, p))

    if target == "background":
        if not _exists(paths.project_intro):
            issues.append(Issue("WARN", "建议补充：项目介绍.md（作为背景设定输入与风格/目标约束）", paths.project_intro))
        return issues

    if target == "outline":
        need_meaningful(paths.setting, f"进入大纲创作前需要：{paths.setting.name}（需要有实际内容，而不是空模板）")
        need_meaningful(paths.timeline, f"进入大纲创作前需要：{paths.timeline.name}（需要有实际内容，而不是空模板）")
        need_meaningful(paths.map, f"进入大纲创作前需要：{paths.map.name}（需要有实际内容，而不是空模板）")
        need_dir(paths.entries_dir, f"进入大纲创作前建议先建立词条目录：{paths.entries_dir.name}/")
        return issues

    if target == "chapter-outline":
        need_meaningful(paths.setting, f"进入细纲创作前需要：{paths.setting.name}（需要有实际内容，而不是空模板）")
        need_dir(paths.chapter_outlines_dir, f"进入细纲创作前需要目录：{paths.chapter_outlines_dir.name}/")
        if not _is_meaningful_doc(paths.outline):
            issues.append(Issue("WARN", f"建议先完善 {paths.outline.name} 再进行细纲创作（否则容易丢失主线/支线衔接）", paths.outline))
        return issues

    if target == "drafting":
        need_dir(paths.chapters_dir, f"进入正文创作前需要目录：{paths.chapters_dir.name}/")
        need_dir(paths.chapter_outlines_dir, f"进入正文创作前需要目录：{paths.chapter_outlines_dir.name}/（每章细纲独立文件）")
        if _exists(paths.chapter_outlines_dir):
            has_any_chapter_outline = any(CHAPTER_OUTLINE_NAME_RE.match(p.name) for p in paths.chapter_outlines_dir.glob("*.md"))
            if not has_any_chapter_outline:
                issues.append(Issue("ERROR", f"进入正文创作前需要至少一份细纲文件：{paths.chapter_outlines_dir.name}/第X章.md", paths.chapter_outlines_dir))
        return issues

    issues.append(Issue("ERROR", f"未知 target：{target}（可选：background/outline/chapter-outline/drafting）"))
    return issues


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="zn_validate.py",
        description="zhike-novel：校验小说项目的阶段、文档格式、命名规范、交叉引用与进度传递（只读）。",
    )
    parser.add_argument("--root", default=".", help="小说项目根目录（默认：.）")
    parser.add_argument("--config", help=f"配置文件路径（默认：{CONFIG_FILE_NAME}）")
    parser.add_argument(
        "--target",
        choices=["background", "outline", "chapter-outline", "drafting"],
        help="门禁校验：只检查进入目标步骤的前置输入是否齐全",
    )
    parser.add_argument(
        "--include-sop",
        action="store_true",
        help="将 SOP/模板文档也纳入“引用断链”扫描（默认不扫，避免示例引用误报）",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="输出格式：text（默认，人类阅读）或 json（给 Agent 做幂等进度定位/决策）",
    )
    return parser.parse_args()


def _compute_next_target(inferred_stage: str, gate_errors_by_target: dict[str, int]) -> str | None:
    """
    幂等入口：优先根据“客观阶段”给出下一步，再用门禁错误做兜底。
    """
    if inferred_stage == "init":
        return "background"

    if inferred_stage == "background":
        return "outline" if gate_errors_by_target.get("outline", 0) > 0 else None

    if inferred_stage == "outline":
        return "chapter-outline"

    if inferred_stage == "chapter-outline":
        return "drafting" if gate_errors_by_target.get("drafting", 0) > 0 else None

    # drafting/qa 这类阶段的“下一步”依赖人类意图（继续写/修订/质检），不强制推断
    # 兜底：找第一个不满足门禁的步骤
    order = ["background", "outline", "chapter-outline", "drafting"]
    for t in order:
        if gate_errors_by_target.get(t, 0) > 0:
            return t
    return None


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    if not _exists(root) or not root.is_dir():
        if args.format == "json":
            sys.stdout.write(json.dumps({"ok": False, "error": f"root 不是有效目录：{root}"}, ensure_ascii=False) + "\n")
            return 2
        sys.stderr.write(f"[ERROR] root 不是有效目录：{root}\n")
        return 2

    _cfg, paths, config_issues = _load_config(root, Path(args.config).resolve() if args.config else None)
    objective_stage, counters = infer_stage(paths)

    declared_stage: str | None = None
    if _exists(paths.status):
        declared_stage = _parse_declared_stage_from_progress(_safe_read_text(paths.status))
    declared_stage_norm = _normalize_declared_stage(declared_stage)

    # 最终阶段：强证据优先（章节/细纲），否则优先相信进度文档（如果可解析），最后再用客观推断兜底。
    if objective_stage in ("drafting", "chapter-outline"):
        inferred_stage = objective_stage
    elif declared_stage_norm:
        inferred_stage = declared_stage_norm
    else:
        inferred_stage = objective_stage

    issues: list[Issue] = []
    issues.extend(config_issues)
    gate_errors_by_target: dict[str, int] = {}
    targets_to_check = [args.target] if args.target else ["background", "outline", "chapter-outline", "drafting"]
    for t in targets_to_check:
        t_issues = gate_check(paths, t)
        gate_errors_by_target[t] = len([i for i in t_issues if i.level == "ERROR"])
        if args.target:
            issues.extend(t_issues)

    # 结构检查（尽量给出“能做下一步”的提示）
    issues.extend(validate_entries(paths.entries_dir))
    outline_issues, outline_count = validate_chapter_outlines(paths.chapter_outlines_dir)
    issues.extend(outline_issues)
    chapter_issues, chapter_count = validate_chapters(paths.chapters_dir, paths.chapter_outlines_dir)
    issues.extend(chapter_issues)

    issues.extend(
        validate_references(
            root,
            include_sop=args.include_sop,
            candidates=[root, paths.entries_dir, paths.chapter_outlines_dir, paths.chapters_dir],
        )
    )

    issues.extend(validate_progress_doc(paths.status, root=root))

    # 进度文档声明与强客观证据不一致时，提示“可能过期”
    if declared_stage_norm and objective_stage in ("drafting", "chapter-outline") and declared_stage_norm != objective_stage:
        issues.append(
            Issue(
                "WARN",
                f"项目状态记录.md 声明阶段与客观产物（章/细纲）不一致：建议更新进度文档以保持幂等续跑",
                paths.status,
            )
        )

    errors = [i for i in issues if i.level == "ERROR"]
    warns = [i for i in issues if i.level == "WARN"]

    next_target = _compute_next_target(inferred_stage, gate_errors_by_target)
    recommended_commands: list[str] = []
    # 技能目录：scripts/zn_validate.py 所在目录的上一级
    skill_root = Path(__file__).resolve().parent.parent
    validate_script = skill_root / "scripts" / "zn_validate.py"
    bootstrap_script = skill_root / "scripts" / "zn_bootstrap.py"
    # init 阶段：优先给 bootstrap（否则门禁校验没有实际推进意义）
    if inferred_stage == "init":
        recommended_commands.append(f'python3 "{bootstrap_script}" --root .')
        recommended_commands.append(f'python3 "{validate_script}" --root .')
    elif next_target:
        recommended_commands.append(f'python3 "{validate_script}" --root . --target {next_target}')
    else:
        recommended_commands.append(f'python3 "{validate_script}" --root .')

    if args.format == "json":
        payload = {
            "ok": len(errors) == 0,
            "root": str(root),
            "config_path": str(paths.config_path),
            "config_loaded": _exists(paths.config_path),
            "paths": {
                "project_intro": str(paths.project_intro),
                "setting": str(paths.setting),
                "timeline": str(paths.timeline),
                "outline": str(paths.outline),
                "map": str(paths.map),
                "status": str(paths.status),
                "entries_dir": str(paths.entries_dir),
                "chapter_outlines_dir": str(paths.chapter_outlines_dir),
                "chapters_dir": str(paths.chapters_dir),
            },
            "objective_stage": objective_stage,
            "inferred_stage": inferred_stage,
            "declared_stage": declared_stage,
            "declared_stage_normalized": declared_stage_norm,
            "next_target": next_target,
            "gate_errors_by_target": gate_errors_by_target,
            "counts": {"entries": counters.get("entries", 0), "chapter_outlines": outline_count, "chapters": chapter_count},
            "issue_counts": {"ERROR": len(errors), "WARN": len(warns)},
            "issues": [
                {"level": i.level, "message": i.message, "path": str(i.path) if i.path else None}
                for i in issues
            ],
            "recommended_commands": recommended_commands,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return 1 if errors else 0

    sys.stdout.write(f"项目根目录：{root}\n")
    sys.stdout.write(f"配置文件：{paths.config_path}（{'存在' if _exists(paths.config_path) else '不存在，使用默认'}）\n")
    sys.stdout.write(f"客观推断阶段：{_stage_label(objective_stage)}\n")
    sys.stdout.write(f"最终采用阶段：{_stage_label(inferred_stage)}\n")
    if declared_stage:
        sys.stdout.write(f"进度文档声明：{declared_stage}\n")

    if issues:
        sys.stdout.write("\n=== 校验结果 ===\n")
        for i in issues:
            sys.stdout.write(i.format() + "\n")
    else:
        sys.stdout.write("\n=== 校验结果 ===\n[OK] 未发现问题。\n")

    sys.stdout.write("\n=== 汇总 ===\n")
    sys.stdout.write(f"错误：{len(errors)}，警告：{len(warns)}\n")
    sys.stdout.write(f"建议下一步 target：{next_target or '（无）'}\n")
    if recommended_commands:
        sys.stdout.write("建议命令：\n")
        for c in recommended_commands[:5]:
            sys.stdout.write(f"  {c}\n")
    sys.stdout.write(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    return 1 if errors else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        # 允许通过管道截断输出（例如：| head）
        raise
    except Exception as exc:
        sys.stderr.write(f"[ERROR] 脚本异常：{exc}\n")
        raise SystemExit(2)
