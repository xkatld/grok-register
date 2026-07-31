"""提供共享的 HTTP 请求、代理处理和 Chromium 启动参数。"""
import os
import random
import re
import time
import urllib.parse

from DrissionPage import ChromiumOptions
from curl_cffi import requests
from cpa_xai.proxyutil import (
    LocalAuthProxyBridge,
    prepare_chromium_proxy,
    proxy_for_chromium,
)


_config = {}
_extension_path = ""
_active_proxy = ""
_proxy_pool = []
_pool_index = 0
_proxy_rotation = "round_robin"  # "round_robin" or "random"

# 代理测试与过滤状态
_tested_good = set()
_tested_bad = set()


def configure_runtime(config_ref, extension_path=""):
    global _config, _extension_path
    _config = config_ref
    _extension_path = str(extension_path or "")
    _refresh_proxy_pool()


def parse_proxy_lines(value):
    """解析用户输入的多行/逗号/分号分隔的代理文本，返回列表。"""
    return _parse_proxy_list(value)


def refresh_proxy_pool():
    """公开刷新代理池（供 GUI/CLI 在修改 proxy 配置后调用）。"""
    _refresh_proxy_pool()


def _refresh_proxy_pool():
    global _proxy_pool, _pool_index
    raw = str(_config.get("proxy", "") or "")
    _proxy_pool = _parse_proxy_list(raw)
    _pool_index = 0


def _parse_proxy_list(value):
    if not value:
        return []
    text = str(value).strip()
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        p = line.strip()
        if p:
            if "://" not in p:
                p = "socks5://" + p
            cleaned.append(p)
    return cleaned


def get_proxy_rotation_mode():
    mode = str(_config.get("proxy_rotation", "round_robin") or "round_robin").strip().lower()
    return "random" if mode == "random" else "round_robin"


def get_proxy_pool():
    return list(_proxy_pool)


def get_proxy_only_tested():
    return bool(_config.get("proxy_only_tested", False))


def get_tested_good():
    return set(_tested_good)


def get_tested_bad():
    return set(_tested_bad)


def clear_proxy_test_results():
    """清空已记录的代理测试结果（好/坏）。"""
    global _tested_good, _tested_bad
    _tested_good.clear()
    _tested_bad.clear()


def mark_proxy_good(proxy):
    p = str(proxy or "").strip()
    if not p:
        return
    _tested_bad.discard(p)
    _tested_good.add(p)


def mark_proxy_bad(proxy):
    p = str(proxy or "").strip()
    if not p:
        return
    _tested_good.discard(p)
    _tested_bad.add(p)


def handle_proxy_failure(reason="", log_callback=None):
    """便捷封装：标记当前代理为坏，并建议调用方在失败后触发 rotate。
    实际跳过坏代理发生在下一次 rotate_proxy_for_next() 或 pick_next_proxy()。
    """
    mark_current_proxy_bad(reason, log_callback)


def mark_current_proxy_bad(reason="", log_callback=None):
    p = get_active_proxy() or get_configured_proxy()
    if p:
        mark_proxy_bad(p)
        if log_callback:
            log_callback(f"[!] 当前代理标记为坏: {_proxy_label(p)} ({reason})")


def is_proxy_tested_good(proxy):
    p = str(proxy or "").strip()
    return (p in _tested_good) and (p not in _tested_bad)


def get_effective_proxy_pool():
    """返回当前用于轮换的有效代理列表。
    - 若开启 proxy_only_tested：仅返回测试通过（_tested_good 且不在 bad）的。
    - 否则：返回全池，但优先排除已知的 _tested_bad；若排除后为空则回退全池。
    """
    base = list(_proxy_pool)
    if not base:
        return []
    only_tested = get_proxy_only_tested()
    if only_tested:
        good = [p for p in base if (p in _tested_good) and (p not in _tested_bad)]
        return good  # 可能为空，调用方应决定是否直连或报错
    else:
        filtered = [p for p in base if p not in _tested_bad]
        return filtered if filtered else base


