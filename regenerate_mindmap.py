"""独立脚本 - 从编辑后的思维导图源文件重新生成 PNG 图片

用法:
    python regenerate_mindmap.py <mindmap.md 源文件路径>

示例:
    python regenerate_mindmap.py output/视频标题_assets/mindmap.md

说明:
    用户可以编辑 mindmap.md 源文件调整思维导图结构，
    然后运行此脚本重新生成 mindmap.png。
    由于笔记 MD 中引用的是相对路径，PNG 原地覆盖后笔记自动更新。
"""

import sys
import os

# 将项目根目录加入路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.mindmap_generator import MindMapGenerator


def main():
    if len(sys.argv) < 2:
        print("用法: python regenerate_mindmap.py <mindmap.md 源文件路径>")
        print("示例: python regenerate_mindmap.py output/视频标题_assets/mindmap.md")
        sys.exit(1)

    source_path = sys.argv[1]

    if not os.path.isfile(source_path):
        print(f"错误: 文件不存在 - {source_path}", file=sys.stderr)
        sys.exit(1)

    if not source_path.endswith('.md'):
        print("警告: 文件不是 .md 格式，继续尝试...", file=sys.stderr)

    result = MindMapGenerator.regenerate(source_path)
    if result:
        print(f"思维导图已重新生成: {result}")
    else:
        print("思维导图重新生成失败", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
