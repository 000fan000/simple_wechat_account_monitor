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
    def __init__(self, wait_timeout: int = 60000):
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
            "mp_info": {"mp_name": "", "logo": "", "biz": ""},
            "mp_id": "",
            "article_type": 0,
            "fetch_error": ""
        }

        try:
            async with PlaywrightController(proxy_url=self.browser_proxy_url, mobile_mode=True) as controller:
                success = await controller.open_url(url, timeout=self.wait_timeout)
                if not success:
                    info["fetch_error"] = "页面加载失败"
                    return info

                page = controller.page
                await asyncio.sleep(3)

                body = await page.content()
                body_text = await page.locator("body").text_content(timeout=10000)
                for err in ["当前环境异常", "该内容已被发布者删除", "The content has been deleted", "内容审核中", "该内容暂时无法查看", "违规无法查看"]:
                    if err in body_text:
                        info["fetch_error"] = err
                        return info

                title = None
                try:
                    title = await page.locator('meta[property="og:title"]').get_attribute("content", timeout=3000)
                except:
                    pass
                if not title:
                    try:
                        title = await page.evaluate('() => document.title')
                    except:
                        pass

                author = None
                try:
                    author = await page.locator('meta[property="og:article:author"]').get_attribute("content", timeout=3000)
                except:
                    pass

                description = None
                try:
                    description = await page.locator('meta[property="og:description"]').get_attribute("content", timeout=3000)
                except:
                    pass

                topic_image = None
                try:
                    topic_image = await page.locator('meta[property="twitter:image"]').get_attribute("content", timeout=3000)
                except:
                    pass

                publish_time = await self._extract_publish_time(page)
                article_type = await self._detect_article_type(page)
                info["article_type"] = article_type

                content = ""
                try:
                    await page.wait_for_selector('#js_content', timeout=15000)
                    content = await page.locator('#js_content').inner_html(timeout=10000)
                except:
                    pass
                if not content:
                    try:
                        content = await page.locator('#js_article').inner_html(timeout=5000)
                    except:
                        pass

                if content:
                    try:
                        await self._scroll_to_bottom_and_load_images(page)
                    except:
                        pass
                    try:
                        c2 = await page.locator('#js_content').inner_html(timeout=5000)
                        if c2:
                            content = c2
                    except:
                        pass

                content = Web.clean_article_content(str(content))
                info["title"] = title or ""
                info["author"] = author or ""
                info["description"] = description or ""
                info["topic_image"] = topic_image or ""
                info["publish_time"] = publish_time
                info["content"] = content or ""

                if content:
                    soup = BeautifulSoup(content, 'html.parser')
                    raw_text = soup.get_text() if soup.get_text() else ""
                    lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
                    ct = '\n'.join(lines)
                    info["content_text"] = ct[:32767] if len(ct) > 32767 else ct
                else:
                    info["content_text"] = (description or "")[:500]

                try:
                    logo_src = None
                    for sel in ['#js_like_profile_bar .wx_follow_avatar img', '#js_like_profile_bar img.wx_follow_avatar_pic', '.wx_follow_avatar img']:
                        try:
                            logo_src = await page.locator(sel).get_attribute('src', timeout=3000)
                            if logo_src:
                                break
                        except:
                            continue
                    if not logo_src:
                        try:
                            logo_src = await page.locator('meta[property="og:image"]').get_attribute("content", timeout=3000)
                        except:
                            pass

                    mp_name = None
                    try:
                        mp_name = await page.evaluate('() => { const el = document.getElementById("js_wx_follow_nickname"); return el ? el.textContent : null; }')
                    except:
                        pass

                    biz = None
                    try:
                        biz = await page.evaluate('() => window.biz')
                    except:
                        pass
                    if not biz:
                        biz = self._extract_biz(url, content or "")

                    info["mp_info"] = {"mp_name": mp_name or "未知公众号", "logo": logo_src or "", "biz": biz or ""}
                    if biz:
                        try:
                            info["mp_id"] = "MP_WXS_" + base64.b64decode(biz).decode("utf-8")
                        except:
                            info["mp_id"] = ""
                except:
                    info["mp_info"] = {"mp_name": "未知公众号", "logo": "", "biz": ""}

                return info

        except Exception as e:
            info["fetch_error"] = str(e)
            return info

    async def _scroll_to_bottom_and_load_images(self, page, scroll_step=500, max_scrolls=30, wait_time=300):
        try:
            total_height = await page.evaluate('() => document.body.scrollHeight')
            pos = 0
            n = 0
            while pos < total_height and n < max_scrolls:
                pos += scroll_step
                await page.evaluate('() => window.scrollTo(0, ' + str(pos) + ')')
                await asyncio.sleep(wait_time / 1000)
                total_height = await page.evaluate('() => document.body.scrollHeight')
                n += 1
            await page.evaluate('() => window.scrollTo(0, document.body.scrollHeight)')
            await asyncio.sleep(1)
        except:
            pass

    async def _extract_publish_time(self, page) -> int:
        try:
            try:
                t = await page.locator('#publish_time').text_content(timeout=3000)
                if t:
                    return self._convert_publish_time_to_timestamp(t)
            except:
                pass
            body = await page.content()
            for p in [r'publish_time\s*=\s*["\']([^"\']+)["\']', r'create_time\s*=\s*["\']([^"\']+)["\']']:
                m = re.search(p, body)
                if m:
                    return self._convert_publish_time_to_timestamp(m.group(1))
            return int(datetime.now().timestamp())
        except:
            return int(datetime.now().timestamp())

    async def _detect_article_type(self, page) -> int:
        try:
            has_video = await page.evaluate('() => !!document.querySelector(".video_iframe, #js_video_page_title, [data-vid], mp-common-videosnap")')
            if has_video:
                return 5
            has_audio = await page.evaluate('() => !!document.querySelector("#js_audio_title, .audio_area, mpvoice")')
            if has_audio:
                return 7
            return 0
        except:
            return 0

    def _convert_publish_time_to_timestamp(self, s: str) -> int:
        try:
            s = re.sub(r'(\d{4})年(\d{1,2})月(\d{1,2})日', lambda m: m.group(1) + '年' + m.group(2).zfill(2) + '月' + m.group(3).zfill(2) + '日', s)
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y年%m月%d日 %H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y年%m月%d日", "%m月%d日"]:
                try:
                    if fmt == "%m月%d日":
                        dt = datetime.strptime(str(datetime.now().year) + '年' + s, "%Y年%m月%d日")
                        if dt > datetime.now():
                            dt = dt.replace(year=datetime.now().year - 1)
                    else:
                        dt = datetime.strptime(s, fmt)
                    return int(dt.timestamp())
                except:
                    continue
            return int(datetime.now().timestamp())
        except:
            return int(datetime.now().timestamp())

    def _extract_biz(self, url: str, content: str) -> str:
        m = re.search(r'[?&]__biz=([^&]+)', url)
        if m:
            return m.group(1)
        m = re.search(r'var\s+biz\s*=\s*["\x27]([^"\x27]+)["\x27]', content)
        if m:
            return m.group(1)
        return ""

    def extract_id_from_url(self, url: str) -> str:
        try:
            m = re.search(r'/s/([A-Za-z0-9_-]+)', url)
            if not m:
                return ""
            s = m.group(1)
            p = 4 - len(s) % 4
            if p != 4:
                s += '=' * p
            try:
                return base64.b64decode(s).decode("utf-8")
            except:
                return m.group(1)
        except:
            return ""


