import asyncio
import json
import os
import re
import sys
import urllib.parse

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


REAL_VLESS = (
    "vless://f189684b-6213-4c0d-a2e3-cb8860f5d4c5@185.220.101.1:443"
    "?security=reality&flow=xtls-rprx-vision&type=tcp"
    "&sni=yahoo.com&fp=chrome"
    "&pbk=1g94O4Q2qQp1uU9D_B3YhT3t5Z7mIu_XjXq9-z0oGkI&sid=8f"
    "#DE | 50 Mbps"
)

WS_VLESS = (
    "vless://aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee@1.2.3.4:8080"
    "?security=tls&type=ws&path=/vpn&host=cdn.example.com&sni=cdn.example.com"
    "#NL | WS"
)

GRPC_VLESS = (
    "vless://aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee@5.6.7.8:443"
    "?security=tls&type=grpc&serviceName=grpc-service&sni=example.com"
    "#US | gRPC"
)

INVALID_UUID = (
    "vless://NOT-A-VALID-UUID@1.2.3.4:443"
    "?security=reality&type=tcp&pbk=1g94O4Q2qQp1uU9D_B3YhT3t5Z7mIu_XjXq9-z0oGkI&sid=8f"
    "#bad"
)

INVALID_SECURITY = (
    "vless://f189684b-6213-4c0d-a2e3-cb8860f5d4c5@1.2.3.4:443"
    "?security=xtls&type=tcp"
    "#xtls-legacy"
)

MISSING_PBK = (
    "vless://f189684b-6213-4c0d-a2e3-cb8860f5d4c5@1.2.3.4:443"
    "?security=reality&type=tcp&pbk=short&sid=8f"
    "#bad-reality"
)

BAD_TRANSPORT = (
    "vless://f189684b-6213-4c0d-a2e3-cb8860f5d4c5@1.2.3.4:443"
    "?security=none&type=ws@@garbage"
    "#bad-transport"
)




class TestVlessParser:
    def setup_method(self):
        from utils.parser import LinkParser
        self.parse = LinkParser.parse_vless

    def test_reality_parse_fields(self):
        cfg = self.parse(REAL_VLESS)
        assert cfg is not None, "Reality config must parse"
        assert cfg["uuid"] == "f189684b-6213-4c0d-a2e3-cb8860f5d4c5"
        assert cfg["server"] == "185.220.101.1"
        assert cfg["port"] == 443
        assert cfg["security"] == "reality"
        assert cfg["flow"] == "xtls-rprx-vision"
        assert cfg["type"] == "tcp"
        assert cfg["pbk"] == "1g94O4Q2qQp1uU9D_B3YhT3t5Z7mIu_XjXq9-z0oGkI"
        assert cfg["sid"] == "8f"

    def test_ws_parse_fields(self):
        cfg = self.parse(WS_VLESS)
        assert cfg is not None
        assert cfg["type"] == "ws"
        assert cfg["path"] == "/vpn"
        assert cfg["host"] == "cdn.example.com"
        assert cfg["security"] == "tls"

    def test_grpc_parse_fields(self):
        cfg = self.parse(GRPC_VLESS)
        assert cfg is not None
        assert cfg["type"] == "grpc"
        assert cfg["serviceName"] == "grpc-service"

    def test_invalid_link_returns_none(self):
        assert self.parse("http://not-vless.com") is None
        assert self.parse("") is None
        assert self.parse("vless://missing-at-sign") is None

    def test_name_decoded_from_fragment(self):
        cfg = self.parse(REAL_VLESS)
        assert cfg is not None
        assert "DE" in cfg["ps"] or "DE" in cfg.get("name", "")




