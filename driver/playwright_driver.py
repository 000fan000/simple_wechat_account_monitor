"""
Async Playwright Controller - 异步浏览器控制器
"""
import os
import sys
import asyncio
import time
from typing import Dict, List, Optional

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


class AntiCrawlerConfig:
    """反爬虫配置"""

    def __init__(self):
        self._ua_generator = UserAgentGenerator()

    def get_anti_crawler_config(self, mobile_mode: bool = False) -> Dict:
        import random
        fingerprint = self._generate_uuid()

        config = {
            "user_agent": self._ua_generator.get_realistic_user_agent(mobile_mode),
            "viewport": {
                "width": random.randint(1200, 1920) if not mobile_mode else 375,
                "height": random.randint(800, 1080) if not mobile_mode else 812,
                "device_scale_factor": random.choice([1, 1.25, 1.5, 2])
            },
            "java_script_enabled": True,
            "ignore_https_errors": True,
            "bypass_csp": True,
            "extra_http_headers": self._get_http_headers(mobile_mode),
            "permissions": [],
        }

        if mobile_mode:
            config["extra_http_headers"].update({
                "User-Agent": config["user_agent"],
                "X-Requested-With": "com.tencent.mm"
            })

        return config

    def _get_http_headers(self, mobile_mode: bool = False) -> Dict[str, str]:
        import random
        headers = {
            "Accept": random.choice([
                "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
            ]),
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": random.choice(["no-cache", "max-age=0"]),
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }
        if mobile_mode:
            headers["X-Requested-With"] = "com.tencent.mm"
        return headers

    def _generate_uuid(self) -> str:
        import uuid
        return str(uuid.uuid4()).replace("-", "")

    @staticmethod
    def get_init_script() -> str:
        return """
        delete Object.getPrototypeOf(navigator).webdriver;
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
            configurable: false,
            enumerable: true
        });

        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                const plugins = [
                    Object.create(Plugin.prototype, {
                        name: { value: 'PDF Viewer', enumerable: true },
                        description: { value: '', enumerable: true },
                        filename: { value: 'internal-pdf-viewer', enumerable: true },
                        length: { value: 1, enumerable: true },
                        item: { value: (i) => i === 0 ? { type: 'application/pdf', suffixes: 'pdf', description: '' } : null },
                        namedItem: { value: (name) => null }
                    }),
                    Object.create(Plugin.prototype, {
                        name: { value: 'Chrome PDF Plugin', enumerable: true },
                        description: { value: 'Portable Document Format', enumerable: true },
                        filename: { value: 'internal-pdf-viewer', enumerable: true },
                        length: { value: 1, enumerable: true },
                        item: { value: (i) => i === 0 ? { type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format' } : null },
                        namedItem: { value: (name) => null }
                    })
                ];
                plugins.length = 2;
                plugins.item = (i) => plugins[i] || null;
                plugins.namedItem = (name) => plugins.find(p => p.name === name) || null;
                plugins.refresh = () => {};
                return plugins;
            },
            configurable: false,
            enumerable: true
        });

        Object.defineProperty(navigator, 'mimeTypes', {
            get: () => {
                const mimeTypes = [
                    { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format', enabledPlugin: { name: 'PDF Viewer' } }
                ];
                mimeTypes.length = 1;
                mimeTypes.item = (i) => mimeTypes[i] || null;
                mimeTypes.namedItem = (name) => mimeTypes.find(m => m.type === name) || null;
                return mimeTypes;
            },
            configurable: false,
            enumerable: true
        });

        Object.defineProperty(navigator, 'languages', {
            get: () => ['zh-CN', 'zh', 'en-US', 'en'],
            configurable: false,
            enumerable: true
        });

        Object.defineProperty(navigator, 'platform', {
            get: () => 'Win32',
            configurable: false,
            enumerable: true
        });

        Object.defineProperty(navigator, 'hardwareConcurrency', {
            get: () => 8,
            configurable: false,
            enumerable: true
        });

        Object.defineProperty(navigator, 'deviceMemory', {
            get: () => 8,
            configurable: false,
            enumerable: true
        });

        if (!window.chrome) {
            window.chrome = {
                app: { isInstalled: false, InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' }, RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' } },
                runtime: { OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' }, OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' }, PlatformArch: { ARM: 'arm', ARM64: 'arm64', X86_32: 'x86-32', X86_64: 'x86-64' }, PlatformOs: { ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' }, RequestUpdateCheckStatus: { NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available' }, connect: () => ({ onDisconnect: { addListener: () => {} }, onMessage: { addListener: () => {} }, postMessage: () => {} }), sendMessage: () => {} },
                csi: () => ({ onloadT: Date.now(), pageT: Date.now(), startE: Date.now(), tran: 15 }),
                loadTimes: () => ({ requestTime: Date.now() / 1000, startLoadTime: Date.now() / 1000, commitLoadTime: Date.now() / 1000, finishDocumentLoadTime: Date.now() / 1000, finishLoadTime: Date.now() / 1000, firstPaintTime: Date.now() / 1000, firstPaintAfterLoadTime: 0, navigationType: 'Other', wasFetchedViaSpdy: true, wasNpnNegotiated: true, npnNegotiatedProtocol: 'h2', wasAlternateProtocolAvailable: false, connectionInfo: 'h2' })
            };
        }

        const originalPermissionsQuery = navigator.permissions.query.bind(navigator.permissions);
        navigator.permissions.query = (parameters) => {
            if (parameters.name === 'notifications') return Promise.resolve({ state: Notification.permission, onchange: null });
            if (parameters.name === 'geolocation') return Promise.resolve({ state: 'prompt', onchange: null });
            return originalPermissionsQuery(parameters);
        };

        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) return 'Google Inc. (NVIDIA)';
            if (parameter === 37446) return 'ANGLE (NVIDIA, GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)';
            return getParameter.apply(this, arguments);
        };

        if (window.RTCPeerConnection) window.RTCPeerConnection = undefined;
        if (window.webkitRTCPeerConnection) window.webkitRTCPeerConnection = undefined;
        if (window.mozRTCPeerConnection) window.mozRTCPeerConnection = undefined;
        """


