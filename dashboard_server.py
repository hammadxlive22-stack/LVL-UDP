# -*- @MASTER_FF_01 -*-
"""
MASTER OFFICIAL - Dashboard Server
Full Web Dashboard with Blue Ninja Theme
"""

import asyncio
import json
import os
import time
from typing import Dict, List, Any, Optional
from aiohttp import web

# ==================== GLOBAL STATE ====================
class BotState:
    def __init__(self):
        self.accounts: Dict[str, Dict[str, Any]] = {}
        self.logs: List[Dict[str, Any]] = []
        self.max_logs = 200
        self.total_matches = 0
        self.total_gained_exp = 0
        self.start_time = time.time()
        self.account_workers: Dict[str, asyncio.Task] = {}
        self.refresh_callbacks: Dict[str, Any] = {}
        self.account_credentials: Dict[str, Dict[str, Any]] = {}

    def log(self, message: str, level: str = "info", uid: Optional[str] = None):
        entry = {
            "time": time.strftime("%H:%M:%S"),
            "level": level,
            "message": message,
            "uid": uid
        }
        self.logs.append(entry)
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)

    def register_account(self, uid: str, nickname: str, region: str, level: int, exp: int, likes: int = 0):
        uid_str = str(uid)
        if uid_str not in self.accounts:
            self.accounts[uid_str] = {
                "uid": uid_str,
                "nickname": nickname or f"Player_{uid_str[:6]}",
                "region": region or "BD",
                "level": level or 1,
                "initial_exp": exp,
                "current_exp": exp,
                "gained_exp": 0,
                "likes": likes or 0,
                "status": "ONLINE",
                "matches_played": 0,
                "active_matches": 0,
                "last_match_time": None,
                "last_updated": time.strftime("%H:%M:%S"),
                "is_paused": False,
                "uptime_seconds": int(time.time()),
                "match_history": []
            }
        else:
            acc = self.accounts[uid_str]
            if nickname:
                acc["nickname"] = nickname
            if region:
                acc["region"] = region
            if level:
                acc["level"] = level
            acc["current_exp"] = exp
            acc["gained_exp"] = max(0, exp - acc["initial_exp"])
            acc["likes"] = likes
            acc["status"] = "ONLINE"
            acc["last_updated"] = time.strftime("%H:%M:%S")
        self.recalc_totals()

    def update_exp(self, uid: str, current_exp: int, level: Optional[int] = None):
        uid_str = str(uid)
        if uid_str in self.accounts:
            acc = self.accounts[uid_str]
            old_exp = acc["current_exp"]
            acc["current_exp"] = current_exp
            if level is not None and level > 0:
                acc["level"] = level
            acc["gained_exp"] = max(0, current_exp - acc["initial_exp"])
            acc["last_updated"] = time.strftime("%H:%M:%S")
            diff = current_exp - old_exp
            if diff > 0:
                self.log(f"{acc['nickname']} gained +{diff} EXP! Total: +{acc['gained_exp']}", "success", uid_str)
            self.recalc_totals()

    def update_status(self, uid: str, status: str, active_matches: Optional[int] = None):
        uid_str = str(uid)
        if uid_str in self.accounts:
            self.accounts[uid_str]["status"] = status
            if active_matches is not None:
                self.accounts[uid_str]["active_matches"] = active_matches
            self.accounts[uid_str]["last_updated"] = time.strftime("%H:%M:%S")

    def increment_match(self, uid: str):
        uid_str = str(uid)
        self.total_matches += 1
        if uid_str in self.accounts:
            acc = self.accounts[uid_str]
            acc["matches_played"] += 1
            acc["last_match_time"] = time.strftime("%H:%M:%S")
            acc["last_updated"] = time.strftime("%H:%M:%S")
            # Match history
            history = acc.get("match_history", [])
            history.append({
                "time": time.strftime("%H:%M:%S"),
                "msg": f"Match #{acc['matches_played']} completed"
            })
            if len(history) > 20:
                history.pop(0)
            acc["match_history"] = history
            self.log(f"{acc['nickname']} finished Match #{acc['matches_played']}", "info", uid_str)

    def recalc_totals(self):
        self.total_gained_exp = sum(acc.get("gained_exp", 0) for acc in self.accounts.values())

    def get_exp_per_hour(self) -> int:
        elapsed = max(1, time.time() - self.start_time)
        return int(self.total_gained_exp / (elapsed / 3600))

    def get_total_active_matches(self) -> int:
        return sum(acc.get("active_matches", 0) for acc in self.accounts.values())


