import requests
import re

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
})

resp = session.get('https://mp.weixin.qq.com/')
content = resp.text

qr_pattern = r'(https?://mp\.weixin\.qq\.com/cgi-bin/loginqrcode\?action=getqrcode&param=\d+)'
qr_match = re.search(qr_pattern, content)

uuid_pattern = r'uuid["\']\s*:\s*["\']([^"\']+)["\']'
uuid_match = re.search(uuid_pattern, content)

print('QR match:', qr_match.group(1) if qr_match else None)
print('UUID match:', uuid_match.group(1) if uuid_match else None)

if not qr_match or not uuid_match:
    print('\n=== Trying API method ===')
    import uuid as uuid_module
    uuid_str = str(uuid_module.uuid4()).replace('-', '')
    session.cookies.set('uuid', uuid_str)

    url = 'https://mp.weixin.qq.com/cgi-bin/bizlogin?action=startlogin'
    data = {
        'fingerprint': uuid_str,
        'token': '',
        'lang': 'zh_CN',
        'f': 'json',
        'ajax': '1',
        'redirect_url': '/cgi-bin/settingpage?t=setting/index&action=index&token=&lang=zh_CN',
        'login_type': '3',
    }
    resp = session.post(url, data=data)
    print('Startlogin status:', resp.status_code)
    print('Startlogin cookies:', dict(session.cookies))
    uuid_from_cookie = resp.cookies.get('uuid')
    print('UUID from cookie:', uuid_from_cookie)

    if uuid_from_cookie:
        qr_url = f'https://mp.weixin.qq.com/cgi-bin/scanloginqrcode?action=getqrcode&uuid={uuid_from_cookie}&random=123456'
        resp2 = session.get(qr_url, allow_redirects=False)
        print('QR status:', resp2.status_code)
        print('QR content-type:', resp2.headers.get('content-type'))