class UserAgentGenerator:
    def __init__(self):
        self.mobile_browser_weights = {'chrome': 0.5, 'safari': 0.3, 'firefox': 0.1, 'edge': 0.1}

    def get_realistic_user_agent(self, mobile_mode: bool = True) -> str:
        if mobile_mode:
            return self._generate_mobile_ua()
        else:
            return self._generate_desktop_ua()

    def _generate_mobile_ua(self) -> str:
        import random
        browser_type = random.choices(list(self.mobile_browser_weights.keys()), weights=list(self.mobile_browser_weights.values()))[0]
        generators = {
            'chrome': self._generate_chrome_mobile_ua,
            'safari': self._generate_safari_mobile_ua,
            'firefox': self._generate_firefox_mobile_ua,
            'edge': self._generate_edge_mobile_ua,
        }
        return generators[browser_type]()

    def _generate_desktop_ua(self) -> str:
        import random
        chrome_ver = f"{random.randint(110, 125)}.{random.randint(0, 9)}.{random.randint(4000, 6500)}.{random.randint(0, 200)}"
        return f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_ver} Safari/537.36"

    def _generate_chrome_mobile_ua(self) -> str:
        import random
        chrome_ver = f"{random.randint(110, 125)}.{random.randint(0, 9)}.{random.randint(4000, 6500)}.{random.randint(0, 200)}"
        android_ver = random.choice(['10', '11', '12', '13', '14'])
        device = random.choice(['SM-G991B', 'SM-G998B', 'Mi 10', 'Mi 11', 'Pixel 6'])
        return f"Mozilla/5.0 (Linux; Android {android_ver}; {device}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_ver} Mobile Safari/537.36"

    def _generate_safari_mobile_ua(self) -> str:
        import random
        ios_ver = random.choice(['15_0', '15_5', '16_0', '16_5', '17_0'])
        safari_ver = f"{random.randint(15, 17)}.{random.randint(0, 6)}"
        return f"Mozilla/5.0 (iPhone; CPU iPhone OS {ios_ver} like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/{safari_ver} Mobile/15E148 Safari/604.1"

    def _generate_firefox_mobile_ua(self) -> str:
        import random
        firefox_ver = random.randint(110, 125)
        android_ver = random.choice(['10', '11', '12', '13'])
        return f"Mozilla/5.0 (Android {android_ver}; Mobile; rv:{firefox_ver}.0) Gecko/{firefox_ver}.0 Firefox/{firefox_ver}.0"

    def _generate_edge_mobile_ua(self) -> str:
        import random
        edge_ver = f"{random.randint(110, 125)}.{random.randint(0, 9)}.{random.randint(1000, 2500)}.{random.randint(0, 100)}"
        chrome_ver = f"{random.randint(110, 125)}.{random.randint(0, 9)}.{random.randint(4000, 6500)}.{random.randint(0, 200)}"
        android_ver = random.choice(['10', '11', '12'])
        device = random.choice(['SM-G991B', 'Pixel 6'])
        return f"Mozilla/5.0 (Linux; Android {android_ver}; {device}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_ver} Mobile Safari/537.36 EdgA/{edge_ver}"