bot_state = BotState()


# ==================== PATHS ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(TEMPLATES_DIR, "static")
TEMPLATE_PATH = os.path.join(TEMPLATES_DIR, "index.html")
ACCOUNTS_FILE = "accounts.json"


# ==================== HTTP HANDLERS ====================

async def handle_index(request: web.Request) -> web.Response:
    if os.path.exists(TEMPLATE_PATH):
        with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = """
        <html><body style="background:#050a18;color:#e8f4ff;font-family:sans-serif;padding:40px;text-align:center">
        <h1>⚠️ templates/index.html not found!</h1>
        <p>Please create templates/index.html</p>
        </body></html>
        """
    return web.Response(text=content, content_type="text/html", charset="utf-8")


async def handle_get_stats(request: web.Request) -> web.Response:
    accounts_data = list(bot_state.accounts.values())
    accounts_data.sort(key=lambda x: x.get("gained_exp", 0), reverse=True)
    return web.json_response({
        "total_accounts": len(bot_state.accounts),
        "total_matches": bot_state.total_matches,
        "total_matches_started": bot_state.total_matches,
        "total_gained_exp": bot_state.total_gained_exp,
        "total_active_matches": bot_state.get_total_active_matches(),
        "exp_per_hour": bot_state.get_exp_per_hour(),
        "accounts": accounts_data,
        "logs": bot_state.logs[-60:],
        "uptime": int(time.time() - bot_state.start_time)
    })


async def handle_add_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        existing = []
        if os.path.exists(ACCOUNTS_FILE):
            try:
                with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = []

        if "uid" in data and "password" in data:
            uid = str(data["uid"]).strip()
            pwd = str(data["password"]).strip()
            if not uid or not pwd:
                return web.json_response({"status": "error", "error": "UID and Password required"})
            existing = [acc for acc in existing if str(acc.get("uid")) != uid]
            existing.append({"uid": uid, "password": pwd})
        elif "token" in data:
            token = str(data["token"]).strip()
            if not token:
                return web.json_response({"status": "error", "error": "Token required"})
            existing = [acc for acc in existing if acc.get("token") != token]
            existing.append({"token": token})
        else:
            return web.json_response({"status": "error", "error": "Invalid payload"})

        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)

        bot_state.log(f"New account added: {data.get('uid') or 'Token'}", "success")

        if "on_account_added" in bot_state.refresh_callbacks:
            asyncio.create_task(bot_state.refresh_callbacks["on_account_added"](data))

        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_delete_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        # Keep the deletion secret server-side; configure DELETE_CONFIRM_PASSWORD in Railway.
        expected_password = os.environ.get("DELETE_CONFIRM_PASSWORD", "")
        supplied_password = str(data.get("confirm_password", ""))
        if not expected_password:
            return web.json_response({"status": "error", "error": "Delete password is not configured on the server"}, status=503)
        if not supplied_password or not __import__("hmac").compare_digest(supplied_password, expected_password):
            return web.json_response({"status": "error", "error": "Incorrect confirmation password"}, status=403)
        uid = str(data.get("uid", "")).strip()
        if not uid:
            return web.json_response({"status": "error", "error": "UID required"}, status=400)
        if os.path.exists(ACCOUNTS_FILE):
            with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
            existing = [acc for acc in existing if str(acc.get("uid")) != uid and str(acc.get("token", ""))[:20] != uid]
            with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2)

        if uid in bot_state.accounts:
            del bot_state.accounts[uid]

        if uid in bot_state.account_workers:
            bot_state.account_workers[uid].cancel()
            del bot_state.account_workers[uid]

        bot_state.log(f"Account {uid} removed", "warning", uid)
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_refresh_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        uid = str(data.get("uid")).strip()
        if "on_refresh_account" in bot_state.refresh_callbacks:
            asyncio.create_task(bot_state.refresh_callbacks["on_refresh_account"](uid))
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_pause_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        uid = str(data.get("uid")).strip()
        if uid in bot_state.accounts:
            acc = bot_state.accounts[uid]
            acc["is_paused"] = not acc.get("is_paused", False)
            if acc["is_paused"]:
                acc["status"] = "PAUSED"
            else:
                acc["status"] = "ONLINE"
            return web.json_response({"status": "ok", "is_paused": acc["is_paused"]})
        return web.json_response({"status": "error", "error": "Account not found"})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_pause_all(request: web.Request) -> web.Response:
    try:
        all_paused = all(acc.get("is_paused", False) for acc in bot_state.accounts.values()) if bot_state.accounts else False
        new_state = not all_paused
        for acc in bot_state.accounts.values():
            acc["is_paused"] = new_state
            acc["status"] = "PAUSED" if new_state else "ONLINE"
        return web.json_response({"status": "ok", "all_paused": new_state})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_restart_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        uid = str(data.get("uid")).strip()
        if uid in bot_state.account_workers:
            bot_state.account_workers[uid].cancel()
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_clear_logs(request: web.Request) -> web.Response:
    try:
        bot_state.logs.clear()
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})



