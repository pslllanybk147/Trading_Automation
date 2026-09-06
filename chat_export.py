# -*- coding: utf-8 -*-
"""ดึงแชทจากเบราว์เซอร์ (CDP port 9222) ลงไฟล์ markdown

ใช้ร่วมกับ Chrome ที่เปิด debug port ไว้:
  chrome.exe --remote-debugging-port=9222 --user-data-dir=%TEMP%\\chrome-debug
(ต้องเป็น user-data-dir แยก — Chrome ปิด DevTools ถ้าใช้โปรไฟล์ default)

ผู้ใช้ล็อกอินเว็บแชทในหน้าต่างนั้นเอง แล้วรัน:
  python chat_export.py                      # เลือก tab แชทอัตโนมัติ
  python chat_export.py --url chatgpt.com    # กรอง tab ที่ URL มีคำนี้
  python chat_export.py -o mychat.md

รองรับ: ChatGPT / Claude / Gemini (แยก role ได้) + fallback อื่น ๆ (ดึงข้อความ
ทั้งกระทู้เป็นเอกสารเดียว)
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from datetime import datetime, UTC
from pathlib import Path

DEBUG_PORT = 9333
DEBUG_HOST = f"http://127.0.0.1:{DEBUG_PORT}"

# selector ต่อไซต์: (container_css, role_attr_of_each_msg) — best effort
SITE_SELECTORS = {
    "chatgpt": {
        "msg": "[data-message-author-role]",
        "role": "el.getAttribute('data-message-author-role')",
        "scroll": "document.querySelector('main')",
    },
    "claude": {
        "msg": "[data-testid='user-message'], .font-claude-message",
        "role": ("el.dataset.testid === 'user-message' ? 'user' : 'assistant'"),
        "scroll": "document.querySelector('main')",
    },
    "gemini": {
        "msg": "user-query, model-response",
        "role": "el.tagName === 'USER-QUERY' ? 'user' : 'assistant'",
        "scroll": "document.querySelector('chat-window, main')",
    },
    "aipass": {
        # de.aipass.net (ไทย เอไอ พาส): ทุกข้อความ = .markdown-content
        # ของผู้ใช้มี class bg-bg-chat-user, ของ AI ไม่มี
        "msg": ".markdown-content",
        "role": "el.className.includes('bg-bg-chat-user') ? 'user' : 'assistant'",
        "scroll": "document.querySelector('main')",
    },
}


def cdp_http(path: str):
    # localhost — บังคับ bypass proxy (บางเครื่องตั้ง http_proxy ไว้)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f"{DEBUG_HOST}{path}", timeout=10) as r:
        return json.loads(r.read().decode())


def pick_tab(url_filter: str) -> dict:
    tabs = [t for t in cdp_http("/json/list") if t.get("type") == "page"]
    if not tabs:
        raise SystemExit("ไม่พบ tab ในเบราว์เซอร์ — เปิด Chrome ด้วย debug port ก่อน")
    if url_filter:
        hits = [t for t in tabs if url_filter.lower() in t.get("url", "").lower()]
        if not hits:
            raise SystemExit(f"ไม่พบ tab ที่ URL มีคำว่า '{url_filter}' — "
                             f"tabs ที่มี: {[t['url'][:60] for t in tabs]}")
        tabs = hits
    return tabs[0]


class CDP:
    def __init__(self, ws_url: str):
        import websocket
        self.ws = websocket.create_connection(ws_url, timeout=30)
        self._id = 0

    def call(self, method: str, **params) -> dict:
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self._id:
                if "error" in msg:
                    raise RuntimeError(f"CDP error: {msg['error']}")
                return msg.get("result", {})

    def eval_js(self, expr: str):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True,
                      awaitPromise=True)
        return r.get("result", {}).get("value")

    def close(self):
        self.ws.close()


EXTRACT_JS = """
() => {
  const cfgSel = %(cfg)s;
  const msgs = [...document.querySelectorAll(cfgSel.msg)];
  const out = [];
  for (const el of msgs) {
    let role;
    try { role = %(role)s; } catch (e) { role = 'unknown'; }
    const text = (el.innerText || '').trim();
    if (text) out.push({ role: String(role), text });
  }
  return { n: out.length, messages: out,
           title: document.title, url: location.href };
}
"""


def site_cfg(url: str) -> dict | None:
    for key, cfg in SITE_SELECTORS.items():
        if key in url.lower():
            return cfg
    return None


def extract(cdp: CDP, url: str, max_rounds: int = 8) -> dict:
    """scroll ขึ้นหาแชทเก่า (virtualized list) จนจำนวนข้อความไม่เพิ่ม แล้วดึงทั้งหมด"""
    cfg = site_cfg(url)
    if cfg is None:
        text = cdp.eval_js("(document.body.innerText || '')")
        return {"title": cdp.eval_js("document.title") or "", "url": url,
                "messages": [{"role": "document", "text": text}]}
    # ต้อง wrap เป็น IIFE — ไม่งั้น Runtime.evaluate คืน "ตัวฟังก์ชัน" ไม่ใช่ผลลัพธ์
    # (role expression ฉีดแบบดิบ — ห้าม json.dumps ไม่งั้นกลายเป็น string literal)
    js = "(" + (EXTRACT_JS % {"cfg": json.dumps(cfg),
                              "role": cfg["role"]}) + ")()"
    scroll_expr = f"(() => {{ const s = {cfg['scroll']}; if (s) s.scrollTop = 0; }})()"
    prev = -1
    for i in range(max_rounds):
        cdp.eval_js(scroll_expr)
        time.sleep(1.0)
        data = cdp.eval_js(js)
        if data and data["n"] == prev:
            break
        prev = data["n"] if data else -1
    return data


def to_md(data: dict) -> str:
    lines = [
        f"# {data['title']}",
        "",
        f"- source: {data['url']}",
        f"- exported: {datetime.now(UTC):%Y-%m-%d %H:%M UTC}",
        f"- messages: {len(data['messages'])}",
        "",
    ]
    for m in data["messages"]:
        role = m["role"]
        label = {"user": "🧑 User", "assistant": "🤖 Assistant"}.get(role, f"💬 {role}")
        lines += [f"## {label}", "", m["text"], "", "---", ""]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="export chat tab -> markdown")
    ap.add_argument("--url", default="", help="กรอง tab ด้วย substring ของ URL")
    ap.add_argument("-o", "--out", default="")
    args = ap.parse_args()

    tab = pick_tab(args.url)
    print(f"tab: {tab['title'][:70]}\n     {tab['url'][:90]}")
    cdp = CDP(tab["webSocketDebuggerUrl"])
    try:
        data = extract(cdp, tab["url"])
    finally:
        cdp.close()
    md = to_md(data)
    out = Path(args.out) if args.out else Path(
        f"chat_export_{datetime.now():%Y%m%d_%H%M}.md")
    out.write_text(md, encoding="utf-8")
    print(f"บันทึก {out}: {len(data['messages'])} ข้อความ, {len(md):,} ตัวอักษร")


if __name__ == "__main__":
    main()