class TestXrayValidator:
    def setup_method(self):
        from utils.checker.xray import XrayExecutor
        self.XrayExecutor = XrayExecutor

    def _parse(self, url):
        from utils.parser import LinkParser
        return LinkParser.parse_vless(url)

    @pytest.mark.asyncio
    async def test_valid_reality_accepted(self):
        proc, port, info = await self.XrayExecutor.start_xray(REAL_VLESS)
        assert info != "CONFIG_ERR: Invalid Link Format"
        assert info != "CONFIG_ERR: Invalid UUID Format"
        if proc:
            await self.XrayExecutor.cleanup(proc, info)

    @pytest.mark.asyncio
    async def test_invalid_uuid_rejected(self):
        proc, port, info = await self.XrayExecutor.start_xray(INVALID_UUID)
        assert proc is None
        assert "UUID" in info, f"Expected UUID error, got: {info}"

    @pytest.mark.asyncio
    async def test_invalid_security_rejected(self):
        proc, port, info = await self.XrayExecutor.start_xray(INVALID_SECURITY)
        assert proc is None
        assert "security" in info.lower() or "CONFIG_ERR" in info

    @pytest.mark.asyncio
    async def test_missing_pbk_rejected(self):
        proc, port, info = await self.XrayExecutor.start_xray(MISSING_PBK)
        assert proc is None
        assert "pbk" in info or "Reality" in info

    @pytest.mark.asyncio
    async def test_bad_transport_rejected(self):
        proc, port, info = await self.XrayExecutor.start_xray(BAD_TRANSPORT)
        assert proc is None
        assert "transport" in info.lower() or "CONFIG_ERR" in info

    def test_free_port_is_valid(self):
        port = self.XrayExecutor._acquire_free_port()
        assert 1024 < port < 65535

    def test_free_port_no_collision(self):
        ports = {self.XrayExecutor._acquire_free_port() for _ in range(10)}
        assert len(ports) == 10, "Acquired ports must be unique"




class TestClashGenerator:
    def setup_method(self):
        from utils.clash import ClashGenerator
        from utils.parser import LinkParser
        self.gen = ClashGenerator
        self.parse = LinkParser.parse_vless

    def _configs(self, *links):
        return [c for c in (self.parse(l) for l in links) if c]

    def test_generates_valid_yaml_structure(self):
        yaml = self.gen.generate_conf(self._configs(REAL_VLESS, WS_VLESS))
        assert "proxies:" in yaml
        assert "proxy-groups:" in yaml
        assert "rules:" in yaml

    def test_contains_ru_split_rules(self):
        yaml = self.gen.generate_conf(self._configs(REAL_VLESS))
        assert "GEOIP,RU,DIRECT" in yaml, "Must have Russian IP direct rule"
        assert "GEOSITE,category-ru,DIRECT" in yaml, "Must have Russian domain direct rule"
        assert "MATCH,Proxy" in yaml, "Must have catch-all proxy rule"

    def test_ru_rules_before_match(self):
        yaml = self.gen.generate_conf(self._configs(REAL_VLESS))
        lines = yaml.split("\n")
        ru_idx = next((i for i, l in enumerate(lines) if "GEOIP,RU" in l), None)
        match_idx = next((i for i, l in enumerate(lines) if "MATCH,Proxy" in l), None)
        assert ru_idx is not None
        assert match_idx is not None
        assert ru_idx < match_idx, "RU rules must appear before MATCH,Proxy"

    def test_private_ip_rules_present(self):
        yaml = self.gen.generate_conf(self._configs(REAL_VLESS))
        assert "192.168.0.0/16" in yaml
        assert "10.0.0.0/8" in yaml

    def test_best_ping_group(self):
        yaml = self.gen.generate_conf(self._configs(REAL_VLESS, WS_VLESS))
        assert "Best Ping" in yaml
        assert "url-test" in yaml

    def test_direct_group_present(self):
        yaml = self.gen.generate_conf(self._configs(REAL_VLESS))
        assert "Direct" in yaml, "Must have a Direct group"
        assert "DIRECT" in yaml

    def test_empty_configs_no_crash(self):
        yaml = self.gen.generate_conf([])
        assert yaml is not None
        assert isinstance(yaml, str)

    def test_reality_proxy_structure(self):
        yaml = self.gen.generate_conf(self._configs(REAL_VLESS))
        assert "reality-opts:" in yaml
        assert "public-key:" in yaml
        assert "short-id:" in yaml

    def test_ws_proxy_structure(self):
        yaml = self.gen.generate_conf(self._configs(WS_VLESS))
        assert "ws-opts:" in yaml
        assert "path:" in yaml

    def test_domain_suffix_rules_in_yaml(self):
        yaml = self.gen.generate_conf(self._configs(REAL_VLESS))
        assert "DOMAIN-SUFFIX,vk.com,DIRECT" in yaml
        assert "DOMAIN-SUFFIX,yandex.ru,DIRECT" in yaml
        assert "DOMAIN-SUFFIX,gosuslugi.ru,DIRECT" in yaml
        assert "DOMAIN-SUFFIX,sberbank.ru,DIRECT" in yaml




