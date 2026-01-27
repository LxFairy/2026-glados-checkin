#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2026 GLaDOS 自动签到 (极客增强版 - 支持钉钉机器人)

功能：
- 全自动签到 + 智能多域名切换
- 支持 PushPlus & 钉钉机器人 双推送
- 适配钉钉加签安全校验
"""

import requests
import json
import os
import sys
import time
import hmac
import hashlib
import base64
import urllib.parse
from datetime import datetime

# Fix Windows Unicode Output
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# ================= 配置 =================

DOMAINS = [
    "https://glados.cloud",
    "https://glados.rocks", 
    "https://glados.network",
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Content-Type': 'application/json;charset=UTF-8',
    'Accept': 'application/json, text/plain, */*',
}

# ================= 工具函数 =================

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")

def extract_cookie(raw: str):
    if not raw: return None
    raw = raw.strip()
    if 'koa:sess=' in raw or 'koa:sess.sig=' in raw: return raw
    if raw.startswith('{'):
        try: return 'koa.sess=' + json.loads(raw).get('token')
        except: pass
    if raw.count('.') == 2 and '=' not in raw and len(raw) > 50: return 'koa:sess=' + raw
    return raw

def get_cookies():
    raw = os.environ.get("GLADOS_COOKIE", "")
    if not raw:
        log("❌ 未配置 GLADOS_COOKIE")
        return []
    sep = '\n' if '\n' in raw else '&'
    return [extract_cookie(c) for c in raw.split(sep) if c.strip()]

# ================= 核心逻辑 =================

class GLaDOS:
    def __init__(self, cookie):
        self.cookie = cookie
        self.domain = DOMAINS[0]
        self.email = "?"
        self.left_days = "?"
        self.points = "?"
        self.points_change = "?"
        self.exchange_info = ""
        self.exchange_text = "" # 纯文本版用于钉钉
        
    def req(self, method, path, data=None):
        for d in DOMAINS:
            try:
                url = f"{d}{path}"
                h = HEADERS.copy()
                h['Cookie'] = self.cookie
                h['Origin'] = d
                h['Referer'] = f"{d}/console/checkin"
                
                if method == 'GET':
                    resp = requests.get(url, headers=h, timeout=10)
                else:
                    resp = requests.post(url, headers=h, json=data, timeout=10)
                
                if resp.status_code == 200:
                    self.domain = d
                    return resp.json()
            except Exception as e:
                log(f"⚠️ {d} 请求失败: {e}")
                continue
        return None

    def get_status(self):
        res = self.req('GET', '/api/user/status')
        if res and 'data' in res:
            d = res['data']
            self.email = d.get('email', 'Unknown')
            self.left_days = str(d.get('leftDays', '?')).split('.')[0]
            return True
        return False

    def get_points(self):
        res = self.req('GET', '/api/user/points')
        if res and 'points' in res:
            self.points = str(res.get('points', '0')).split('.')[0]
            history = res.get('history', [])
            if history:
                last = history[0]
                change = str(last.get('change', '0')).split('.')[0]
                self.points_change = f"+{change}" if not change.startswith('-') else change
            
            plans = res.get('plans', {})
            pts = int(self.points)
            exchange_lines = []
            text_lines = []
            for plan_id, plan_data in plans.items():
                need, days = plan_data['points'], plan_data['days']
                if pts >= need:
                    exchange_lines.append(f"✅ {need}分→{days}天 (可兑换)")
                    text_lines.append(f"● {need}分→{days}天 (✅)")
                else:
                    exchange_lines.append(f"❌ {need}分→{days}天 (差{need-pts}分)")
                    text_lines.append(f"● {need}分→{days}天 (❌ 差{need-pts})")
            self.exchange_info = "<br>".join(exchange_lines)
            self.exchange_text = "\n".join(text_lines)
            return True
        return False

    def checkin(self):
        return self.req('POST', '/api/user/checkin', {'token': 'glados.cloud'})

# ================= 推送模块 =================

def push_dingtalk(webhook, secret, title, results_objs):
    """钉钉机器人推送逻辑 (2026 极客标准)"""
    if not webhook: return
    
    # 1. 处理加签
    timestamp = str(round(time.time() * 1000))
    url = webhook
    if secret:
        string_to_sign = f'{timestamp}\n{secret}'
        hmac_code = hmac.new(secret.encode('utf-8'), string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        url = f"{webhook}&timestamp={timestamp}&sign={sign}"

    # 2. 构造 Markdown 内容
    md_text = f"## {title}\n\n"
    for g in results_objs:
        md_text += f"### 👤 账号: {g.email}\n"
        md_text += f"- **积分**: `{g.points}` ({g.points_change})\n"
        md_text += f"- **天数**: `{g.left_days} 天`\n"
        md_text += f"- **结果**: {g.last_msg}\n"
        md_text += f"#### 🎁 兑换选项:\n{g.exchange_text}\n\n---\n"
    
    md_text += f"\n> 推送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    data = {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": md_text}
    }
    
    try:
        res = requests.post(url, json=data, timeout=10).json()
        if res.get("errcode") == 0: log("✅ 钉钉推送成功")
        else: log(f"❌ 钉钉推送失败: {res.get('errmsg')}")
    except Exception as e:
        log(f"⚠️ 钉钉请求异常: {e}")

def push_plus(token, title, content):
    if not token: return
    try:
        url = "http://www.pushplus.plus/send"
        requests.get(url, params={'token': token, 'title': title, 'content': content, 'template': 'html'}, timeout=5)
        log("✅ PushPlus 推送成功")
    except:
        log("❌ PushPlus 推送失败")

# ================= 主程序 =================

def main():
    log("🚀 2026 GLaDOS Checkin Starting...")
    cookies = get_cookies()
    if not cookies: sys.exit(1)
    
    html_results = []
    results_objs = []
    success_cnt = 0
    
    for i, cookie in enumerate(cookies, 1):
        g = GLaDOS(cookie)
        res = g.checkin()
        g.last_msg = res.get('message', 'Failure') if res else "Network Error"
        
        g.get_status()
        g.get_points()
        
        log(f"用户: {g.email} | 积分: {g.points} | 天数: {g.left_days} | 结果: {g.last_msg}")
        if "Checkin" in g.last_msg: success_cnt += 1
        
        results_objs.append(g)
        html_results.append(f"""
