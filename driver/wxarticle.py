"""
异步微信公众号文章获取器
基于 Playwright 实现文章内容抓取
"""
import random
import time
import base64
import re
import asyncio
from datetime import datetime
from typing import Dict
from bs4 import BeautifulSoup

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from driver.playwright_driver import PlaywrightController


class WXArticleFetcher:
    def __init__(self, wait_timeout: int = 30000):
        self.wait_timeout = wait_timeout
        self.browser_proxy_url = ""

    async def get_article_content(self, url: str) -> Dict:
        info = {
            "id": self.extract_id_from_url(url),
            "title": "",
            "author": "",
            "description": "",
            "topic_image": "",
            "publish_time": 0,
            "content": "",
            "content_text": "",
            "mp_info": {
                "mp_name": "",
                "logo": "",
                "biz": ""
            },
            "mp_id": "",
            "article_type": 0,
            "fetch_error": ""
        }

        try:
            async with PlaywrightController(
                proxy_url=self.browser_proxy_url,
                mobile_mode=True
            ) as controller:
                success = await controller.open_url(url, timeout=self.wait_timeout)
                if not success:
                    info["fetch_error"] = "页面加载失败"
                    return info

                page = controller.page

                await asyncio.sleep(2)

                body = await page.content()
                body_text = await page.locator("body").text_content()

                if "当前环境异常" in body_text:
                    info["fetch_error"] = "当前环境异常，完成验证后即可继续访问"
                    return info

                if "该内容已被发布者删除" in body_text or "The content has been deleted" in body_text:
                    info["fetch_error"] = "该内容已被发布者删除"
                    return info

                if "内容审核中" in body_text:
                    info["fetch_error"] = "内容审核中"
                    return info

                if "该内容暂时无法查看" in body_text:
                    info["fetch_error"] = "该内容暂时无法查看"
                    return info

                if "违规无法查看" in body_text:
                    info["fetch_error"] = "违规无法查看"
                    return info

                title = await page.locator('meta[property="og:title"]').get_attribute("content", timeout=5000)
                author = await page.locator('meta[property="og:article:author"]').get_attribute("content", timeout=5000)
                description = await page.locator('meta[property="og:description"]').get_attribute("content", timeout=5000)
                topic_image = await page.locator('meta[property="twitter:image"]').get_attribute("content", timeout=5000)

                if not title:
                    title = await page.evaluate('() => document.title')

                publish_time = await self._extract_publish_time(page)
                article_type = await self._detect_article_type(page)
                info["article_type"] = article_type

                content = await page.locator('#js_content').inner_html()
                if not content:
                    content = await page.locator('#js_article').inner_html()

                try:
                    await self._scroll_to_bottom_and_load_images(page)
                except Exception:
                    pass

                content = await page.locator('#js_content').inner_html()
                if not content:
                    content = await page.locator('#js_article').inner_html()

                content = Web.clean_article_content(str(content))

                info["title"] = title or ""
                info["author"] = author or ""
                info["description"] = description or ""
                info["topic_image"] = topic_image or ""
                info["publish_time"] = publish_time
                info["content"] = content or ""

                soup = BeautifulSoup(content, 'html.parser')
                raw_text = soup.get_text() if soup.get_text() else ""
                lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
                content_text = '\n'.join(lines)
                info["content_text"] = content_text[:5000]

                try:
                    logo_src = None
                    selectors = [
                        '#js_like_profile_bar .wx_follow_avatar img',
                        '#js_like_profile_bar img.wx_follow_avatar_pic',
                        '.wx_follow_avatar img'
                    ]
                    for selector in selectors:
                        try:
                            ele_logo = page.locator(selector)
                            logo_src = await ele_logo.get_attribute('src', timeout=3000)
                            if logo_src:
                                break
                        except Exception:
                            continue

                    if not logo_src:
                        try:
                            logo_src = await page.locator('meta[property="og:image"]').get_attribute("content", timeout=3000)
                        except Exception:
                            pass

                    mp_name = None
                    try:
                        mp_name = await page.evaluate('() => { const el = document.getElementById("js_wx_follow_nickname"); return el ? el.textContent : null; }')
                    except Exception:
                        pass

                    if not mp_name:
                        try:
                            mp_name = await page.locator('meta[property="og:article:author"]').get_attribute("content", timeout=3000)
                        except Exception:
                            pass

                    biz = None
                    try:
                        biz = await page.evaluate('() => window.biz')
                    except Exception:
                        pass

                    if not biz:
                        biz = self._extract_biz(url, content or "")

                    info["mp_info"] = {
                        "mp_name": mp_name or "未知公众号",
                        "logo": logo_src or "",
                        "biz": biz or ""
                    }

                    if biz:
                        try:
                            info["mp_id"] = "MP_WXS_" + base64.b64decode(biz).decode("utf-8")
                        except Exception:
                            info["mp_id"] = ""

                except Exception:
                    info["mp_info"] = {
                        "mp_name": "未知公众号",
                        "logo": "",
                        "biz": ""
                    }

                return info

        except Exception as e:
            info["fetch_error"] = str(e)
            return info

    async def _scroll_to_bottom_and_load_images(self, page, scroll_step: int = 500, max_scrolls: int = 30, wait_time: int = 300):
        try:
            total_height = await page.evaluate('() => document.body.scrollHeight')
            current_position = 0
            scroll_count = 0

            while current_position < total_height and scroll_count < max_scrolls:
                current_position += scroll_step
                await page.evaluate(f'() => window.scrollTo(0, {current_position})')
                await asyncio.sleep(wait_time / 1000)
                total_height = await page.evaluate('() => document.body.scrollHeight')
                scroll_count += 1

            await page.evaluate('() => window.scrollTo(0, 0)')
            await asyncio.sleep(0.5)
            await page.evaluate('() => window.scrollTo(0, document.body.scrollHeight)')
            await asyncio.sleep(1)

        except Exception:
            pass

    async def _extract_publish_time(self, page) -> int:
        try:
            try:
                publish_time_str = await page.locator('#publish_time').text_content()
                if publish_time_str:
                    return self._convert_publish_time_to_timestamp(publish_time_str)
            except Exception:
                pass

            content = await page.content()
            patterns = [
                r'publish_time\s*=\s*["\']([^"\']+)["\']',
                r'var\s+publish_time\s*=\s*["\']([^"\']+)["\']',
                r'create_time\s*=\s*["\']([^"\']+)["\']',
            ]

            for pattern in patterns:
                match = re.search(pattern, content)
                if match:
                    return self._convert_publish_time_to_timestamp(match.group(1))

            return int(datetime.now().timestamp())

        except Exception:
            return int(datetime.now().timestamp())

    async def _detect_article_type(self, page) -> int:
        try:
            content = await page.content()

            has_video = await page.evaluate('() => !!document.querySelector(".video_iframe, #js_video_page_title, [data-vid], mp-common-videosnap")')
            if has_video:
                return 5

            has_audio = await page.evaluate('() => !!document.querySelector("#js_audio_title, .audio_area, mpvoice")')
            if has_audio:
                return 7

            has_images = await page.evaluate('() => !!document.querySelector("#js_text_title")')
            if has_images:
                return 10

            item_show_type = await page.evaluate('() => window.item_show_type')
            if item_show_type is not None:
                article_type = int(item_show_type)
                if article_type in [0, 5, 7, 10]:
                    return article_type

            patterns = [
                r"item_show_type\s*=\s*['\"](\d+)['\"]",
                r"item_show_type\s*=\s*window\.a_value_which_never_exists\s*\|\|\s*['\"](\d+)['\"]",
            ]

            for pattern in patterns:
                match = re.search(pattern, content)
                if match:
                    article_type = int(match.group(1))
                    if article_type in [0, 5, 7, 10]:
                        return article_type

            return 0

        except Exception:
            return 0

    def _convert_publish_time_to_timestamp(self, publish_time_str: str) -> int:
        try:
            normalized_str = re.sub(
                r'(\d{4})年(\d{1,2})月(\d{1,2})日',
                lambda m: f"{m.group(1)}年{m.group(2).zfill(2)}月{m.group(3).zfill(2)}日",
                publish_time_str
            )

            formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y年%m月%d日 %H:%M",
                "%Y-%m-%d %H:%M",
                "%Y-%m-%d",
                "%Y年%m月%d日",
                "%m月%d日",
            ]

            for fmt in formats:
                try:
                    if fmt == "%m月%d日":
                        current_date = datetime.now()
                        current_year = current_date.year
                        full_time_str = f"{current_year}年{normalized_str}"
                        dt = datetime.strptime(full_time_str, "%Y年%m月%d日")
                        if dt > current_date:
                            dt = dt.replace(year=current_year - 1)
                    else:
                        dt = datetime.strptime(normalized_str, fmt)
                    return int(dt.timestamp())
                except ValueError:
                    continue

            return int(datetime.now().timestamp())

        except Exception:
            return int(datetime.now().timestamp())

    def _extract_biz(self, url: str, content: str) -> str:
        match = re.search(r'[?&]__biz=([^&]+)', url)
        if match:
            return match.group(1)

        match = re.search(r'var\s+biz\s*=\s*["\']([^"\']+)["\']', content)
        if match:
            return match.group(1)

        return ""

    def extract_id_from_url(self, url: str) -> str:
        try:
            match = re.search(r'/s/([A-Za-z0-9_-]+)', url)
            if not match:
                return ""

            id_str = match.group(1)
            padding = 4 - len(id_str) % 4
            if padding != 4:
                id_str += '=' * padding

            try:
                id_number = base64.b64decode(id_str).decode("utf-8")
                return id_number
            except Exception:
                return match.group(1)

        except Exception:
            return ""