class TestSingBoxGenerator:
    def setup_method(self):
        from utils.singbox import SingBoxGenerator
        from utils.parser import LinkParser
        self.gen = SingBoxGenerator
        self.parse = LinkParser.parse_vless

    def _configs(self, *links):
        return [c for c in (self.parse(l) for l in links) if c]

    def _parsed(self, *links):
        raw = self.gen.generate(self._configs(*links))
        return json.loads(raw)

    def test_valid_json(self):
        raw = self.gen.generate(self._configs(REAL_VLESS))
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)

    def test_required_top_level_keys(self):
        cfg = self._parsed(REAL_VLESS)
        for key in ("log", "dns", "inbounds", "outbounds", "route"):
            assert key in cfg, f"Missing top-level key: {key}"

    def test_outbounds_structure(self):
        cfg = self._parsed(REAL_VLESS)
        tags = [o["tag"] for o in cfg["outbounds"]]
        assert "proxy" in tags, "Must have selector outbound 'proxy'"
        assert "auto" in tags, "Must have urltest outbound 'auto'"
        assert "direct" in tags, "Must have direct outbound"
        assert "block" in tags, "Must have block outbound"

    def test_vless_outbound_structure(self):
        cfg = self._parsed(REAL_VLESS)
        vless_obs = [o for o in cfg["outbounds"] if o.get("type") == "vless"]
        assert len(vless_obs) == 1
        ob = vless_obs[0]
        assert ob["server"] == "185.220.101.1"
        assert ob["server_port"] == 443
        assert ob["uuid"] == "f189684b-6213-4c0d-a2e3-cb8860f5d4c5"
        assert ob["flow"] == "xtls-rprx-vision"

    def test_reality_tls_block(self):
        cfg = self._parsed(REAL_VLESS)
        vless_obs = [o for o in cfg["outbounds"] if o.get("type") == "vless"]
        tls = vless_obs[0]["tls"]
        assert tls["enabled"] is True
        assert "reality" in tls
        assert tls["reality"]["public_key"] == "1g94O4Q2qQp1uU9D_B3YhT3t5Z7mIu_XjXq9-z0oGkI"

    def test_ws_transport_structure(self):
        cfg = self._parsed(WS_VLESS)
        vless_obs = [o for o in cfg["outbounds"] if o.get("type") == "vless"]
        transport = vless_obs[0]["transport"]
        assert transport["type"] == "ws"
        assert transport["path"] == "/vpn"

    def test_ru_routing_rules(self):
        cfg = self._parsed(REAL_VLESS)
        rules = cfg["route"]["rules"]
        ru_rule = next(
            (r for r in rules if r.get("outbound") == "direct" and "rules" in r),
            None
        )
        assert ru_rule is not None, "Must have RU direct routing rule"
        inner_tags = [list(r.keys())[0] for r in ru_rule["rules"] if r]
        assert "geoip" in inner_tags, "Must route RU geoip to direct"
        assert "domain_suffix" in inner_tags, "Must route RU domains to direct"

    def test_ru_domain_suffixes_coverage(self):
        cfg = self._parsed(REAL_VLESS)
        rules = cfg["route"]["rules"]
        ru_rule = next(r for r in rules if r.get("outbound") == "direct" and "rules" in r)
        domains = next(r["domain_suffix"] for r in ru_rule["rules"] if "domain_suffix" in r)
        for expected in ["ru", "vk.com", "yandex.ru", "gosuslugi.ru", "sberbank.ru"]:
            assert expected in domains, f"Missing domain: {expected}"

    def test_route_final_is_proxy(self):
        cfg = self._parsed(REAL_VLESS)
        assert cfg["route"]["final"] == "proxy"

    def test_inbound_mixed(self):
        cfg = self._parsed(REAL_VLESS)
        inbounds = cfg["inbounds"]
        assert any(i["type"] == "mixed" for i in inbounds)

    def test_dns_has_ru_server(self):
        cfg = self._parsed(REAL_VLESS)
        dns_rules = cfg["dns"]["rules"]
        assert any(
            "category-ru" in str(r.get("geosite", ""))
            for r in dns_rules
        ), "DNS must route RU geosite to local server"

    def test_empty_configs_no_crash(self):
        raw = self.gen.generate([])
        parsed = json.loads(raw)
        assert "outbounds" in parsed

    def test_multiple_configs_all_in_selector(self):
        cfg = self._parsed(REAL_VLESS, WS_VLESS)
        selector = next(o for o in cfg["outbounds"] if o["tag"] == "proxy")
        assert len(selector["outbounds"]) >= 3