<div style="border:2px solid #333; padding:15px; margin-bottom:15px; border-radius:10px; background:#fff;">
    <h3 style="margin:0 0 15px 0; color:#333; border-bottom:2px solid #333; padding-bottom:8px;">👤 {g.email}</h3>
    <p style="margin:8px 0; color:#000; font-size:16px;"><b>当前积分:</b> <span style="color:#e74c3c; font-size:22px; font-weight:bold;">{g.points}</span> <span style="color:#27ae60; font-weight:bold;">({g.points_change})</span></p>
    <p style="margin:8px 0; color:#000; font-size:16px;"><b>剩余天数:</b> <span style="font-weight:bold;">{g.left_days} 天</span></p>
    <p style="margin:8px 0; color:#000; font-size:16px;"><b>签到结果:</b> {g.last_msg}</p>
    <div style="margin-top:15px; padding:12px; background:#f0f0f0; border-radius:8px; border:1px solid #ccc;">
        <p style="margin:0 0 8px 0; color:#333; font-weight:bold; font-size:15px;">🎁 兑换选项:</p>
        <p style="margin:0; color:#000; font-size:14px; line-height:1.8;">{g.exchange_info}</p>
    </div>
</div>
""")

    title = f"GLaDOS签到: 成功{success_cnt}/{len(cookies)}"
    
    # 1. 尝试 PushPlus 推送
    ptoken = os.environ.get("PUSHPLUS_TOKEN")
    if ptoken:
        content = "".join(html_results) + f"<br><small>时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</small>"
        push_plus(ptoken, title, content)
        
    # 2. 尝试 钉钉机器人 推送
    d_webhook = os.environ.get("DINGTALK_WEBHOOK")
    d_secret = os.environ.get("DINGTALK_SECRET")
    if d_webhook:
        push_dingtalk(d_webhook, d_secret, title, results_objs)

if __name__ == '__main__':
    main()
