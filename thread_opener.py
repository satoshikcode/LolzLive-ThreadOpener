import requests
import time
import sys
import os
import json
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")

API_BASE_URL = "https://prod-api.lolz.live"
RATE_LIMIT_DELAY = 0.35
THREADS_PER_PAGE = 50

class C:
    RST  = "\033[0m"
    R    = "\033[91m"
    G    = "\033[92m"
    Y    = "\033[93m"
    B    = "\033[94m"
    M    = "\033[95m"
    CY   = "\033[96m"
    W    = "\033[97m"
    BOLD = "\033[1m"
    DIM  = "\033[2m"

def clr(text, color):
    return f"{color}{text}{C.RST}"

def ts():
    return datetime.now().strftime("%H:%M:%S")

def log(msg, level="info"):
    colors = {"info": C.CY, "ok": C.G, "warn": C.Y, "err": C.R}
    signs  = {"info": "*", "ok": "+", "warn": "!", "err": "-"}
    color = colors.get(level, C.W)
    sign  = signs.get(level, "*")
    print(f"  {clr(ts(), C.DIM)}  {clr(f'[{sign}]', color)} {msg}")

def separator():
    print(f"  {clr('-' * 62, C.DIM)}")

def print_banner():
    print(f"""
  {clr('=' * 50, C.CY)}
  {clr('  LOLZ.LIVE  ::  THREAD OPENER', C.W + C.BOLD)}
  {clr('  Автоматическое открытие закрытых тем', C.DIM)}
  {clr('=' * 50, C.CY)}
""")

class LolzAPI:
    def __init__(self, token: str):
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        })
        self._last_req = 0

    def _rate_limit(self):
        elapsed = time.time() - self._last_req
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        self._last_req = time.time()

    def _request(self, method, endpoint, **kwargs):
        self._rate_limit()
        url = f"{API_BASE_URL}{endpoint}"
        try:
            resp = self.session.request(method, url, **kwargs)
            if resp.status_code == 429:
                log("Rate limit, ожидание 5 сек...", "warn")
                time.sleep(5)
                return self._request(method, endpoint, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError:
            code = resp.status_code
            if code == 403:
                log(f"Нет доступа (403): {endpoint}", "err")
            elif code == 401:
                log("Неверный токен (401)", "err")
            else:
                log(f"HTTP {code}: {endpoint}", "err")
            return None
        except requests.exceptions.ConnectionError:
            log("Нет подключения к сети", "err")
            return None
        except Exception as e:
            log(f"Ошибка: {e}", "err")
            return None

    def get_me(self):
        return self._request("GET", "/users/me")

    def get_my_threads(self, page=1):
        return self._request("GET", "/threads", params={
            "tab": "mythreads", "page": page, "limit": THREADS_PER_PAGE,
        })

    def open_thread(self, thread_id):
        return self._request("PUT", f"/threads/{thread_id}", data={
            "discussion_open": 1,
        })

def get_token():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            token = cfg.get("token", "").strip()
            if token:
                log(f"Токен загружен из {clr('config.json', C.W)}")
                return token
        except Exception:
            pass

    token = os.environ.get("LOLZ_TOKEN", "").strip()
    if token:
        log("Токен загружен из LOLZ_TOKEN")
        return token

    print(f"  {clr('Введите API токен:', C.W)}")
    print(f"  {clr('https://lolz.live/account/api', C.DIM)}")
    print()
    token = input(f"  {clr('>', C.CY)} ").strip()
    if not token:
        log("Токен пуст", "err")
        sys.exit(1)

    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"token": token}, f, indent=2)
        log(f"Токен сохранён в {clr('config.json', C.W)}", "ok")
    except Exception as e:
        log(f"Не удалось сохранить токен: {e}", "warn")

    return token


def fetch_closed_threads(api):
    closed = []
    total = 0
    page = 1

    log("Сканирование тем...")
    separator()

    while True:
        log(f"Страница {clr(str(page), C.W)}")
        data = api.get_my_threads(page=page)
        if not data:
            log("Ошибка загрузки", "err")
            break

        threads = data.get("threads", [])
        if isinstance(threads, dict):
            threads = list(threads.values())
        if not threads:
            break

        for t in threads:
            total += 1
            tid = t.get("thread_id")
            title = t.get("thread_title", "—")
            is_closed = t.get("thread_is_closed", False)
            can_edit = t.get("permissions", {}).get("edit", False)
            forum_id = t.get("forum_id", 0)
            forum_title = t.get("forum", {}).get("forum_title", "") or t.get("node_title", f"Forum #{forum_id}")

            if is_closed:
                closed.append({
                    "id": tid,
                    "title": title,
                    "can_edit": can_edit,
                    "forum_id": forum_id,
                    "forum_title": forum_title,
                })

        if len(threads) < THREADS_PER_PAGE:
            break
        page += 1

    separator()
    log(f"Просканировано: {clr(str(total), C.W)}")
    log(f"Закрытых:       {clr(str(len(closed)), C.Y)}")
    return closed


def get_unique_forums(threads):
    forums = {}
    for t in threads:
        fid = t["forum_id"]
        if fid not in forums:
            forums[fid] = {"id": fid, "title": t["forum_title"], "count": 0}
        forums[fid]["count"] += 1
    return list(forums.values())