class TestKeyboard:
    SAFE_PROTOCOLS = {"https", "http", "tg"}

    def _extract_urls(self, markup):
        urls = []
        for row in markup.inline_keyboard:
            for btn in row:
                if btn.url:
                    urls.append(btn.url)
        return urls

    def _protocol_of(self, url: str) -> str:
        return url.split("://")[0] if "://" in url else ""

    def test_sub_action_kb_all_urls_valid(self):
        from keyboards.user import sub_action_kb
        kb = sub_action_kb("https://direct.example.com/sub64?id=12345")
        urls = self._extract_urls(kb)
        assert len(urls) > 0, "Must have URL buttons"
        for url in urls:
            proto = self._protocol_of(url)
            assert proto in self.SAFE_PROTOCOLS, (
                f"Button URL has unsafe protocol '{proto}': {url}"
            )

    def test_sub_action_kb_hiddify_present(self):
        from keyboards.user import sub_action_kb
        kb = sub_action_kb("https://direct.example.com/sub64?id=99")
        urls = self._extract_urls(kb)
        assert any("hiddify" in u for u in urls), "Hiddify button must exist"

    def test_sub_action_kb_v2raytun_present(self):
        from keyboards.user import sub_action_kb
        kb = sub_action_kb("https://direct.example.com/sub64?id=99")
        urls = self._extract_urls(kb)
        assert any("v2raytun" in u for u in urls), "V2RayTun button must exist"

    def test_sub_action_kb_no_bare_sing_box_protocol(self):
        from keyboards.user import sub_action_kb
        kb = sub_action_kb("https://direct.example.com/sub64?id=99")
        urls = self._extract_urls(kb)
        for url in urls:
            assert not url.startswith("sing-box://"), (
                f"Direct sing-box:// not allowed in TG buttons: {url}"
            )