def pick_next_proxy():
    """根据配置的轮换策略从 effective pool 选取下一个（会遵守仅测试通过 / 排除坏代理 规则）。"""
    global _pool_index
    pool = get_effective_proxy_pool()
    if not pool:
        return ""
    mode = get_proxy_rotation_mode()
    if mode == "random":
        return random.choice(pool)
    # round robin over the (possibly filtered) pool
    p = pool[_pool_index % len(pool)]
    _pool_index += 1
    return p


def set_active_proxy(proxy):
    global _active_proxy
    _active_proxy = str(proxy or "").strip()


def get_active_proxy():
    return _active_proxy


def rotate_proxy_for_next(log_callback=None):
    """为下一个账号选取代理并设为 active。返回选取的代理字符串。
    会自动跳过已知的坏代理；如果启用仅测试通过，则只从好代理中选。
    """
    p = pick_next_proxy()
    # 若 pick 为空（例如 only_tested 开启但无好代理），尝试直接从有效池取一个
    if not p:
        eff = get_effective_proxy_pool()
        if eff:
            p = eff[0]
    set_active_proxy(p)
    if log_callback and p:
        label = _proxy_label(p)
        only = "（仅测试通过）" if get_proxy_only_tested() else ""
        log_callback(f"[*] 切换代理: {label} {only}")
    elif log_callback:
        log_callback("[*] 无可用代理，使用直连")
    return p


def _proxy_label(proxy):
    raw = str(proxy or "").strip()
    if not raw:
        return "(none)"
    try:
        parsed = urllib.parse.urlsplit(raw if "://" in raw else "http://" + raw)
        auth = "user:***@" if parsed.username else ""
        host = parsed.hostname or "?"
        port = parsed.port
        suffix = f":{port}" if port else ""
        scheme = (parsed.scheme or "http").lower()
        return f"{scheme}://{auth}{host}{suffix}"
    except Exception:
        return raw[:60]


def get_configured_proxy():
    """向后兼容：优先返回当前激活的代理。
    当开启 proxy_only_tested 时，优先返回测试通过的好代理；
    若没有好代理则返回空串（直连），避免使用未验证或已坏的代理。
    """
    only = get_proxy_only_tested()

    def _pick_good_active():
        # 尝试用当前 active（如果它是好代理）
        act = _active_proxy.strip() if _active_proxy else ""
        if act and is_proxy_tested_good(act):
            return act
        # 否则从有效好代理中挑一个并激活
        eff = get_effective_proxy_pool()
        if eff:
            chosen = eff[0]
            set_active_proxy(chosen)
            return chosen
        return ""

    if only:
        chosen = _pick_good_active()
        if chosen:
            return chosen
        # 没有好代理：返回空，调用方将直连
        return ""

    # 非仅测试模式：正常返回当前 active 或池首项
    if _active_proxy:
        return _active_proxy
    if _proxy_pool:
        return _proxy_pool[0]
    return str(_config.get("proxy", "") or "").strip()


def get_proxies():
    proxy = get_configured_proxy()
    return {"http": proxy, "https": proxy} if proxy else {}


def _parse_proxy_url(proxy):
    raw = str(proxy or "").strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = "http://" + raw
    try:
        return urllib.parse.urlsplit(raw)
    except Exception:
        return None


def _safe_proxy_port(parsed):
    try:
        return parsed.port
    except Exception:
        return None


def _proxy_has_auth(proxy):
    parsed = _parse_proxy_url(proxy)
    return bool(parsed and parsed.hostname and (parsed.username is not None or parsed.password is not None))


def _strip_proxy_auth(proxy):
    raw = str(proxy or "").strip()
    parsed = _parse_proxy_url(raw)
    if not parsed or not parsed.hostname:
        return raw
    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = "[%s]" % host
    port = _safe_proxy_port(parsed)
    netloc = "%s:%s" % (host, port) if port else host
    stripped = urllib.parse.urlunsplit((parsed.scheme or "http", netloc, parsed.path, parsed.query, parsed.fragment))
    return stripped.split("://", 1)[1] if "://" not in raw else stripped


