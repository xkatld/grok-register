import base64
import os
import select
import socket
import socketserver
import ssl
import threading
import urllib.parse

_tls = threading.local()

def set_runtime_proxy(proxy):
    value = str(proxy or "").strip()
    _tls.proxy = value or None

def get_runtime_proxy():
    return getattr(_tls, "proxy", None)

def resolve_proxy(explicit=None):
    for candidate in (
        str(explicit or "").strip(),
        str(get_runtime_proxy() or "").strip(),
        str(os.environ.get("https_proxy") or "").strip(),
        str(os.environ.get("HTTPS_PROXY") or "").strip(),
        str(os.environ.get("http_proxy") or "").strip(),
        str(os.environ.get("HTTP_PROXY") or "").strip(),
    ):
        if candidate:
            return candidate
    return ""

def _parse_proxy(proxy):
    raw = str(proxy or "").strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = "socks5://" + raw
    try:
        return urllib.parse.urlsplit(raw)
    except Exception:
        return None

def _safe_port(parsed):
    try:
        return parsed.port
    except Exception:
        return None

def _has_proxy_auth(proxy):
    parsed = _parse_proxy(proxy)
    return bool(parsed and parsed.hostname)

def _recv_until_headers(sock, timeout=20, limit=65536):
    sock.settimeout(timeout)
    data = b""
    while b"\r\n\r\n" not in data and len(data) < limit:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    return data

def _relay(left, right, timeout=90):
    left.settimeout(timeout)
    right.settimeout(timeout)
    sockets = [left, right]
    while True:
        readable, _, _ = select.select(sockets, [], [], timeout)
        if not readable:
            return
        for sock in readable:
            data = sock.recv(65536)
            if not data:
                return
            peer = right if sock is left else left
            peer.sendall(data)

class _BridgeServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

class _BridgeHandler(socketserver.BaseRequestHandler):
    def handle(self):
        bridge = self.server.bridge
        upstream = None
        try:
            initial = _recv_until_headers(self.request, timeout=bridge.timeout)
            if not initial:
                return
            first_line = initial.split(b"\r\n", 1)[0].decode("latin1", "ignore")
            if first_line.upper().startswith("CONNECT "):
                target = first_line.split()[1]
                if ":" in target:
                    target_host, target_port_str = target.rsplit(":", 1)
                    target_port = int(target_port_str)
                else:
                    target_host = target
                    target_port = 80
                upstream = bridge.open_upstream(target_host, target_port)
                self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                _relay(self.request, upstream, timeout=bridge.relay_timeout)
                return
            else:
                lines = initial.split(b"\r\n")
                first_parts = lines[0].decode("latin1", "ignore").split()
                if len(first_parts) >= 2:
                    url_parsed = urllib.parse.urlsplit(first_parts[1])
                    target_host = url_parsed.hostname or "127.0.0.1"
                    target_port = url_parsed.port or 80
                    upstream = bridge.open_upstream(target_host, target_port)
                    upstream.sendall(initial)
                    _relay(self.request, upstream, timeout=bridge.relay_timeout)
        except Exception:
            return
        finally:
            if upstream is not None:
                try:
                    upstream.close()
                except Exception:
                    pass

class LocalAuthProxyBridge(object):
    def __init__(self, proxy_url):
        parsed = _parse_proxy(proxy_url)
        if not parsed or not parsed.hostname:
            raise ValueError("proxy URL is invalid")
        scheme = (parsed.scheme or "socks5").lower()
        self.upstream_scheme = scheme
        self.upstream_host = parsed.hostname
        self.upstream_port = _safe_port(parsed) or 1080
        self.username = urllib.parse.unquote(parsed.username or "")
        self.password = urllib.parse.unquote(parsed.password or "")
        raw_auth = ("%s:%s" % (self.username, self.password)).encode("utf-8")
        self.auth_header = base64.b64encode(raw_auth).decode("ascii") if (self.username or self.password) else ""
        self.timeout = 20
        self.relay_timeout = 90
        self.server = None
        self.thread = None
        self.local_proxy = ""

    def open_upstream(self, target_host, target_port):
        if self.upstream_scheme in ("socks5", "socks5h"):
            sock = socket.create_connection((self.upstream_host, self.upstream_port), timeout=self.timeout)
            if self.username or self.password:
                sock.sendall(b"\x05\x02\x00\x02")
            else:
                sock.sendall(b"\x05\x01\x00")
            resp = sock.recv(2)
            if len(resp) < 2 or resp[0] != 5:
                sock.close()
                raise ValueError("socks5 handshake failed")
            method = resp[1]
            if method == 2:
                u_bytes = self.username.encode("utf-8")
                p_bytes = self.password.encode("utf-8")
                auth_req = b"\x01" + bytes([len(u_bytes)]) + u_bytes + bytes([len(p_bytes)]) + p_bytes
                sock.sendall(auth_req)
                auth_resp = sock.recv(2)
                if len(auth_resp) < 2 or auth_resp[1] != 0:
                    sock.close()
                    raise ValueError("socks5 auth failed")
            elif method != 0:
                sock.close()
                raise ValueError("socks5 auth method not supported")
            
            host_bytes = target_host.encode("utf-8")
            req = b"\x05\x01\x00\x03" + bytes([len(host_bytes)]) + host_bytes + target_port.to_bytes(2, "big")
            sock.sendall(req)
            conn_resp = sock.recv(10)
            if len(conn_resp) < 4 or conn_resp[1] != 0:
                sock.close()
                raise ValueError("socks5 connect failed")
            return sock
        else:
            sock = socket.create_connection((self.upstream_host, self.upstream_port), timeout=self.timeout)
            if self.upstream_scheme == "https":
                context = ssl.create_default_context()
                sock = context.wrap_socket(sock, server_hostname=self.upstream_host)
            sock.settimeout(self.timeout)
            return sock

    def start(self):
        self.server = _BridgeServer(("127.0.0.1", 0), _BridgeHandler)
        self.server.bridge = self
        port = self.server.server_address[1]
        self.local_proxy = "http://127.0.0.1:%s" % port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self.local_proxy

    def stop(self):
        if self.server is not None:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:
                pass
        self.server = None
        self.thread = None
        self.local_proxy = ""

def proxy_for_chromium(proxy):
    raw = str(proxy or "").strip()
    if not raw:
        return ""
    parsed = _parse_proxy(raw)
    if not parsed or not parsed.hostname:
        return ""
    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = "[%s]" % host
    port = _safe_port(parsed) or 1080
    scheme = parsed.scheme or "socks5"
    return "%s://%s:%s" % (scheme, host, port)

def prepare_chromium_proxy(proxy, log=None):
    logger = log or (lambda message: None)
    raw = str(proxy or "").strip()
    if not raw:
        return "", None
    bridge = LocalAuthProxyBridge(raw)
    local_proxy = bridge.start()
    logger("started authenticated proxy bridge: %s" % local_proxy)
    return local_proxy, bridge

def proxy_log_label(proxy):
    raw = str(proxy or "").strip()
    if not raw:
        return ""
    parsed = _parse_proxy(raw)
    if not parsed:
        return "(proxy)"
    host = parsed.hostname or "?"
    port = _safe_port(parsed)
    auth = "user:***@" if parsed.username else ""
    suffix = ":%s" % port if port else ""
    return "%s://%s%s%s" % (parsed.scheme or "socks5", auth, host, suffix)