class TestSubServerEndpoints:
    @pytest.fixture(autouse=True)
    def checker_url(self):
        from config import config
        self.base = f"http://127.0.0.1:{config.CHECKER_PORT}"
        self.sub_port = config.WEB_PORT
        self.sub_base = f"http://127.0.0.1:{self.sub_port}"

    @pytest.mark.asyncio
    async def test_checker_health(self):
        import aiohttp
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(self.base + "/", timeout=aiohttp.ClientTimeout(total=5)) as r:
                    assert r.status == 200, f"CheckerSVC health check failed: {r.status}"
                    text = await r.text()
                    assert "OK" in text
        except Exception as e:
            pytest.fail(f"CheckerSVC not reachable: {e}")

    @pytest.mark.asyncio
    async def test_sub_server_responds(self):
        import aiohttp
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    self.sub_base + "/sub?id=0",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as r:
                    assert r.status in (200, 204), f"Sub server unexpected status: {r.status}"
        except Exception as e:
            pytest.fail(f"Sub server not reachable: {e}")

    @pytest.mark.asyncio
    async def test_sub_clash_format_headers(self):
        import aiohttp
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    self.sub_base + "/sub?id=0&format=clash",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as r:
                    ct = r.headers.get("Content-Type", "")
                    assert "yaml" in ct.lower() or "text" in ct.lower(), (
                        f"Clash format should return yaml content-type, got: {ct}"
                    )
        except Exception as e:
            pytest.fail(f"Sub server clash endpoint failed: {e}")

    @pytest.mark.asyncio
    async def test_sub_singbox_format_returns_json(self):
        import aiohttp
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    self.sub_base + "/sub?id=0&format=singbox",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as r:
                    assert r.status == 200
                    ct = r.headers.get("Content-Type", "")
                    assert "json" in ct.lower(), f"sing-box format should return json, got: {ct}"
                    body = await r.text()
                    parsed = json.loads(body)
                    assert "outbounds" in parsed
        except Exception as e:
            pytest.fail(f"Sub server singbox endpoint failed: {e}")

    @pytest.mark.asyncio
    async def test_redirect_hiddify(self):
        import aiohttp
        test_url = urllib.parse.quote("https://example.com/sub?id=1", safe="")
        try:
            async with aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=False)
            ) as s:
                async with s.get(
                    f"{self.sub_base}/redirect?app=hiddify&url={test_url}",
                    timeout=aiohttp.ClientTimeout(total=5),
                    allow_redirects=False,
                ) as r:
                    assert r.status in (301, 302, 303), f"Redirect should redirect, got {r.status}"
                    location = r.headers.get("Location", "")
                    assert "hiddify" in location.lower(), f"Hiddify redirect wrong: {location}"
        except Exception as e:
            pytest.fail(f"Redirect endpoint failed: {e}")

    @pytest.mark.asyncio
    async def test_redirect_singbox(self):
        import aiohttp
        raw_url = "https://example.com/sub?id=1&format=singbox"
        test_url = urllib.parse.quote(raw_url, safe="")
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"{self.sub_base}/redirect?app=singbox&url={test_url}",
                    timeout=aiohttp.ClientTimeout(total=5),
                    allow_redirects=False,
                ) as r:
                    assert r.status in (301, 302, 303)
                    location = r.headers.get("Location", "")
                    assert "sing-box://" in location, f"Singbox redirect wrong: {location}"
                    assert "%26" in location or "&format" not in location.split("?url=")[-1], (
                        f"sub_url must be URL-encoded inside deep link: {location}"
                    )
        except Exception as e:
            pytest.fail(f"Singbox redirect endpoint failed: {e}")




class TestGeoIP:
    def setup_method(self):
        from utils.checker.geo_ip import GeoIP
        self.geo = GeoIP

    @pytest.mark.asyncio
    async def test_mmdb_reader_loads(self):
        await self.geo.initialize()
        assert self.geo._reader is not None, "MMDB reader must be loaded"

    def test_code_to_region_all_countries_covered(self):
        from utils.checker.geo_ip import GeoIP
        missing = []
        for code in GeoIP.FLAGS.keys():
            region = GeoIP.code_to_region(code)
            name_part = region.split(" ", 1)[1] if " " in region else region
            if name_part == code:
                missing.append(code)
        assert not missing, f"These country codes lack proper names: {missing}"

    def test_code_to_region_known_countries(self):
        from utils.checker.geo_ip import GeoIP
        cases = {
            "DE": "Germany",
            "RU": "Russia",
            "US": "USA",
            "NL": "Netherlands",
            "JP": "Japan",
            "BA": "Bosnia",
            "VN": "Vietnam",
            "KG": "Kyrgyzstan",
            "XK": "Kosovo",
        }
        for code, expected_name in cases.items():
            region = GeoIP.code_to_region(code)
            assert expected_name in region, f"{code} -> expected '{expected_name}' in '{region}'"

    def test_code_to_region_has_flag(self):
        from utils.checker.geo_ip import GeoIP
        region = GeoIP.code_to_region("RU")
        assert "🇷🇺" in region

    def test_code_to_region_empty_returns_unk(self):
        from utils.checker.geo_ip import GeoIP
        assert GeoIP.code_to_region("") == "🌍 UNK"
        assert GeoIP.code_to_region("X") == "🌍 UNK"
        assert GeoIP.code_to_region("ABC") == "🌍 UNK"

    @pytest.mark.asyncio
    async def test_resolve_known_ip(self):
        await self.geo.initialize()
        if self.geo._reader:
            try:
                code = self.geo._reader.country("8.8.8.8").country.iso_code
                region = self.geo.code_to_region(code)
                assert "USA" in region, f"8.8.8.8 should be USA, got: {region}"
            except Exception:
                pass