def _vault_authorized(request: web.Request) -> bool:
    import hmac
    expected = os.environ.get("VAULT_PASSWORD", "2795601167")
    supplied = request.headers.get("X-Vault-Password", "")
    return bool(expected and supplied and hmac.compare_digest(supplied, expected))


async def handle_vault_accounts(request: web.Request) -> web.Response:
    if not _vault_authorized(request):
        return web.json_response({"status": "error", "error": "Vault locked or incorrect password"}, status=403)
    try:
        rows = []
        if os.path.exists(ACCOUNTS_FILE):
            with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                stored = json.load(f)
            if not isinstance(stored, list):
                stored = []
        else:
            stored = []
        for item in stored:
            uid = str(item.get("uid", ""))
            live = bot_state.accounts.get(uid, {})
            token = str(item.get("token", ""))
            rows.append({
                "uid": uid or ("TOKEN-" + token[:8] if token else "—"),
                "password": str(item.get("password", "")),
                "token": token,
                "name": str(item.get("label") or live.get("nickname") or ("Token account" if token else "Unlabelled account")),
                "level": live.get("level", item.get("level", "—")),
                "region": live.get("region", item.get("region", "—")),
                "type": "Access Token" if token else "UID / Password"
            })
        return web.json_response({"status": "ok", "accounts": rows})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)}, status=500)


# ==================== SERVER START ====================

async def start_web_dashboard(host: str = "0.0.0.0", port: int = 20333):
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/stats", handle_get_stats)
    app.router.add_get("/api/vault/accounts", handle_vault_accounts)
    app.router.add_post("/api/account/add", handle_add_account)
    app.router.add_post("/api/account/delete", handle_delete_account)
    app.router.add_post("/api/account/refresh", handle_refresh_account)
    app.router.add_post("/api/account/pause", handle_pause_account)
    app.router.add_post("/api/account/pause_all", handle_pause_all)
    app.router.add_post("/api/account/restart", handle_restart_account)
    app.router.add_post("/api/logs/clear", handle_clear_logs)

    # Static files (logo, images)
    if os.path.exists(STATIC_DIR):
        app.router.add_static("/static", STATIC_DIR)
        print(f"\033[92m[+] Static folder: {STATIC_DIR}\033[0m")
    else:
        os.makedirs(STATIC_DIR, exist_ok=True)
        print(f"\033[93m[!] Created static folder: {STATIC_DIR}\033[0m")
        print(f"\033[93m[!] Put your logo.png inside templates/static/\033[0m")

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    print(f"\033[92m[+] Web Dashboard: http://localhost:{port}\033[0m")
    print(f"\033[92m[+] Logo path: {os.path.join(STATIC_DIR, 'logo.png')}\033[0m")