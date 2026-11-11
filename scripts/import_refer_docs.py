#!/usr/bin/env python3
"""import_refer_docs.py — 把根目录 ``refer.txt`` 导入 docs/tushare_refer。

规则：

* ``*-info/`` 行切换分类目录；
* 每个 ``接口：name`` 开始一个接口，标题取接口行之前最近的非空行；
* ``输入参数`` / ``输出参数`` 的制表符表格转 Markdown；
* ``接口用法/接口示例/接口使用`` 转 Python 代码块；
* ``数据样例/数据结果/数据示例`` 转 text 代码块；
* 其余说明文字保留为段落/二级标题。

只新增/覆盖 refer 中出现的接口文件；不删除 docs 下已有的其他接口。
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFER_PATH = PROJECT_ROOT.parent / "refer.txt"
DOCS_ROOT = PROJECT_ROOT / "docs" / "tushare_refer"

CATEGORY_RE = re.compile(r"^[a-z0-9_-]+-info/$")
INTERFACE_RE = re.compile(r"^接口[:：]\s*([A-Za-z0-9_]+)")
INPUT_RE = re.compile(r"输入参数$")
OUTPUT_RE = re.compile(r"输出参数$")
EXAMPLE_RE = re.compile(r"接口(用法|示例|使用)$")
SAMPLE_RE = re.compile(r"数据(样例|结果|示例)$")
META_SKIP = {"接口说明", "接口介绍", "接口", "接口："}
TEXT_HEADINGS = {
    "说明",
    "注意",
    "注",
    "备注",
    "接口说明",
    "算法说明",
    "复权说明",
    "市场说明",
    "代码说明",
    "字段说明",
    "权限说明",
}
TABLE_HEADINGS = {"数据列表", "字段列表", "补充说明"}


@dataclass
class Interface:
    category: str
    name: str
    title: str
    title_index: int
    interface_index: int
    body: list[str] = field(default_factory=list)


@dataclass
class Section:
    heading: str
    kind: str  # table / code / text
    lines: list[str] = field(default_factory=list)


def parse_refer(text: str, *, default_category: str = "") -> list[Interface]:
    lines = text.splitlines()
    markers: list[tuple[int, str]] = []
    starts: list[Interface] = []
    category = default_category
    for index, line in enumerate(lines):
        stripped = line.strip()
        if CATEGORY_RE.fullmatch(stripped):
            category = stripped.rstrip("/")
            markers.append((index, category))
            continue
        match = INTERFACE_RE.match(stripped)
        if not match:
            continue
        title = ""
        title_index = index
        cursor = index - 1
        while cursor >= 0:
            candidate = lines[cursor].strip()
            if candidate and candidate not in META_SKIP:
                title = candidate
                title_index = cursor
                break
            cursor -= 1
        starts.append(
            Interface(
                category=category,
                name=match.group(1),
                title=title,
                title_index=title_index,
                interface_index=index,
            )
        )

    for order, item in enumerate(starts):
        end = len(lines)
        if order + 1 < len(starts):
            end = starts[order + 1].title_index
        for marker_index, _ in markers:
            if item.interface_index < marker_index < end:
                end = marker_index
        item.body = lines[item.interface_index + 1 : end]
    return starts


def _is_heading(line: str) -> tuple[str, str] | None:
    text = line.strip().rstrip("：:")
    if INPUT_RE.search(text):
        return ("输入参数", "table")
    if OUTPUT_RE.search(text):
        return ("输出参数", "table")
    if EXAMPLE_RE.search(text):
        return ("接口示例", "code")
    if SAMPLE_RE.search(text):
        return ("数据样例", "code")
    if text.endswith("参数说明") and len(text) <= 40:
        return (text, "table")
    if text in TABLE_HEADINGS:
        return (text, "table")
    if text in TEXT_HEADINGS:
        return (text, "text")
    return None


def _table(lines: list[str]) -> str:
    rows = [line.rstrip() for line in lines if "\t" in line]
    if not rows:
        return ""
    header = [cell.strip() for cell in rows[0].split("\t")]
    width = len(header)
    out = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in rows[1:]:
        cells = [cell.strip() for cell in row.split("\t")]
        cells = (cells + [""] * width)[:width]
        out.append("| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |")
    return "\n".join(out)


def _paragraphs(lines: list[str]) -> str:
    out: list[str] = []
    buffer: list[str] = []
    for line in lines:
        if line.strip():
            buffer.append(line.rstrip())
        elif buffer:
            out.append("\n".join(buffer))
            buffer = []
    if buffer:
        out.append("\n".join(buffer))
    return "\n\n".join(out)


def render(item: Interface) -> str:
    sections: list[Section] = []
    metadata: list[str] = []
    current: Section | None = None
    for line in item.body:
        stripped = line.strip()
        if stripped in META_SKIP:
            continue
        heading = _is_heading(line)
        if heading is not None:
            current = Section(heading[0], heading[1])
            sections.append(current)
            continue
        if current is None:
            metadata.append(line)
        else:
            current.lines.append(line)
    # 后处理：把同一标题的连续 table section 合并，避免重复标题。
    merged: list[Section] = []
    for section in sections:
        if merged and merged[-1].heading == section.heading and section.kind == "table":
            merged[-1].lines.extend(section.lines)
        else:
            merged.append(section)

    out: list[str] = [f"# {item.title or item.name}", ""]
    out.append(f"接口：`{item.name}`，可以通过数据工具调试和查看数据")
    if metadata:
        text = _paragraphs(metadata)
        if text:
            out.extend(["", text])
    for section in merged:
        content = "\n".join(section.lines).strip("\n")
        if section.kind == "table":
            table = _table(section.lines)
            if not table:
                continue
            out.extend(["", f"## {section.heading}", "", table])
        elif section.kind == "code":
            if not content:
                continue
            language = "text" if section.heading == "数据样例" else "python"
            out.extend(
                ["", f"## {section.heading}", "", f"```{language}", content, "```"]
            )
        else:
            if content:
                out.extend(["", f"## {section.heading}", "", content])
    return "\n".join(out).rstrip() + "\n"


def write_docs(items: list[Interface]) -> list[Path]:
    written: list[Path] = []
    for item in items:
        if not item.category:
            raise ValueError(f"接口 {item.name} 没有分类")
        target_dir = DOCS_ROOT / item.category
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{item.name}.md"
        target.write_text(render(item), encoding="utf-8")
        written.append(target)
    return written


def write_index(items: list[Interface]) -> Path:
    counts: dict[str, int] = {}
    for item in items:
        counts[item.category] = counts.get(item.category, 0) + 1
    descriptions = {
        "basic-info": "股票基础信息、交易日历、ST、名称变更、股权分置等",
        "finance-info": "A 股三大报表、财务指标、分级、业绩预告/快报、审计意见等",
        "quote-info": "A 股日/周/月线、复权因子、每日指标、涨跌停、停复牌、分钟线等",
        "market-info": "异常波动、前十大股东、质押、回购、解禁、大宗交易、账户、增发等",
        "moneyflow-info": "个股/行业/概念/市场资金流向（同花顺、东方财富）",
        "etf-info": "ETF 基础信息、基准指数、实时/历史分钟、日线、复权、份额、持仓",
        "index-info": "指数基础、日/周/月线、成分权重、申万/中信行业分类、指数因子、公告",
        "macro-info": "GDP/CPI/PPI/M2/PMI、Shibor/LPR/Libor/Hibor、美债、韩国市场数据",
        "hk-info": "港股基础、交易日历、日线/复权/分钟、财务报表",
        "sge-info": "上海黄金交易所现货基础信息与日线",
        "fx-info": "人民币汇率中间价、外汇基础/日线、外汇与黄金/SDR 储备",
        "us-info": "美股基础、交易日历、日线/复权、ETF、财务报表",
        "special-info": "盈利预测、筹码分布、技术因子、集合竞价、调研、券商金股等",
        "margin-info": "融资融券、转融通、做空/借券交易",
        "limhit-info": "涨跌停、龙虎榜、游资、同花顺/东方财富/通达信板块与热榜",
        "future-info": "期货基础、日线/复权、结算、持仓、仓单、主力合约映射",
        "bond-info": "可转债基础、发行、赎回、利率、日线、持有人、转股、评级、回购、银行间报价",
    }
    lines = [
        "# Tushare 接口参考",
        "",
        "本目录保存 Tushare Pro 接口的 Markdown 版数据字典与调用说明，",
        "按接口类别分目录，一个接口一个 `.md` 文件。",
        "",
        "- 原始文件：工作区根目录 `refer.txt` 与 `bond-info.txt`；分类依据是文件中的 `*-info/` 标记或导入参数。",
        f"- 本次从源文件导入 {len(items)} 个接口（{len(counts)} 个分类）。",
        f"- 当前接口文件总数：{sum(1 for _ in DOCS_ROOT.rglob('*.md')) - 1}（不含本 README）。",
        "- 生成日期：2026-11-11。",
        "",
        "## 1. 目录",
        "",
        "| 目录 | 文件数 | 内容 |",
        "| --- | ---: | --- |",
    ]
    all_categories = sorted(
        set(counts)
        | {
            "basic-info",
            "finance-info",
            "quote-info",
            "market-info",
            "moneyflow-info",
            "etf-info",
            "index-info",
            "macro-info",
            "hk-info",
            "sge-info",
            "fx-info",
            "us-info",
            "bond-info",
            "special-info",
            "margin-info",
            "limhit-info",
            "future-info",
        }
    )
    for category in all_categories:
        count = sum(1 for path in (DOCS_ROOT / category).glob("*.md"))
        lines.append(f"| `{category}/` | {count} | {descriptions.get(category, '')} |")
    lines.extend(
        [
            "",
            "## 2. 单个文件的结构",
            "",
            "每个接口文件统一包含：",
            "",
            "1. `# 中文名称`",
            "2. `接口：\\`name\\``，以及官方说明",
            "3. 描述 / 限量 / 积分 / 权限等元信息（保留官方原文）",
            "4. `## 输入参数`：名称、类型、必选、描述",
            "5. `## 输出参数`：名称、类型、默认显示、描述",
            "6. `## 接口示例`：Python 调用示例",
            "7. `## 数据样例`：官方返回样例（`text` 代码块）",
            "",
            "## 3. 积分与权限",
            "",
            "- 当前环境按 **5000 积分** token 设计；积分与频率对应表见",
            "  [`basic-info/points_refer.md`](basic-info/points_refer.md)。",
            "- 各接口文件中的“积分 / 权限 / 限量”是**官方原文**，部分接口要求",
            "  6000、8000、10000 积分或单独开通权限；调用前先看目标文件。",
            "",
            "## 4. 安全约定",
            "",
            "- 示例代码中的 token 是占位符，不要替换为真实 token 后提交。",
            "- 真实 token 只放在本机 `.env`，由 `data_pipeline.config` 读取。",
            "",
        ]
    )
    target = DOCS_ROOT / "README.md"
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导入 Tushare refer/bond 文档")
    parser.add_argument(
        "--source",
        type=Path,
        default=REFER_PATH,
        help="源 txt；默认 refer.txt",
    )
    parser.add_argument(
        "--category",
        default="",
        help="源文件没有 *-info/ 分类标记时使用的目录名",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    text = args.source.read_text(encoding="utf-8")
    default_category = args.category or (
        args.source.stem if args.source.stem.endswith("-info") else ""
    )
    items = parse_refer(text, default_category=default_category)
    if not items:
        raise SystemExit(f"{args.source} 中没有找到接口")
    missing = [item.name for item in items if not item.category]
    if missing:
        raise SystemExit(f"以下接口没有分类，请用 --category 指定：{missing[:5]}")
    written = write_docs(items)
    index = write_index(items)
    print(f"source: {args.source}")
    print(f"interfaces: {len(written)}")
    print(f"index: {index}")
    for category in sorted({item.category for item in items}):
        print(f"  {category}: {sum(1 for item in items if item.category == category)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