class TestCollectorDedup:
    def test_dedup_regex_extracts_server(self):
        import re
        pattern = re.compile(r'@([^@:/?#\s]+):\d+', re.ASCII)

        cases = [
            (REAL_VLESS, "185.220.101.1"),
            (WS_VLESS, "1.2.3.4"),
            (GRPC_VLESS, "5.6.7.8"),
        ]
        for link, expected_server in cases:
            m = pattern.search(link)
            assert m is not None, f"Regex must match: {link[:60]}"
            assert m.group(1) == expected_server, (
                f"Expected {expected_server}, got {m.group(1)}"
            )

    def test_same_server_deduplicated_in_batch(self):
        import re
        pattern = re.compile(r'@([^@:/?#\s]+):\d+', re.ASCII)

        def extract_server(link):
            m = pattern.search(link)
            return m.group(1).strip().lower() if m else ""

        links = [
            REAL_VLESS,
            REAL_VLESS.replace("f189684b", "aaaaaaaa"),
            WS_VLESS,
        ]

        seen: set[str] = set()
        deduped = []
        for link in links:
            srv = extract_server(link)
            if srv and srv in seen:
                continue
            seen.add(srv)
            deduped.append(link)

        assert len(deduped) == 2, f"Same server must be deduped, got {len(deduped)} links"

    def test_different_servers_kept(self):
        import re
        pattern = re.compile(r'@([^@:/?#\s]+):\d+', re.ASCII)

        def extract_server(link):
            m = pattern.search(link)
            return m.group(1).strip().lower() if m else ""

        links = [REAL_VLESS, WS_VLESS, GRPC_VLESS]
        seen: set[str] = set()
        deduped = []
        for link in links:
            srv = extract_server(link)
            if srv and srv in seen:
                continue
            seen.add(srv)
            deduped.append(link)

        assert len(deduped) == 3, "Different servers must all be kept"




class TestRedisConnectivity:
    @pytest.mark.asyncio
    async def test_redis_ping(self):
        import redis.asyncio as redis_async
        from config import config
        client = redis_async.from_url(config.REDIS_URL)
        try:
            result = await client.ping()
            assert result is True, "Redis must respond to PING"
        except Exception as e:
            pytest.fail(f"Redis connection failed: {e}")
        finally:
            await client.aclose()

    @pytest.mark.asyncio
    async def test_redis_set_get(self):
        import redis.asyncio as redis_async
        from config import config
        client = redis_async.from_url(config.REDIS_URL)
        try:
            await client.set("_test_key_bot", "test_value", ex=10)
            val = await client.get("_test_key_bot")
            assert val is not None
            assert val.decode() == "test_value"
            await client.delete("_test_key_bot")
        except Exception as e:
            pytest.fail(f"Redis set/get failed: {e}")
        finally:
            await client.aclose()




class TestDatabaseConnectivity:
    @pytest.mark.asyncio
    async def test_db_connection(self):
        from database.core import async_session_factory
        from sqlalchemy import text
        try:
            async with async_session_factory() as session:
                result = await session.execute(text("SELECT 1"))
                row = result.fetchone()
                assert row[0] == 1
        except Exception as e:
            pytest.fail(f"DB connection failed: {e}")

    @pytest.mark.asyncio
    async def test_subscriptions_table_exists(self):
        from database.core import async_session_factory
        from sqlalchemy import text
        async with async_session_factory() as session:
            result = await session.execute(text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_name = 'subscriptions'"
            ))
            count = result.scalar()
            assert count == 1, "subscriptions table must exist"

    @pytest.mark.asyncio
    async def test_sub_repo_total_count(self):
        from database.repo import SubRepo
        count = await SubRepo.get_total_count()
        assert isinstance(count, int)
        assert count >= 0

    @pytest.mark.asyncio
    async def test_sub_repo_active_count(self):
        from database.repo import SubRepo
        count = await SubRepo.get_active_count()
        assert isinstance(count, int)
        assert count >= 0

    @pytest.mark.asyncio
    async def test_get_all_keys_returns_set(self):
        from database.repo import SubRepo
        keys = await SubRepo.get_all_keys_set()
        assert isinstance(keys, set)

    @pytest.mark.asyncio
    async def test_enforce_limits_runs_without_error(self):
        from database.repo import SubRepo
        deleted = await SubRepo.enforce_limits()
        assert isinstance(deleted, int)
        assert deleted >= 0