def _proxy_endpoint_terms(proxy=None):
    parsed = _parse_proxy_url(proxy or get_configured_proxy())
    if not parsed or not parsed.hostname:
        return []
    terms = [parsed.hostname]
    port = _safe_proxy_port(parsed)
    if port:
        terms.extend(["%s:%s" % (parsed.hostname, port), "port %s" % port])
    return [item.lower() for item in terms if item]


def is_proxy_connection_error(exc):
    if not get_configured_proxy():
        return False
    err = str(exc or "").lower()
    if not err:
        return False
    if any(item in err for item in ("proxy", "tunnel", "socks")):
        return True
    markers = (
        "could not connect", "failed to connect", "connection refused",
        "connection reset", "connect error", "timed out", "timeout",
    )
    if any(item in err for item in markers):
        terms = _proxy_endpoint_terms()
        return not terms or any(term in err for term in terms)
    return False


def page_has_proxy_error(page_obj):
    try:
        url = str(getattr(page_obj, "url", "") or "")
        title = str(page_obj.run_js("return document.title || ''") or "")
        body = str(page_obj.run_js("return document.body ? document.body.innerText.slice(0, 2000) : ''") or "")
    except Exception:
        return False
    text = "%s\n%s\n%s" % (url, title, body)
    text = text.lower()
    return any(marker in text for marker in (
        "err_proxy", "proxy connection failed", "proxy server",
        "proxy authentication", "tunnel connection failed",
        "无法连接到代理服务器", "代理服务器",
    ))


def prepare_browser_proxy(use_proxy=True, log_callback=None):
    proxy = get_configured_proxy()
    if not use_proxy or not proxy:
        return "", None
    logger = None
    if log_callback:
        logger = lambda message: log_callback("[*] 已为 Chromium 启动本地代理桥: %s" % message.split(": ", 1)[-1]) if "started authenticated proxy bridge" in message else log_callback(message)
    return prepare_chromium_proxy(proxy, log=logger)


def apply_browser_proxy_option(options, proxy):
    if not proxy:
        return
    if hasattr(options, "set_proxy"):
        try:
            options.set_proxy(proxy)
            return
        except Exception:
            pass
    if not hasattr(options, "set_argument"):
        raise AttributeError("当前 DrissionPage ChromiumOptions 不支持设置浏览器代理")
    try:
        options.set_argument("--proxy-server=%s" % proxy)
    except TypeError:
        options.set_argument("--proxy-server", proxy)


def create_browser_options(browser_proxy="", extension_path=None):
    options = ChromiumOptions()
    options.auto_port()
    options.set_timeouts(base=1)
    apply_browser_proxy_option(options, browser_proxy)

    for flag in (
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--no-zygote",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
    ):
        try:
            options.set_argument(flag)
        except Exception:
            pass

    for candidate in (
        "/usr/bin/google-chrome-stable",
        "/usr/bin/google-chrome",
        "/usr/bin/vivaldi-stable",
        "/usr/bin/vivaldi",
        "/usr/bin/brave-browser",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
    ):
        if os.path.isfile(candidate):
            try:
                options.set_browser_path(candidate)
            except Exception:
                pass
            break

    effective_extension = _extension_path if extension_path is None else str(extension_path or "")
    if effective_extension and os.path.exists(effective_extension):
        options.add_extension(effective_extension)
    return options


def _build_request_kwargs(**kwargs):
    request_kwargs = dict(kwargs)
    proxies = request_kwargs.pop("proxies", None)
    if proxies is None:
        proxies = get_proxies()
    if proxies:
        request_kwargs["proxies"] = proxies
    request_kwargs.setdefault("timeout", 15)
    return request_kwargs


def http_get(url, **kwargs):
    request_kwargs = _build_request_kwargs(**kwargs)
    try:
        return requests.get(url, **request_kwargs)
    except Exception as exc:
        if is_proxy_connection_error(exc):
            # 代理失败，标记当前代理为坏
            try:
                mark_current_proxy_bad("http_get 代理连接失败")
            except Exception:
                pass
            direct = dict(request_kwargs)
            direct.pop("proxies", None)
            return requests.get(url, **direct)
        raise