class Web:
    @staticmethod
    def fix_images(content: str) -> str:
        try:
            soup = BeautifulSoup(content, 'html.parser')

            img_tags = soup.find_all('img')
            for img_tag in img_tags:
                src_value = img_tag.get('src') or img_tag.get('data-src', '')
                if "data:image" in src_value and src_value != img_tag.get('data-src', ''):
                    src_value = img_tag.get('data-src', '')
                style_value = img_tag.get('style', '')
                img_tag.attrs = {}
                if src_value:
                    img_tag['src'] = src_value
                if style_value:
                    img_tag['style'] = style_value

            for tag_name in ['section', 'p', 'span']:
                tags = soup.find_all(tag_name)
                for tag in tags:
                    style_value = tag.get('style', '')
                    tag.attrs = {}
                    if style_value:
                        tag['style'] = style_value

            elements_with_data_src = soup.find_all(attrs={'data-src': True})
            for element in elements_with_data_src:
                if element.name != 'img':
                    data_src = element.get('data-src', '')
                    if data_src:
                        style = element.get('style', '')
                        if style and 'background' in style.lower():
                            if 'url(' not in style.lower():
                                if style.endswith(';'):
                                    element['style'] = f"{style}background-image: url(\"{data_src}\")"
                                else:
                                    element['style'] = f"{style};background-image: url(\"{data_src}\")"

            return soup.prettify()
        except Exception:
            return content

    @staticmethod
    def clean_article_content(html_content: str, mp_id: str = "") -> str:
        html_content = Web.fix_images(html_content)
        return html_content

    @staticmethod
    def get_description(content: str, length: int = 200) -> str:
        if not content:
            return ""
        try:
            soup = BeautifulSoup(content, 'html.parser')
            text = soup.get_text().strip().strip("\n").replace("\n", " ").replace("\r", " ")
            return text[:length] + "..." if len(text) > length else text
        except Exception:
            return ""


async def fetch_article_content(url: str) -> Dict:
    fetcher = WXArticleFetcher()
    return await fetcher.get_article_content(url)


def fetch_article_content_sync(url: str) -> Dict:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(fetch_article_content(url))
        return result
    finally:
        loop.close()