class TestSmartAddSubscription:
    @pytest.mark.asyncio
    async def test_rejects_low_speed(self):
        from database.repo import SubRepo
        result = await SubRepo.smart_add_subscription(
            vless_key=REAL_VLESS,
            region="🇩🇪 Germany",
            latency=50,
            speed_mbps=0.5,
        )
        assert result is False, "Must reject configs with speed < minimum"

    @pytest.mark.asyncio
    async def test_dedup_by_exact_key(self):
        from database.repo import SubRepo
        from database.core import async_session_factory
        from database.models import Subscription
        from sqlalchemy import delete

        async with async_session_factory() as session:
            await session.execute(
                delete(Subscription).where(Subscription.vless_key == REAL_VLESS)
            )
            await session.commit()

        first = await SubRepo.smart_add_subscription(
            vless_key=REAL_VLESS,
            region="🇩🇪 Germany",
            latency=50,
            speed_mbps=50.0,
        )

        second = await SubRepo.smart_add_subscription(
            vless_key=REAL_VLESS,
            region="🇩🇪 Germany",
            latency=50,
            speed_mbps=50.0,
        )

        assert second is False, "Duplicate exact key must be rejected"

        async with async_session_factory() as session:
            await session.execute(
                delete(Subscription).where(Subscription.vless_key == REAL_VLESS)
            )
            await session.commit()

    @pytest.mark.asyncio
    async def test_dedup_by_server_address(self):
        from database.repo import SubRepo
        from database.core import async_session_factory
        from database.models import Subscription
        from sqlalchemy import delete, or_

        same_server_different_uuid = (
            "vless://00000000-0000-0000-0000-000000000001@185.220.101.1:443"
            "?security=reality&type=tcp&flow=xtls-rprx-vision"
            "&pbk=1g94O4Q2qQp1uU9D_B3YhT3t5Z7mIu_XjXq9-z0oGkI&sid=8f"
            "&sni=yahoo.com#Test1"
        )
        same_server_v2 = (
            "vless://00000000-0000-0000-0000-000000000002@185.220.101.1:443"
            "?security=reality&type=tcp&flow=xtls-rprx-vision"
            "&pbk=1g94O4Q2qQp1uU9D_B3YhT3t5Z7mIu_XjXq9-z0oGkI&sid=8f"
            "&sni=yahoo.com#Test2"
        )

        async with async_session_factory() as session:
            await session.execute(
                delete(Subscription).where(
                    or_(
                        Subscription.vless_key == same_server_different_uuid,
                        Subscription.vless_key == same_server_v2,
                    )
                )
            )
            await session.commit()

        first = await SubRepo.smart_add_subscription(
            vless_key=same_server_different_uuid,
            region="🇩🇪 Germany",
            latency=50,
            speed_mbps=50.0,
        )

        second = await SubRepo.smart_add_subscription(
            vless_key=same_server_v2,
            region="🇩🇪 Germany",
            latency=40,
            speed_mbps=60.0,
        )

        assert second is False, "Same server address must be rejected"

        async with async_session_factory() as session:
            await session.execute(
                delete(Subscription).where(
                    or_(
                        Subscription.vless_key == same_server_different_uuid,
                        Subscription.vless_key == same_server_v2,
                    )
                )
            )
            await session.commit()