class Web:
    @staticmethod
    def fix_images(content: str) -> str:
        try:
            soup = BeautifulSoup(content, 'html.parser')
            for img in soup.find_all('img'):
                src = img.get('src') or img.get('data-src', '')
                if "data:image" in src and src != img.get('data-src', ''):
                    src = img.get('data-src', '')
                style = img.get('style', '')
                img.attrs = {}
                if src:
                    img['src'] = src
                if style:
                    img['style'] = style
            for tag_name in ['section', 'p', 'span']:
                for tag in soup.find_all(tag_name):
                    style = tag.get('style', '')
                    tag.attrs = {}
                    if style:
                        tag['style'] = style
            for el in soup.find_all(attrs={'data-src': True}):
                if el.name != 'img':
                    ds = el.get('data-src', '')
                    if ds:
                        st = el.get('style', '')
                        if st and 'background' in st.lower() and 'url(' not in st.lower():
                            el['style'] = st + (';' if not st.endswith(';') else '') + 'background-image: url("' + ds + '")'
            return soup.prettify()
        except:
            return content

    @staticmethod
    def clean_article_content(html_content: str, mp_id: str = "") -> str:
        return Web.fix_images(html_content)


async def fetch_article_content(url: str) -> Dict:
    fetcher = WXArticleFetcher(wait_timeout=60000)
    return await fetcher.get_article_content(url)


def fetch_article_content_sync(url: str) -> Dict:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(fetch_article_content(url))
    finally:
        loop.close()