def select_filter_mode(forums, total_count):
    print()
    separator()
    log("Выберите режим:")
    print()
    print(f"    {clr('1.', C.W)} Открыть все закрытые темы {clr(f'({total_count} шт)', C.DIM)}")
    print(f"    {clr('2.', C.W)} Открыть только в выбранных разделах")
    print(f"    {clr('3.', C.W)} Открыть во всех разделах кроме выбранных")
    print(f"    {clr('4.', C.W)} Открыть конкретные темы по ID")
    print()

    choice = input(f"  {clr('>', C.CY)} ").strip()

    if choice == "1":
        return None

    if choice == "4":
        print()
        print(f"  {clr('Введите ID тем через запятую:', C.W)}")
        raw = input(f"  {clr('>', C.CY)} ").strip()
        try:
            ids = set(int(x.strip()) for x in raw.split(",") if x.strip())
        except ValueError:
            log("Неверный ввод", "err")
            sys.exit(1)
        if not ids:
            log("Ничего не введено", "err")
            sys.exit(1)
        log(f"Выбрано тем по ID: {clr(str(len(ids)), C.Y)}")
        return ("ids", ids)

    if choice not in ("2", "3"):
        log("Неверный выбор", "err")
        sys.exit(1)

    print()
    separator()
    log("Разделы с закрытыми темами:")
    print()
    for i, f in enumerate(forums, 1):
        fid = f["id"]
        ftitle = f["title"][:45]
        fcount = f["count"]
        print(f"    {clr(f'{i:>3}.', C.DIM)}  {clr(ftitle, C.W)}  {clr(f'({fcount} тем)', C.DIM)}  {clr(f'ID:{fid}', C.DIM)}")

    print()
    print(f"  {clr('Введите номера через запятую (1,3,5):', C.W)}")
    raw = input(f"  {clr('>', C.CY)} ").strip()

    try:
        indices = [int(x.strip()) for x in raw.split(",") if x.strip()]
        selected_ids = set()
        for idx in indices:
            if 1 <= idx <= len(forums):
                selected_ids.add(forums[idx - 1]["id"])
    except ValueError:
        log("Неверный ввод", "err")
        sys.exit(1)

    if not selected_ids:
        log("Ничего не выбрано", "err")
        sys.exit(1)

    selected_names = [f["title"] for f in forums if f["id"] in selected_ids]
    if choice == "2":
        log(f"Только разделы: {clr(', '.join(selected_names), C.Y)}")
        return ("include", selected_ids)
    else:
        log(f"Исключены разделы: {clr(', '.join(selected_names), C.R)}")
        return ("exclude", selected_ids)


def apply_filter(threads, filter_mode):
    if filter_mode is None:
        return threads

    mode, values = filter_mode
    if mode == "include":
        return [t for t in threads if t["forum_id"] in values]
    elif mode == "exclude":
        return [t for t in threads if t["forum_id"] not in values]
    elif mode == "ids":
        return [t for t in threads if t["id"] in values]


def open_threads(api, threads):
    ok = 0
    fail = 0
    total = len(threads)

    separator()
    log(f"Открытие {clr(str(total), C.W)} тем...")
    separator()

    for i, t in enumerate(threads, 1):
        tid = t["id"]
        title = t["title"]
        tag = f"[{i}/{total}]"

        result = api.open_thread(tid)
        if result:
            ok += 1
            print(f"  {clr(tag, C.DIM)}  {clr('[+]', C.G)} {title[:55]}")
        else:
            fail += 1
            print(f"  {clr(tag, C.DIM)}  {clr('[-]', C.R)} {title[:55]}")

    return ok, fail


def main():
    if sys.platform == "win32":
        os.system("color")

    print_banner()
    token = get_token()
    print()
    separator()

    api = LolzAPI(token)

    log("Проверка токена...")
    me = api.get_me()
    if not me:
        log("Авторизация провалена", "err")
        sys.exit(1)

    user = me.get("user", {})
    username = user.get("username", "?")
    user_id = user.get("user_id", "?")
    log(f"Авторизован: {clr(username, C.G + C.BOLD)}  (ID: {user_id})", "ok")
    separator()
    print()

    closed = fetch_closed_threads(api)

    if not closed:
        print()
        log("Закрытых тем не найдено", "ok")
        return

    editable = [t for t in closed if t.get("can_edit")]
    locked   = [t for t in closed if not t.get("can_edit")]

    if locked:
        print()
        log(f"Без прав на открытие: {clr(str(len(locked)), C.R)} тем (пропущены)")

    if not editable:
        print()
        log("Нет тем с правами на редактирование", "warn")
        return

    forums = get_unique_forums(editable)
    filter_mode = select_filter_mode(forums, len(editable))
    filtered = apply_filter(editable, filter_mode)

    if not filtered:
        print()
        log("После фильтрации не осталось тем", "warn")
        return

    print()
    separator()
    log(f"К открытию: {clr(str(len(filtered)), C.Y)} тем")
    print()
    for i, t in enumerate(filtered, 1):
        tid = t['id']
        fname = t['forum_title'][:20]
        print(f"    {clr(f'{i:>3}.', C.DIM)}  {clr(t['title'][:40], C.Y)}  {clr(f'[{fname}]', C.DIM)}  {clr(f'#{tid}', C.DIM)}")

    print()
    separator()
    confirm = input(f"  Открыть {clr(str(len(filtered)), C.W)} тем? (y/n): ").strip().lower()

    if confirm not in ("y", "yes", "д", "да"):
        log("Отмена", "warn")
        return

    print()

    ok, fail = open_threads(api, filtered)

    print()
    separator()
    log(f"Результат:", "info")
    log(f"  Открыто:  {clr(str(ok), C.G)}", "ok")
    if fail > 0:
        log(f"  Ошибок:   {clr(str(fail), C.R)}", "err")
    log(f"  Всего:    {clr(str(len(filtered)), C.W)}")
    separator()

    if fail == 0:
        log("Все темы успешно открыты", "ok")
    else:
        log(f"Не удалось открыть {fail} тем", "warn")
    print()


if __name__ == "__main__":
    main()
