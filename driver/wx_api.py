"""
微信公众平台扫码登录模块（简化版）
基于纯HTTP API实现二维码登录，无需浏览器
"""
import os
import re
import time
import json
from urllib.parse import quote
from typing import Optional, Dict, Any, Callable
from threading import Lock, Timer

import requests

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import cfg, saveWxToken, getWxToken


class WeChatAPI:
    def __init__(self):
        self.base_url = "https://mp.weixin.qq.com"
        self.login_url = f"{self.base_url}/"
        self.home_url = f"{self.base_url}/cgi-bin/home"

        self._islogin = False
        self.is_logged_in = False
        self.fingerprint = self._generate_uuid()
        self.session = requests.Session()
        self.token = None
        self.cookies_dict = []
        self.cookies = {}
        self.qr_code_path = "static/qr.png"
        self.wx_login_url = f"/{self.qr_code_path}"
        self.lock_file_path = "data/lock.lock"

        self._lock = Lock()
        self.login_callback = None
        self.notice_callback = None

        self._uuid = None
        self._login_status = "waiting"

        os.makedirs(os.path.dirname(self.qr_code_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.lock_file_path), exist_ok=True)

        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Referer': 'https://mp.weixin.qq.com/'
        })

    def _generate_uuid(self):
        import uuid
        return str(uuid.uuid4()).replace('-', '')

    def _reset_state(self):
        self._login_status = "waiting"
        self._islogin = False
        self.is_logged_in = False
        self._uuid = None

    def get_qr_code(self, callback=None, notice=None):
        self._reset_state()
        self._clean_lock()
        if self.check_lock():
            return {'code': None, 'is_exists': False, 'msg': '登录脚本正在运行，请勿重复运行'}

        with self._lock:
            self.login_callback = callback
            self.notice_callback = notice

            try:
                self.session.get(self.login_url)
                qr_info = self._extract_qr_info()

                if qr_info:
                    self._clean_qr_code()
                    self._generate_qr_image(qr_info['qr_url'])
                    self.set_lock()
                    self._uuid = qr_info['uuid']
                    self._start_login_check(qr_info['uuid'])

                    if self.notice_callback:
                        self.notice_callback()

                    return {
                        'code': f"/{self.qr_code_path}?t={int(time.time())}",
                        'is_exists': os.path.exists(self.qr_code_path),
                        'uuid': qr_info['uuid'],
                        'msg': '请使用微信扫描二维码登录'
                    }
                else:
                    return {'code': None, 'is_exists': False, 'msg': '获取二维码失败'}

            except Exception as e:
                return {'code': None, 'is_exists': False, 'msg': f'获取二维码失败: {str(e)}'}

    def _extract_qr_info(self):
        try:
            return self._get_qr_info_api()
        except Exception:
            return None

    def _get_qr_info_api(self):
        try:
            uuid_str = self._generate_uuid()
            url = f"{self.base_url}/cgi-bin/bizlogin?action=startlogin"
            data = {
                "fingerprint": uuid_str, "token": "", "lang": "zh_CN", "f": "json",
                "ajax": "1",
                "redirect_url": "/cgi-bin/settingpage?t=setting/index&action=index&token=&lang=zh_CN",
                "login_type": "3",
            }
            response = self.session.post(url, data=data)
            if response.status_code == 200:
                try:
                    resp_json = response.json()
                    uuid_val = resp_json.get('uuid', uuid_str)
                except Exception:
                    uuid_val = uuid_str
            else:
                uuid_val = uuid_str
            qr_api_url = f"{self.base_url}/cgi-bin/scanloginqrcode?action=getqrcode&uuid={uuid_val}&random={int(time.time() * 1000)}"
            return {'qr_url': qr_api_url, 'uuid': uuid_val}
        except Exception:
            return None

    def _generate_qr_image(self, qr_url):
        os.makedirs(os.path.dirname(self.qr_code_path), exist_ok=True)
        if qr_url.startswith('http'):
            response = self.session.get(qr_url)
            response.raise_for_status()
            with open(self.qr_code_path, 'wb') as f:
                f.write(response.content)
        else:
            api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={quote(qr_url)}"
            response = self.session.get(api_url)
            response.raise_for_status()
            with open(self.qr_code_path, 'wb') as f:
                f.write(response.content)

    def _start_login_check(self, uuid):
        def check_login():
            try:
                status = self._check_login_status()
                if status == 'success':
                    self._islogin = True
                    self._login_status = "success"
                    self._handle_login_success()
                elif status == 'scanned':
                    self._login_status = "scanned"
                    if self.notice_callback:
                        self.notice_callback('已扫描，请在手机上确认登录')
                    Timer(2.0, check_login).start()
                elif status == 'expired':
                    self._login_status = "expired"
                    if self.notice_callback:
                        self.notice_callback('二维码已过期，请重新获取')
                else:
                    Timer(2.0, check_login).start()
            except Exception:
                if self.notice_callback:
                    self.notice_callback('检查登录状态失败，请重试')
            finally:
                self.release_lock()
        Timer(2.0, check_login).start()

    def _check_login_status(self):
        try:
            if not os.path.exists(self.qr_code_path):
                return "not_exists"
            check_url = f"{self.base_url}/cgi-bin/scanloginqrcode"
            params = {"action": "ask", "fingerprint": self.fingerprint, "lang": "zh_CN", "f": "json", "ajax": 1}
            response = self.session.get(check_url, params=params)
            response.raise_for_status()
            if response.headers.get('content-type', '').startswith('application/json'):
                data = response.json()
                status = data.get('status', 0)
                if status == 1 or status == 3:
                    with self._lock:
                        self.cookies = requests.utils.dict_from_cookiejar(self.session.cookies) if self.session.cookies else {}
                    return 'success'
                elif status == 2 or status == 4:
                    return 'scanned'
        except Exception:
            return 'error'
        return 'waiting'

    def _handle_login_success(self):
        try:
            self.is_logged_in = True
            self._extract_login_info()
            self._clean_qr_code()
            self._get_account_info()
            return True
        except Exception:
            return False

    def _extract_login_info(self):
        try:
            login_data = {
                "userlang": "zh_CN", "redirect_url": "", "cookie_forbidden": "0",
                "cookie_cleaned": "0", "plugin_used": "0", "login_type": "3",
                "fingerprint": self.fingerprint, "token": "", "lang": "zh_CN", "f": "json", "ajax": "1"
            }
            response = self.session.post("https://mp.weixin.qq.com/cgi-bin/bizlogin?action=login", data=login_data)
            response.raise_for_status()
            self.cookies = requests.utils.dict_from_cookiejar(self.session.cookies) if self.session.cookies else {}
            token_match = re.search(r'token=([^&\s"\']+)', response.text)
            if token_match:
                self.token = token_match.group(1)
        except Exception:
            pass

    def _get_account_info(self):
        try:
            response = self.session.get(self.home_url)
            response.raise_for_status()
            account_list = self._get_account_list()
            if account_list is None:
                return None
            biz_list = account_list['biz_list']['list']
            first_biz_item = biz_list[0] if len(biz_list) > 0 else None
            account_info = {
                'wx_app_name': first_biz_item.get('username', '') if first_biz_item else '',
                'wx_logo': first_biz_item.get('headimgurl', '') if first_biz_item else '',
            }
            token_data = {
                'token': self.token,
                'cookie_str': self._format_cookies_string(),
                'cookies_list': self._convert_cookies_to_list(),
                'fingerprint': self.fingerprint,
                'expiry': self._calculate_expiry(),
                'ext_data': account_info
            }
            saveWxToken(token_data)
            if self.login_callback:
                self.login_callback(token_data, account_info)
            return account_info
        except Exception:
            return None

    def _get_account_list(self):
        try:
            if not self.token:
                return None
            url = f"{self.base_url}/cgi-bin/switchacct"
            params = {'action': 'get_acct_list', 'fingerprint': self.fingerprint, 'token': self.token, 'lang': 'zh_CN', 'f': 'json', 'ajax': '1'}
            headers = {'accept': '*/*', 'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8', 'x-requested-with': 'XMLHttpRequest', 'Referer': f"{self.base_url}/cgi-bin/home?t=home/index&lang=zh_CN&token={self.token}"}
            response = self.session.get(url, params=params, headers=headers)
            response.raise_for_status()
            result = response.json()
            if 'base_resp' in result and result['base_resp']['ret'] == 0:
                return result
            return None
        except Exception:
            return None

    def _convert_cookies_to_list(self):
        cookies_list = []
        for cookie in self.session.cookies:
            cookie_item = {'name': cookie.name, 'value': cookie.value, 'domain': cookie.domain or '.weixin.qq.com', 'path': cookie.path or '/'}
            if cookie.expires:
                cookie_item['expires'] = cookie.expires
            cookies_list.append(cookie_item)
        return cookies_list

    def _format_cookies_string(self):
        return '; '.join([f"{k}={v}" for k, v in self.cookies.items()])

    def _calculate_expiry(self):
        try:
            for cookie in self.session.cookies:
                if cookie.expires:
                    remaining = cookie.expires - time.time()
                    if remaining > 0:
                        return {'expiry_timestamp': cookie.expires, 'remaining_seconds': int(remaining), 'expiry_time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(cookie.expires))}
            default_expiry = time.time() + 7200
            return {'expiry_timestamp': default_expiry, 'remaining_seconds': 7200, 'expiry_time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(default_expiry))}
        except Exception:
            default_expiry = time.time() + 7200
            return {'expiry_timestamp': default_expiry, 'remaining_seconds': 7200, 'expiry_time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(default_expiry))}

    def _clean_qr_code(self):
        try:
            if os.path.exists(self.qr_code_path):
                os.remove(self.qr_code_path)
        except Exception:
            pass

    def _clean_lock(self):
        try:
            if os.path.exists(self.lock_file_path):
                os.remove(self.lock_file_path)
        except Exception:
            pass

    def check_lock(self, timeout=300):
        if not os.path.exists(self.lock_file_path):
            return False
        try:
            with open(self.lock_file_path, 'r') as f:
                content = f.read().strip()
            parts = content.split('|')
            if parts and len(parts) > 1:
                lock_time = float(parts[1])
                if time.time() - lock_time > timeout:
                    os.remove(self.lock_file_path)
                    return False
            return True
        except Exception:
            return False

    def set_lock(self):
        with open(self.lock_file_path, 'w') as f:
            f.write(f"{os.getpid()}|{time.time()}")
        self.isLOCK = True

    def release_lock(self):
        try:
            if os.path.exists(self.lock_file_path):
                with open(self.lock_file_path, 'r') as f:
                    content = f.read().strip()
                parts = content.split('|')
                if parts and int(parts[0]) == os.getpid():
                    os.remove(self.lock_file_path)
            self.isLOCK = False
            return True
        except Exception:
            return False

    def logout(self):
        with self._lock:
            self.is_logged_in = False
            self._islogin = False
            self._login_status = "waiting"
            self.token = None
            self.cookies = {}
            self.session.cookies.clear()
            self._clean_qr_code()
            token_file = cfg.get("wx.token_file", "data/wx_token.json")
            if os.path.exists(token_file):
                os.remove(token_file)

    def get_login_status(self):
        token_data = getWxToken()
        if token_data and token_data.get('token'):
            expiry = token_data.get('expiry', {})
            remaining = expiry.get('remaining_seconds', 0) if isinstance(expiry, dict) else 0
            if remaining > 0:
                self.is_logged_in = True
                self.token = token_data.get('token')
                self._login_status = "success"
                return {"status": 2, "is_logged_in": True, "msg": "已登录", "expiry": expiry}
        if self._login_status == "scanned":
            return {"status": 1, "is_logged_in": False, "msg": "已扫描，请在手机上确认"}
        elif self._login_status == "expired":
            return {"status": -1, "is_logged_in": False, "msg": "二维码已过期，请重新获取"}
        elif self._login_status == "success":
            return {"status": 2, "is_logged_in": True, "msg": "已登录"}
        else:
            return {"status": 0, "is_logged_in": False, "msg": "未扫码"}


WeChat_api = WeChatAPI()

def get_qr_code(callback=None, notice=None):
    return WeChat_api.get_qr_code(callback, notice)

def get_login_status():
    return WeChat_api.get_login_status()

def logout():
    WeChat_api.logout()