def http_post(url, **kwargs):
    request_kwargs = _build_request_kwargs(**kwargs)
    try:
        return requests.post(url, **request_kwargs)
    except Exception as exc:
        if is_proxy_connection_error(exc):
            try:
                mark_current_proxy_bad("http_post 代理连接失败")
            except Exception:
                pass
            direct = dict(request_kwargs)
            direct.pop("proxies", None)
            return requests.post(url, **direct)
        raise


# ===================== 代理测试 =====================

def _normalize_proxy_for_requests(proxy):
    """为 curl_cffi 构造 proxies 字典。支持 socks5:// 等。"""
    if not proxy:
        return {}
    p = str(proxy).strip()
    if not p:
        return {}
    return {"http": p, "https": p}


def test_proxy(proxy, timeout=12, target="https://www.google.com", log_callback=None):
    """测试单个代理的连通性。
    返回: {"ok": bool, "latency_ms": int|None, "error": str|None, "proxy": str}
    成功会标记为 good，失败标记为 bad。
    """
    p = str(proxy or "").strip()
    start = time.time()
    try:
        proxies = _normalize_proxy_for_requests(p)
        r = requests.get(target, proxies=proxies if proxies else None, timeout=timeout, impersonate="chrome120")
        latency = int((time.time() - start) * 1000)
        if 200 <= r.status_code < 400:
            mark_proxy_good(p)
            if log_callback:
                log_callback(f"[ProxyTest] {_proxy_label(p)}: OK {latency}ms")
            return {"ok": True, "latency_ms": latency, "error": None, "proxy": p}
        else:
            err = f"HTTP {r.status_code}"
            mark_proxy_bad(p)
            if log_callback:
                log_callback(f"[ProxyTest] {_proxy_label(p)}: FAIL {err}")
            return {"ok": False, "latency_ms": latency, "error": err, "proxy": p}
    except Exception as e:
        latency = int((time.time() - start) * 1000)
        msg = f"{type(e).__name__}: {e}"
        mark_proxy_bad(p)
        if log_callback:
            log_callback(f"[ProxyTest] {_proxy_label(p)}: FAIL {msg}")
        return {"ok": False, "latency_ms": latency, "error": msg, "proxy": p}


def test_proxies(proxies, timeout=12, target="https://www.google.com", log_callback=None, max_workers=8):
    """批量测试代理列表。返回结果列表（顺序与输入一致）。"""
    results = []
    # 简单串行 + 轻微并发控制；避免同时开太多连接导致本地资源问题
    # 这里用简单线程池
    from concurrent.futures import ThreadPoolExecutor, as_completed
    work = list(proxies or [])
    if not work:
        return results
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(work)))) as ex:
        fut_map = {ex.submit(test_proxy, p, timeout=timeout, target=target, log_callback=log_callback): p for p in work}
        # 保持输入顺序收集
        ordered = {p: None for p in work}
        for fut in as_completed(fut_map):
            res = fut.result()
            ordered[fut_map[fut]] = res
        for p in work:
            if ordered[p] is not None:
                results.append(ordered[p])
    return results


def test_current_pool(timeout=12, target="https://www.google.com", log_callback=None):
    """测试当前配置的代理池。"""
    pool = get_proxy_pool()
    return test_proxies(pool, timeout=timeout, target=target, log_callback=log_callback)


def apply_proxy_test_filter(results, log_callback=None):
    """根据测试结果批量标记好/坏代理，并刷新有效池。
    results: list of {"ok": bool, "proxy": str, ...}
    """
    for r in (results or []):
        p = str((r or {}).get("proxy") or "").strip()
        if not p:
            continue
        if r.get("ok"):
            mark_proxy_good(p)
        else:
            mark_proxy_bad(p)
    if log_callback:
        log_callback(f"[ProxyFilter] 好代理: {len(_tested_good)} | 坏代理: {len(_tested_bad)} | 仅测试通过: {'开' if get_proxy_only_tested() else '关'}")
    # 刷新一次索引，确保下次轮换从过滤后的集合开始
    global _pool_index
    _pool_index = 0