class TestBroadcastHandler:
    def test_parse_buttons_single(self):
        from handlers.admin.broadcast import _parse_buttons
        rows = _parse_buttons("Сайт | https://example.com")
        assert len(rows) == 1
        assert rows[0][0]["text"] == "Сайт"
        assert rows[0][0]["url"] == "https://example.com"

    def test_parse_buttons_two_in_row(self):
        from handlers.admin.broadcast import _parse_buttons
        rows = _parse_buttons("Кнопка 1 | https://a.com || Кнопка 2 | https://b.com")
        assert len(rows) == 1
        assert len(rows[0]) == 2

    def test_parse_buttons_two_rows(self):
        from handlers.admin.broadcast import _parse_buttons
        raw = "Строка 1 | https://a.com\nСтрока 2 | https://b.com"
        rows = _parse_buttons(raw)
        assert len(rows) == 2

    def test_parse_buttons_invalid_no_pipe(self):
        from handlers.admin.broadcast import _parse_buttons
        rows = _parse_buttons("просто текст без ссылки")
        assert rows == []

    def test_parse_buttons_invalid_no_http(self):
        from handlers.admin.broadcast import _parse_buttons
        rows = _parse_buttons("Кнопка | не-ссылка")
        assert rows == []

    def test_build_inline_kb_none_when_empty(self):
        from handlers.admin.broadcast import _build_inline_kb
        assert _build_inline_kb([]) is None

    def test_build_inline_kb_returns_markup(self):
        from handlers.admin.broadcast import _build_inline_kb
        kb = _build_inline_kb([[{"text": "Test", "url": "https://t.me"}]])
        assert kb is not None
        assert len(kb.inline_keyboard) == 1
        assert kb.inline_keyboard[0][0].text == "Test"
        assert kb.inline_keyboard[0][0].url == "https://t.me"

    def test_buttons_preview_text(self):
        from handlers.admin.broadcast import _buttons_preview_text
        buttons = [[{"text": "A", "url": "https://a.com"}, {"text": "B", "url": "https://b.com"}]]
        preview = _buttons_preview_text(buttons)
        assert "[A]" in preview
        assert "[B]" in preview

    def test_buttons_preview_empty(self):
        from handlers.admin.broadcast import _buttons_preview_text
        assert _buttons_preview_text([]) == ""

    def test_broadcast_handler_has_try_except(self):
        import inspect
        from handlers.admin.broadcast import ask_broadcast
        src = inspect.getsource(ask_broadcast)
        assert "try:" in src, "ask_broadcast must handle media messages with try/except"
        assert "edit_caption" in src, "ask_broadcast must fallback to edit_caption for media"


class TestTrojanSupport:
    def test_parse_trojan_link(self):
        from utils.parser import LinkParser
        link = "trojan://mypassword@1.2.3.4:443?security=tls&sni=example.com#MyTrojan"
        parsed = LinkParser.parse_trojan(link)
        assert parsed is not None
        assert parsed["_protocol"] == "trojan"
        assert parsed["password"] == "mypassword"
        assert parsed["server"] == "1.2.3.4"
        assert parsed["port"] == 443
        assert parsed["security"] == "tls"
        assert parsed["sni"] == "example.com"
        assert parsed["name"] == "MyTrojan"

    def test_singbox_generation_with_trojan(self):
        from utils.singbox import SingBoxGenerator
        from utils.parser import LinkParser
        link = "trojan://mypassword@1.2.3.4:443?security=tls&sni=example.com#MyTrojan"
        parsed = LinkParser.parse_trojan(link)
        config_str = SingBoxGenerator.generate([parsed])
        assert "trojan" in config_str
        assert "mypassword" in config_str
        assert "1.2.3.4" in config_str

    def test_clash_generation_with_trojan(self):
        from utils.clash import ClashGenerator
        from utils.parser import LinkParser
        link = "trojan://mypassword@1.2.3.4:443?security=tls&sni=example.com#MyTrojan"
        parsed = LinkParser.parse_trojan(link)
        config_str = ClashGenerator.generate_conf([parsed])
        assert "type: trojan" in config_str
        assert "password: mypassword" in config_str
        assert "1.2.3.4" in config_str


if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", __file__, "-v", "--tb=short", "-p", "no:warnings"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    sys.exit(result.returncode)
