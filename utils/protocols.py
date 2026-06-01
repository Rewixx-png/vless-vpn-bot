SUPPORTED_SCHEMES: frozenset[str] = frozenset(
    {"vless", "vmess", "trojan", "ss", "ssr", "hysteria2", "hy2", "tuic"}
)

ACTIVE_SCHEMES: frozenset[str] = frozenset(
    {"vless", "trojan", "hy2", "hysteria2", "tuic"}
)

RENAMED_FRAGMENT_SCHEMES: frozenset[str] = frozenset({"hy2", "hysteria2", "tuic"})
BOTH_PROTOCOL_FILTER_VALUE = "vless,hy2,hysteria2,tuic"
PROTOCOL_PREFIXES: tuple[str, ...] = tuple(f"{scheme}://" for scheme in ACTIVE_SCHEMES)
ACTIVE_PROTOCOL_PATTERN = r"(?:vless|trojan|hy2|hysteria2|tuic)"
