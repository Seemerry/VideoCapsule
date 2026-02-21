"""思维导图生成模块 - 使用 Markmap.js + Playwright 将 Markdown 渲染为 PNG"""

import os
import re
import sys
import tempfile
from typing import Optional


class MindMapGenerator:
    """思维导图生成器 - 使用 Markmap.js + Playwright 渲染"""

    # HTML 模板，使用 __MINDMAP_CONTENT__ 作为占位符
    HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    body { margin: 0; background: white; }
    #markmap { display: block; width: 100vw; height: 100vh; }
  </style>
</head>
<body>
  <svg id="markmap"></svg>
  <script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
  <script src="https://cdn.jsdelivr.net/npm/markmap-view"></script>
  <script src="https://cdn.jsdelivr.net/npm/markmap-lib"></script>
  <script>
    const md = __MINDMAP_CONTENT__;
    const { Transformer } = markmap;
    const { Markmap } = markmap;
    const transformer = new Transformer();
    const { root } = transformer.transform(md);
    const svg = document.querySelector('#markmap');
    const mm = Markmap.create(svg, {
      autoFit: true,
      color: (node) => {
        const colors = ['#2196F3', '#4CAF50', '#FF9800', '#9C27B0', '#F44336', '#00BCD4'];
        return colors[node.state.depth % colors.length];
      }
    }, root);
    setTimeout(() => document.body.setAttribute('data-ready', 'true'), 2000);
  </script>
</body>
</html>"""

    def generate(self, mindmap_md: str, output_dir: str, title: str) -> Optional[dict]:
        """生成思维导图图片和源文件

        Args:
            mindmap_md: 思维导图 Markdown 内容
            output_dir: 输出目录
            title: 视频标题（用于生成 assets 子文件夹名）

        Returns:
            dict: {'image_path', 'image_relative_path', 'source_path', 'source_relative_path'}
            失败返回 None
        """
        try:
            # 创建 assets 子文件夹
            safe_title = self._sanitize_dirname(title)
            assets_dir = os.path.join(output_dir, f"{safe_title}_assets")
            os.makedirs(assets_dir, exist_ok=True)

            # 1. 保存源文件
            source_path = os.path.join(assets_dir, 'mindmap.md')
            with open(source_path, 'w', encoding='utf-8') as f:
                f.write(mindmap_md)

            # 2. 渲染 PNG
            image_path = os.path.join(assets_dir, 'mindmap.png')
            success = self._render_to_png(mindmap_md, image_path)
            if not success:
                return None

            # 3. 构建相对路径
            source_relative = f"{safe_title}_assets/mindmap.md"
            image_relative = f"{safe_title}_assets/mindmap.png"

            print(f"思维导图已生成: {image_path}", file=sys.stderr)
            return {
                'image_path': os.path.abspath(image_path),
                'image_relative_path': image_relative,
                'source_path': os.path.abspath(source_path),
                'source_relative_path': source_relative,
            }

        except Exception as e:
            print(f"思维导图生成失败: {e}", file=sys.stderr)
            return None

    @staticmethod
    def regenerate(source_path: str) -> Optional[str]:
        """从已有的源文件重新生成 PNG

        Args:
            source_path: mindmap.md 源文件路径

        Returns:
            str: 生成的 PNG 路径，失败返回 None
        """
        if not os.path.isfile(source_path):
            print(f"源文件不存在: {source_path}", file=sys.stderr)
            return None

        try:
            with open(source_path, 'r', encoding='utf-8') as f:
                mindmap_md = f.read()

            # PNG 输出到同目录
            output_dir = os.path.dirname(source_path)
            image_path = os.path.join(output_dir, 'mindmap.png')

            generator = MindMapGenerator()
            success = generator._render_to_png(mindmap_md, image_path)
            if success:
                print(f"思维导图已重新生成: {image_path}", file=sys.stderr)
                return os.path.abspath(image_path)
            return None

        except Exception as e:
            print(f"思维导图重新生成失败: {e}", file=sys.stderr)
            return None

    def _render_to_png(self, mindmap_md: str, output_path: str) -> bool:
        """使用 Playwright 将 Markdown 渲染为 PNG

        Args:
            mindmap_md: 思维导图 Markdown 内容
            output_path: PNG 输出路径

        Returns:
            bool: 是否成功
        """
        tmp_html = None
        try:
            from playwright.sync_api import sync_playwright

            # 生成临时 HTML
            md_json = self._escape_for_js(mindmap_md)
            html_content = self.HTML_TEMPLATE.replace('__MINDMAP_CONTENT__', md_json)

            tmp_fd, tmp_html = tempfile.mkstemp(suffix='.html')
            with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
                f.write(html_content)

            # Playwright 截图
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={'width': 1600, 'height': 900})
                page.goto(f'file:///{tmp_html.replace(os.sep, "/")}')

                # 等待渲染完成
                page.wait_for_selector('[data-ready="true"]', timeout=15000)

                # 对 SVG 元素截图
                svg = page.query_selector('#markmap')
                if svg:
                    svg.screenshot(path=output_path)
                else:
                    page.screenshot(path=output_path)

                browser.close()

            return os.path.exists(output_path)

        except Exception as e:
            print(f"Playwright 渲染失败: {e}", file=sys.stderr)
            return False

        finally:
            if tmp_html and os.path.exists(tmp_html):
                try:
                    os.unlink(tmp_html)
                except OSError:
                    pass

    @staticmethod
    def _escape_for_js(text: str) -> str:
        """将 Markdown 文本转义为 JavaScript 字符串字面量"""
        import json
        return json.dumps(text, ensure_ascii=False)

    @staticmethod
    def _sanitize_dirname(title: str) -> str:
        """清理文件夹名称，移除非法字符"""
        illegal_chars = r'[<>:"/\\|?*]'
        sanitized = re.sub(illegal_chars, '_', title)
        sanitized = sanitized.strip(' .')
        return sanitized[:100] if len(sanitized) > 100 else sanitized
