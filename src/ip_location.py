"""基于 ip2region XDB 的离线 IPv4/IPv6 归属地查询。"""
import ipaddress
import logging
from functools import lru_cache
from importlib import import_module
from pathlib import Path
from threading import Lock

DATA_DIR = Path(__file__).resolve().parent / "ip2region-master" / "data"
DB_PATHS = {version: DATA_DIR / f"ip2region_v{version}.xdb" for version in (4, 6)}
_lock = Lock()
_searchers = {}


def _address(ip):
    address = ipaddress.ip_address(ip)
    return getattr(address, "ipv4_mapped", None) or address


def is_internal_ip(ip):
    try:
        address = _address(ip)
        return address.is_loopback or address.is_private or address.is_link_local
    except (ValueError, TypeError):
        return False


def _get_searcher(version):
    with _lock:
        if version not in _searchers:
            try:
                util = import_module("src.ip2region-master._vendor.ip2region.util")
                searcher = import_module("src.ip2region-master._vendor.ip2region.searcher")
                path = str(DB_PATHS[version])
                util.verify_from_file(path)
                header = util.load_header_from_file(path)
                db_version = util.version_from_header(header)
                content = util.load_content_from_file(path)
                _searchers[version] = searcher.new_with_buffer(db_version, content)
            except Exception:
                logging.getLogger(__name__).exception("无法加载 IPv%s 归属地数据库", version)
                _searchers[version] = None
        return _searchers[version]


def _parse_region(raw, version):
    parts = raw.split("|")
    if version == 6:
        parts = [parts[i] if len(parts) > i else "" for i in (1, 2, 3, 5)]
    result = []
    for index in range(4):
        value = parts[index].strip() if len(parts) > index else ""
        result.append(value if value not in ("", "0") else "")
    return tuple(result)


@lru_cache(maxsize=4096)
def query_ip_location(ip):
    try:
        address = _address(ip)
    except (ValueError, TypeError):
        return {"country": "未知", "region": "", "city": "", "isp": ""}
    if is_internal_ip(str(address)):
        return {"country": "本机/内网", "region": "", "city": "", "isp": ""}
    searcher = _get_searcher(address.version)
    if searcher:
        try:
            values = _parse_region(searcher.search(str(address)), address.version)
            return dict(zip(("country", "region", "city", "isp"), values))
        except Exception:
            logging.getLogger(__name__).warning("IP 归属地查询失败: %s", ip, exc_info=True)
    return {"country": "未知", "region": "", "city": "", "isp": ""}


def format_ip_location(ip):
    result = query_ip_location(ip)
    values = []
    for key in ("country", "region", "city", "isp"):
        value = result.get(key, "")
        if value and value not in values:
            values.append(value)
    return " ".join(values) or "未知"


def format_ip_city(ip):
    result = query_ip_location(ip)
    for key in ("city", "region", "country"):
        value = result.get(key, "")
        if value:
            return value
    return "未知"
