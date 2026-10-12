"""公开仓库里不许出现本机实际值。

内网地址、主机别名、内部路径、真实域名、凭据只写在私有运维记录里，本仓库一律用占位符。
**标记表放在仓库根的 `.private-markers.txt`，它被 gitignore 掉、永不入库**（否则这个文件自己
就是一次泄露）。因为路径是中性的，这个文件里也就不含任何敏感值，可以放心提交。

命中时只报「文件:行号」和第几条标记，**不回显命中内容**——回显等于再泄露一次。
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MARKER_FILE = Path(
    os.environ.get("PRIVATE_MARKERS_FILE", REPO_ROOT / ".private-markers.txt")
)


def _markers():
    """读取标记表；没有就返回空（这个检查是本机护栏，别的机器上不存在很正常）。"""
    if not MARKER_FILE.is_file():
        return []
    patterns = []
    for number, raw in enumerate(MARKER_FILE.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            patterns.append(re.compile(line))
        except re.error as error:
            raise AssertionError(
                f"{MARKER_FILE} 第 {number} 行不是合法正则（{error}）；"
                "注释行要以 # 开头"
            ) from None
    return patterns


def _tracked_files():
    """git 已跟踪 + 已 add 的文件。untracked 的文件推不上去，不入本次检查。"""
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return [path for path in result.stdout.split("\0") if path]


def test_no_private_marker_in_tracked_files():
    patterns = _markers()
    if not patterns:
        pytest.skip(f"没有私有标记表（{MARKER_FILE}），跳过")

    tracked = _tracked_files()
    if tracked is None:
        pytest.skip("不在 git 仓库里，不知道要检查哪些文件，跳过")

    hits = []
    for name in tracked:
        try:
            text = (REPO_ROOT / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            for index, pattern in enumerate(patterns, start=1):
                if pattern.search(line):
                    hits.append(f"  {name}:{number}（命中标记 #{index}）")
                    break

    assert not hits, (
        "这些行命中了本机私有标记，公开仓库里要换成占位符"
        f"（标记表：{MARKER_FILE}）：\n" + "\n".join(hits)
    )
