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

RU_DOMAIN_SUFFIXES: list[str] = [
    "ru", "xn--p1ai",
    "vk.com", "vk.ru", "vkontakte.ru",
    "yandex.ru", "yandex.net", "yandex.com", "ya.ru", "yastatic.net",
    "mail.ru", "list.ru", "inbox.ru", "bk.ru",
    "ok.ru", "odnoklassniki.ru",
    "sber.ru", "sberbank.ru", "sbp.ru",
    "gosuslugi.ru", "mos.ru", "nalog.gov.ru",
    "ozon.ru", "wildberries.ru", "wb.ru",
    "avito.ru", "cian.ru", "hh.ru",
    "rbc.ru", "kommersant.ru", "ria.ru", "tass.ru", "interfax.ru",
    "lenta.ru", "gazeta.ru", "meduza.io",
    "1tv.ru", "russia.tv", "ntv.ru", "rt.com",
    "rambler.ru", "auto.ru", "drom.ru",
    "2gis.ru", "2gis.com",
    "kaspersky.ru", "drweb.ru",
    "beeline.ru", "mts.ru", "megafon.ru", "tele2.ru", "rostelecom.ru",
    "raiffeisen.ru", "tinkoff.ru", "alfabank.ru", "vtb.ru", "gazprombank.ru",
    "kinopoisk.ru", "ivi.ru", "okko.tv", "more.tv", "premier.one",
    "lamoda.ru", "dns-shop.ru", "mvideo.ru", "eldorado.ru", "citilink.ru",
    "telegram.org", "t.me",
]
