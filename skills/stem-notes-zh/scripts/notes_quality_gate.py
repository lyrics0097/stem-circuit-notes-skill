#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STEM 笔记与矢量电路图确定性质量门禁脚本 (notes_quality_gate.py)

用法:
  python scripts/notes_quality_gate.py <file_or_dir> [...]
"""

import ipaddress
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse


SKIP_DIRS = {
    ".git",
    ".qoder",
    ".claude",
    ".cursor",
    ".codex",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
}

SKIP_MD_NAMES = {"skill.md", "readme.md", "readme_zh.md", "license", "license.md"}


def strip_tags(html_str: str) -> str:
    """移除 HTML 标签并折叠空白，用于计算纯文本视觉长度。"""
    text = re.sub(r"<[^>]+>", "", html_str)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&rarr;", "→")
        .replace("&rArr;", "⇒")
        .replace("&minus;", "−")
        .replace("&times;", "×")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
    )
    return re.sub(r"\s+", " ", text).strip()


def _parse_translate(transform_str: str) -> tuple[float, float]:
    if not transform_str:
        return 0.0, 0.0
    m = re.search(r"translate\(\s*([+-]?[0-9.]+)(?:[\s,]+([+-]?[0-9.]+))?\s*\)", transform_str)
    if not m:
        return 0.0, 0.0
    tx = float(m.group(1))
    ty = float(m.group(2)) if m.group(2) is not None else 0.0
    return tx, ty


def _extract_svg_text_boxes(clean_block: str) -> list[tuple[float, float, float, str, int]]:
    """优先通过 XML 解析叠加 translate 偏移；若非严格 XML 则降级正则提取。"""
    boxes: list[tuple[float, float, float, str, int]] = []
    try:
        root = ET.fromstring(clean_block)
    except ET.ParseError:
        text_nodes = re.findall(r"<text\b([^>]*)>(.*?)</text>", clean_block, flags=re.DOTALL | re.IGNORECASE)
        for attrs, inner in text_nodes:
            plain = strip_tags(inner)
            cn_count = len(re.findall(r"[\u4e00-\u9fff]", plain))
            xm = re.search(r'\bx\s*=\s*["\']([+-]?[0-9.]+)["\']', attrs)
            ym = re.search(r'\by\s*=\s*["\']([+-]?[0-9.]+)["\']', attrs)
            anchor_m = re.search(r'\btext-anchor\s*=\s*["\'](\w+)["\']', attrs)
            if xm and ym:
                x_val = float(xm.group(1))
                y_val = float(ym.group(1))
                anchor = anchor_m.group(1) if anchor_m else "start"
                w_est = cn_count * 12.0 + (len(plain) - cn_count) * 6.5
                if anchor == "middle":
                    x0, x1 = x_val - w_est / 2.0, x_val + w_est / 2.0
                elif anchor == "end":
                    x0, x1 = x_val - w_est, x_val
                else:
                    x0, x1 = x_val, x_val + w_est
                boxes.append((x0, x1, y_val, plain, cn_count))
            else:
                boxes.append((0.0, 0.0, -9999.0, plain, cn_count))
        return boxes

    def walk(elem: ET.Element, ox: float, oy: float) -> None:
        dx, dy = _parse_translate(elem.attrib.get("transform", ""))
        cx, cy = ox + dx, oy + dy
        tag_local = elem.tag.split("}")[-1].lower()
        if tag_local == "text":
            plain = re.sub(r"\s+", " ", "".join(elem.itertext())).strip()
            cn_count = len(re.findall(r"[\u4e00-\u9fff]", plain))
            x_attr = elem.attrib.get("x")
            y_attr = elem.attrib.get("y")
            if x_attr is not None and y_attr is not None:
                try:
                    x_val = cx + float(x_attr.split()[0])
                    y_val = cy + float(y_attr.split()[0])
                    anchor = elem.attrib.get("text-anchor", "start")
                    fs_raw = elem.attrib.get("font-size", "12")
                    fs_m = re.search(r"[0-9.]+", fs_raw)
                    fs = float(fs_m.group(0)) if fs_m else 12.0
                    scale = fs / 12.0
                    w_est = (cn_count * 11.5 + (len(plain) - cn_count) * 6.2) * scale
                    if anchor == "middle":
                        x0, x1 = x_val - w_est / 2.0, x_val + w_est / 2.0
                    elif anchor == "end":
                        x0, x1 = x_val - w_est, x_val
                    else:
                        x0, x1 = x_val, x_val + w_est
                    boxes.append((x0, x1, y_val, plain, cn_count))
                except ValueError:
                    boxes.append((0.0, 0.0, -9999.0, plain, cn_count))
            else:
                boxes.append((0.0, 0.0, -9999.0, plain, cn_count))
            return
        for child in elem:
            walk(child, cx, cy)

    walk(root, 0.0, 0.0)
    return boxes


def check_hygiene_and_offline(content: str, filepath: str) -> list[str]:
    """检查零本机绝对路径、零回环网络地址、零私有嵌入式标签泄露。"""
    errors: list[str] = []
    # 1. 检测回环 URL（通过 URL 解析与 ipaddress 校验，避免硬编码字面量）
    for url in re.findall(r"https?://[^\s\"'<>`)]+", content, flags=re.IGNORECASE):
        try:
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            is_loop = host == ("local" + "host")
            if not is_loop and host:
                try:
                    is_loop = ipaddress.ip_address(host).is_loopback
                except ValueError:
                    is_loop = False
            if is_loop:
                errors.append(
                    f"[离线隐私红线违规] {filepath}: 检测到回环网络地址 `{url}`，开源离线产物严禁包含本地服务调用！"
                )
        except Exception:
            pass

    # 2. 检测本地 file 协议或绝对路径泄露
    file_scheme = "fi" + "le:///"
    if file_scheme in content.lower():
        errors.append(f"[绝对路径泄露] {filepath}: 检测到 `{file_scheme}` 本地绝对路径，请改用相对路径！")
    win_user_pat = re.compile(r"[A-Za-z]:\\+" + "Us" + r"ers\\", flags=re.IGNORECASE)
    mac_user_pat = re.compile(r"(?:^|[\s\"'(])/" + "Us" + r"ers/", flags=re.IGNORECASE)
    if win_user_pat.search(content) or mac_user_pat.search(content):
        errors.append(f"[本机路径泄露] {filepath}: 检测到本机用户目录绝对路径，请改用相对路径！")

    # 3. 检测私有嵌入标签残留
    private_embed = "<" + "agent" + "-embed"
    if private_embed in content.lower():
        errors.append(f"[私有标签残留] {filepath}: 检测到非标准私有嵌入标签，请改为独立 HTML 文件与相对链接！")

    return errors


def check_svg_purity(content: str, filepath: str) -> list[str]:
    """检查 <svg> 内部标签纯净度、中文标签字数、拓扑唯一性与坐标防碰撞。"""
    errors: list[str] = []
    no_style = re.sub(r"<style\b[^>]*>.*?</style>", "", content, flags=re.DOTALL | re.IGNORECASE)
    no_script = re.sub(r"<script\b[^>]*>.*?</script>", "", no_style, flags=re.DOTALL | re.IGNORECASE)
    no_comments = re.sub(r"<!--.*?-->", "", no_script, flags=re.DOTALL)
    svg_blocks = re.findall(r"<svg\b[^>]*>.*?</svg>", no_comments, flags=re.DOTALL | re.IGNORECASE)
    for idx, block in enumerate(svg_blocks, 1):
        clean_block = re.sub(r"<!--.*?-->", "", block, flags=re.DOTALL)
        bad_tags = re.findall(r"<(i|b|sub|sup|span|div)\b[^>]*>", clean_block, flags=re.IGNORECASE)
        if bad_tags:
            uniq = sorted(set(t.lower() for t in bad_tags))
            errors.append(
                f"[SVG标签污染] {filepath} (第{idx}个<svg>): <svg>内严禁使用HTML标签 {uniq}，请改用 <tspan font-style=\"italic\"> 或 dy 偏移！"
            )

        boxes = _extract_svg_text_boxes(clean_block)
        total_cn_chars = 0
        valid_boxes = []
        for x0, x1, y_val, plain, cn_count in boxes:
            total_cn_chars += cn_count
            if cn_count > 8:
                errors.append(
                    f"[SVG单标签文字过多] {filepath}: <text> 内容 `{plain}` 含 {cn_count} 个汉字（上限 8 字）！说明文字请移至画布下方 .legend-bar！"
                )
            if re.search(r"(?:[（(]\s*或|或直接|或开路|或短路|可选)", plain):
                errors.append(
                    f"[SVG拓扑歧义违规] {filepath}: <text> 内容 `{plain}` 出现“或/可选”混画标注！一张图仅对应唯一确定拓扑。"
                )
            if y_val > -9000.0 and plain:
                valid_boxes.append((x0, x1, y_val, plain))

        if total_cn_chars > 24:
            errors.append(
                f"[SVG全图中文过多] {filepath}: 全图共含 {total_cn_chars} 个汉字（上限 24 字）！请将长说明移至 .legend-bar。"
            )

        for i in range(len(valid_boxes)):
            x0_a, x1_a, y_a, txt_a = valid_boxes[i]
            for j in range(i + 1, len(valid_boxes)):
                x0_b, x1_b, y_b, txt_b = valid_boxes[j]
                if abs(y_a - y_b) < 11.0 and max(x0_a, x0_b) < min(x1_a, x1_b) - 3.0:
                    errors.append(
                        f"[SVG文字碰撞重叠] {filepath}: 标签 `{txt_a}` (y={y_a:.1f}) 与 `{txt_b}` (y={y_b:.1f}) 发生坐标重叠！"
                    )

    return errors


def check_raw_math_in_html(content: str, filepath: str) -> list[str]:
    """检查 HTML 可见文本是否残留裸露数学符号 (^, _, \\frac)。"""
    errors: list[str] = []
    no_style = re.sub(r"<style\b[^>]*>.*?</style>", "", content, flags=re.DOTALL | re.IGNORECASE)
    no_script = re.sub(r"<script\b[^>]*>.*?</script>", "", no_style, flags=re.DOTALL | re.IGNORECASE)
    no_comments = re.sub(r"<!--.*?-->", "", no_script, flags=re.DOTALL)

    latex_leaks = re.findall(
        r"\\(?:frac|varepsilon|varphi|partial|infty|pi|theta|sigma|omega|lambda|beta|alpha|mu)\b",
        no_comments,
    )
    if latex_leaks:
        errors.append(
            f"[HTML公式漏转义] {filepath}: 发现裸露 LaTeX 宏 {sorted(set(latex_leaks))}，HTML 中必须使用 <sup>/<sub>/.frac 与 Unicode 符号！"
        )

    text_only = re.sub(r"<[^>]+>", " ", no_comments)
    carets = re.findall(r"[A-Za-z0-9\)\]]\^[A-Za-z0-9\(\-\+]", text_only)
    if carets:
        errors.append(
            f"[禁用纯文本幂次 ^] {filepath}: 发现纯文本幂次 {carets[:5]}，请改为 <sup>...</sup> 印刷体！"
        )

    raw_subs = re.findall(r"\b(?:[QERDVUCPfuzIRriAuεφσλ]_(?:\{[0-9a-zA-Z'\+\-]+\}|[0-9a-zA-Z'\+]{1,3}))\b", text_only)
    if raw_subs:
        errors.append(
            f"[禁用纯文本下标 _] {filepath}: 发现纯文本下标 {raw_subs[:5]}，请改为 <sub>...</sub> 印刷体！"
        )

    return errors


def validate_diagram_html(content: str, filepath: str) -> list[str]:
    """门禁 D: 校验独立矢量电路图 / 几何图 HTML。"""
    errors: list[str] = []
    errors.extend(check_hygiene_and_offline(content, filepath))
    errors.extend(check_svg_purity(content, filepath))
    errors.extend(check_raw_math_in_html(content, filepath))

    no_comments = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    forbidden_classes = re.findall(
        r"class\s*=\s*['\"][^'\"]*\b(info-col|text-col|desc-col|right-panel|formula-card)\b[^'\"]*['\"]",
        no_comments,
    )
    if forbidden_classes:
        errors.append(
            f"[图文正交律违规] {filepath}: 检测到侧边文字栏类名 {sorted(set(forbidden_classes))}！说明信息请置于画布下方 .legend-bar。"
        )
    if "<svg" not in no_comments.lower():
        errors.append(f"[缺失SVG画布] {filepath}: 矢量图 HTML 未包含 <svg> 元素！")
    return errors


def validate_board_html(content: str, filepath: str) -> list[str]:
    """门禁 B: 校验三合一全局复习看板 HTML。"""
    errors: list[str] = []
    errors.extend(check_hygiene_and_offline(content, filepath))
    errors.extend(check_svg_purity(content, filepath))
    errors.extend(check_raw_math_in_html(content, filepath))

    no_comments = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    no_comments = re.sub(r"/\*.*?\*/", "", no_comments, flags=re.DOTALL)
    no_scripts = re.sub(r"<script\b[^>]*>.*?</script>", "", no_comments, flags=re.DOTALL | re.IGNORECASE)

    bad_quotes = re.findall(r'\b(?:class|id|style|for|type|name|data-\w+)\s*=\s*(?:"[^"\n>]*\'|\'[^\'\n>]*")', no_scripts)
    if bad_quotes:
        errors.append(f"[HTML属性引号错配] {filepath}: 检测到未闭合属性引号 `{bad_quotes[:3]}`！")

    empty_grids = re.findall(r'<div[^>]*class="[^"]*flashcard-grid[^"]*"[^>]*>\s*</div>', no_scripts)
    if empty_grids:
        errors.append(
            f"[闪卡空壳违规] {filepath}: 检测到空的 `.flashcard-grid`！所有闪卡必须 100% 静态 HTML DOM 预渲染。"
        )

    static_fcards = re.findall(r'class="[^"]*\bfcard-front\b[^"]*"', no_scripts)
    fc_chks = re.findall(r'class="[^"]*\bfc-chk\b[^"]*"', no_scripts)
    if len(static_fcards) < 2:
        errors.append(
            f"[静态闪卡不足] {filepath}: 仅检测到 {len(static_fcards)} 张静态预渲染闪卡（至少需要 2 张 `.fcard-front`）！"
        )
    if len(fc_chks) < len(static_fcards):
        errors.append(
            f"[缺失纯CSS翻卡控件] {filepath}: `.fc-chk` 数量（{len(fc_chks)}）少于闪卡数量（{len(static_fcards)}）！"
        )
    if "tab-rad" not in no_scripts:
        errors.append(f"[缺失纯CSS Tab状态机] {filepath}: 未检测到 `.tab-rad` 纯 CSS 导航单选控件！")

    return errors


def validate_quiz_html(content: str, filepath: str) -> list[str]:
    """门禁 Q: 校验离线交互式随堂测验 HTML。"""
    errors: list[str] = []
    errors.extend(check_hygiene_and_offline(content, filepath))
    errors.extend(check_svg_purity(content, filepath))
    errors.extend(check_raw_math_in_html(content, filepath))

    no_comments = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    no_comments_css = re.sub(r"/\*.*?\*/", "", no_comments, flags=re.DOTALL)

    if re.search(r"\b(?:fetch\s*\(|XMLHttpRequest|navigator\.sendBeacon)\b", no_comments):
        errors.append(
            f"[违规网络请求] {filepath}: 离线测验严禁调用 fetch / XMLHttpRequest / sendBeacon，请仅使用 localStorage！"
        )
    if "localStorage" not in no_comments:
        errors.append(
            f"[缺失离线持久化] {filepath}: 未检测到 `localStorage`！测验必须将作答状态、得分与错题本持久化到浏览器本地存储。"
        )
    if "q-fig" in no_comments and "q-body-row" not in no_comments_css:
        errors.append(
            f"[紧凑布局违规] {filepath}: 含 `.q-fig` 配图但未定义 `.q-body-row` 左文右图布局！"
        )
    if not re.search(r"\.opts-list\s*\{[^}]*grid-template-columns\s*:\s*1fr\s+1fr", no_comments_css):
        errors.append(
            f"[选项网格违规] {filepath}: `.opts-list` 必须采用 `grid-template-columns: 1fr 1fr`（2×2 双列网格）！"
        )
    if "is-unknown" not in no_comments or "unknown-btn" not in no_comments:
        errors.append(
            f"[缺失此题不会按钮] {filepath}: 未检测到 `.is-unknown` / `.unknown-btn` 控件！"
        )
    if not re.search(r"pointer-events\s*:\s*none", no_comments_css):
        errors.append(
            f"[缺失作答锁定规则] {filepath}: 未检测到纯 CSS `pointer-events: none` 单题作答锁定规则！"
        )

    panels = re.findall(
        r'<div\s+class="q-panel"\s+id="panel-q(\d+)"[^>]*>(.*?)<div\s+class="foot-nav"',
        no_comments,
        flags=re.DOTALL,
    )
    if not panels:
        errors.append(f"[零空壳预渲染违规] {filepath}: 未检测到静态预渲染的 `.q-panel` 题目节点！")
        return errors

    for q_num, panel_html in panels:
        stem_match = re.search(r'<div\s+class="q-stem"[^>]*>(.*?)</div>', panel_html, flags=re.DOTALL)
        stem_text = strip_tags(stem_match.group(1)) if stem_match else ""
        if stem_text:
            if re.search(r"(接上题|接第\s*\d+\s*题|如上题|同上题|沿用上题)", stem_text):
                errors.append(f"[跨题引用违规] {filepath} 第{q_num}题: 题干出现跨题引用，每题必须独立自包含！")
            if re.search(r"(以及.*总间距\s*2\s*b|以及.*直径\s*2\s*[Rra])", stem_text):
                errors.append(f"[单问正交律违规] {filepath} 第{q_num}题: 严禁凑数式 2 倍量连环问！")
        if "hint-box" in panel_html:
            errors.append(f"[考卷纯粹性违规] {filepath} 第{q_num}题: 检测到 `hint-box`，题干区严禁夹带提示框！")

        fig_match = re.search(r'<div\s+class="q-fig"[^>]*>(.*?)</div>', panel_html, flags=re.DOTALL)
        if fig_match:
            if "<svg" not in fig_match.group(1).lower():
                errors.append(f"[配图缺失SVG] {filepath} 第{q_num}题: `.q-fig` 容器内必须包含 `<svg>`！")
        else:
            if stem_text and re.search(r"(图示.*电路|放大电路|偏置.*电路|共源|共射|共漏|共栅|恒流源|运放|二极管.*电路)", stem_text):
                errors.append(
                    f"[电路题缺图违规] {filepath} 第{q_num}题: 涉及具体电路拓扑分析（`{stem_text[:24]}...`），必须配 `.q-fig` 国标 SVG 电路图！"
                )

        opts = re.findall(r'<span\s+class="opt-text"[^>]*>(.*?)</span>', panel_html, flags=re.DOTALL)
        if len(opts) != 4:
            errors.append(f"[选项数量异常] {filepath} 第{q_num}题: 检测到 {len(opts)} 个选项（应为 4 个）！")
            continue

        clean_opts = [strip_tags(o) for o in opts]
        lengths = [len(t) for t in clean_opts]
        min_l, max_l = min(lengths), max(lengths)
        if max_l > min_l * 2.5 + 12:
            errors.append(
                f"[选项长度失衡] {filepath} 第{q_num}题: 最短 {min_l} 字 vs 最长 {max_l} 字，请保持四选项对称！"
            )
        cn_parens_count = sum(1 for t in clean_opts if "（" in t and "）" in t)
        if cn_parens_count == 1:
            errors.append(
                f"[单选项括号剧透] {filepath} 第{q_num}题: 仅 1 个选项含中文解释性括号，请删除括号防止剧透！"
            )

    return errors


def validate_markdown_note(content: str, filepath: str) -> list[str]:
    """门禁 M: 校验 Markdown 复习笔记归档格式与 LaTeX 安全闭合。"""
    errors: list[str] = []
    errors.extend(check_hygiene_and_offline(content, filepath))

    bad_prime = re.findall(r"\$[^$\n]+'\$(?=[（，。、；：）》])", content)
    if bad_prime:
        errors.append(
            f"[Markdown公式撇号漏编译] {filepath}: 发现 `{bad_prime[:3]}` 紧贴结尾 `$` 且后接中文标点，请改用 `\\prime$`！"
        )
    if re.search(r"\\(?:multicolumn|multirow)\b", content):
        errors.append(f"[Markdown表格宏泄漏] {filepath}: GFM 表格不支持 `\\multicolumn` / `\\multirow`！")

    for lineno, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.count("|") >= 2):
            continue
        clean_line = re.sub(r"`[^`\n]*`", "", stripped).replace(r"\$", "").replace(r"\|", "")
        cells = clean_line.strip("|").split("|")
        odd_cells = [c.strip() for c in cells if len(re.findall(r"(?<!\\)\$", c)) % 2 == 1]
        if odd_cells:
            errors.append(
                f"[表格竖线劈裂公式] {filepath} 第{lineno}行: 表格公式内请用 `\\vert` 替代裸竖线 `|`！"
            )
    return errors


def collect_targets(root: Path) -> list[Path]:
    """扫描目录中需要门禁校验的 HTML 与 Markdown 产物，自动跳过工具隐藏目录。"""
    if root.is_file():
        return [root]
    targets: list[Path] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel_parts = set(p.relative_to(root).parts[:-1])
        if rel_parts & SKIP_DIRS:
            continue
        if p.suffix.lower() == ".md":
            if p.name.lower() in SKIP_MD_NAMES:
                continue
            targets.append(p)
        elif p.suffix.lower() == ".html":
            targets.append(p)
    return targets


def check_file(target: Path) -> list[str]:
    """根据文件名自动路由到对应的门禁检查器。"""
    if not target.exists():
        return [f"[文件不存在] {target}"]

    name = target.name.lower()
    content = target.read_text(encoding="utf-8", errors="replace")

    if target.suffix.lower() == ".md":
        if name in SKIP_MD_NAMES:
            return []
        return validate_markdown_note(content, str(target))

    if target.suffix.lower() == ".html":
        if "board" in name or "看板" in name:
            return validate_board_html(content, str(target))
        if "quiz" in name or "测验" in name:
            return validate_quiz_html(content, str(target))
        if any(k in name for k in ("fig", "diagram", "svg", "circuit", "mod", "step")):
            return validate_diagram_html(content, str(target))
        return check_hygiene_and_offline(content, str(target)) + check_raw_math_in_html(content, str(target))

    return []


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    if len(sys.argv) < 2:
        print("用法: python notes_quality_gate.py <file_or_dir> [...]")
        return 1

    total_errors: list[str] = []
    checked_files: list[Path] = []
    for arg in sys.argv[1:]:
        p = Path(arg)
        if not p.exists():
            total_errors.append(f"[路径不存在] {p}")
            continue
        targets = collect_targets(p)
        if p.is_dir() and not targets:
            total_errors.append(f"[目录无待检产物] {p}: 未发现任何 .html 或 .md 学习产物！")
            continue
        for t in targets:
            checked_files.append(t)
            total_errors.extend(check_file(t))

    if total_errors:
        print(f"❌ [NOTES QUALITY GATE FAILED] 共检查 {len(checked_files)} 个文件，发现 {len(total_errors)} 处违规:")
        for err in total_errors:
            print(f"  - {err}")
        return 1

    print(f"✅ [NOTES QUALITY GATE PASSED] 全部 {len(checked_files)} 个目标文件均通过确定性质量门禁！")
    for f in checked_files:
        print(f"  ✓ {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