class PlaywrightController:
    def __init__(self, headless: bool = None, browser_type: str = "chromium", proxy_url: Optional[str] = "", user_agent: Optional[str] = None, debug: bool = False, mobile_mode: bool = False):
        self.headless = os.environ.get("HEADLESS", "true").lower() == "true" if headless is None else headless
        self.browser_type = browser_type
        self.proxy_url = proxy_url
        self.debug = debug
        self.mobile_mode = mobile_mode

        self.anti_crawler_config = AntiCrawlerConfig()

        if user_agent:
            self.user_agent = user_agent
        else:
            self.user_agent = self.anti_crawler_config._ua_generator.get_realistic_user_agent(mobile_mode)

        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    async def start_browser(self) -> None:
        if self._browser is not None:
            return

        start_time = time.time()

        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()

            browser_launcher = getattr(self._playwright, self.browser_type)

            launch_options = {"headless": self.headless}

            if self.browser_type == "chromium":
                launch_options["args"] = [
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                ]

            if self.proxy_url:
                launch_options["proxy"] = {"server": self.proxy_url}

            self._browser = await browser_launcher.launch(**launch_options)

            anti_config = self.anti_crawler_config.get_anti_crawler_config(self.mobile_mode)

            context_options = {
                "user_agent": self.user_agent,
                "viewport": anti_config.get("viewport", {"width": 1920, "height": 1080}),
                "locale": "zh-CN",
                "timezone_id": "Asia/Shanghai",
            }

            if "extra_http_headers" in anti_config:
                context_options["extra_http_headers"] = anti_config["extra_http_headers"]

            for key in ["java_script_enabled", "ignore_https_errors", "bypass_csp"]:
                if key in anti_config:
                    context_options[key] = anti_config[key]

            self._context = await self._browser.new_context(**context_options)
            self._page = await self._context.new_page()

            await self._apply_anti_crawler_scripts(self._page)

        except Exception as e:
            print(f"[Playwright] 启动浏览器失败: {str(e)}")
            raise

    async def _apply_anti_crawler_scripts(self, page) -> None:
        try:
            init_script = AntiCrawlerConfig.get_init_script()
            await page.add_init_script(init_script)
        except Exception as e:
            print(f"[Playwright] 反检测脚本注入失败: {str(e)}")

    async def open_url(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 30000) -> bool:
        if not self.is_page_valid():
            await self.start_browser()

        try:
            await self._page.goto(url, wait_until=wait_until, timeout=timeout)
            await self._smart_wait()
            return True
        except Exception as e:
            print(f"[Playwright] 打开URL失败: {url}, 错误: {str(e)}")
            return False

    async def _smart_wait(self) -> None:
        try:
            await self._page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        await asyncio.sleep(0.5)

    async def close(self) -> None:
        try:
            if self._page:
                await self._page.close()
                self._page = None
            if self._context:
                await self._context.close()
                self._context = None
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
        except Exception as e:
            print(f"[Playwright] 关闭浏览器失败: {str(e)}")

    async def __aenter__(self):
        await self.start_browser()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    @property
    def page(self):
        return self._page

    def is_page_valid(self) -> bool:
        if self._page is None:
            return False
        try:
            return hasattr(self._page, '_impl_obj') and self._page._impl_obj is not None
        except Exception:
            return False