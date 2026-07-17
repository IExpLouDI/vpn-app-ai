from src.config import Config, _netmask_to_cidr


class TestConfig:
    def test_default_config(self):
        cfg = Config()
        assert cfg.dev == "tun"
        assert cfg.proto == "udp"
        assert cfg.port == 1194
        assert cfg.get_mode() == "client"

    def test_server_mode(self):
        cfg = Config(server="10.8.0.0/24")
        assert cfg.get_mode() == "server"

    def test_from_dict(self):
        cfg = Config.from_dict({
            "dev": "tun1",
            "port": 1195,
            "proto": "tcp",
            "unknown": "ignored",
        })
        assert cfg.dev == "tun1"
        assert cfg.port == 1195
        assert cfg.proto == "tcp"
        assert not hasattr(cfg, "unknown")

    def test_config_file_parsing(self, tmp_path):
        conf = tmp_path / "server.conf"
        conf.write_text("\n".join([
            "dev tun0",
            "proto udp",
            "port 1194",
            "server 10.8.0.0 255.255.255.0",
            "ifconfig-pool 10.8.0.2 10.8.0.100",
            "ca ca.crt",
            "cert server.crt",
            "key server.key",
            "cipher AES-256-GCM",
            "comp-lzo",
            "keepalive 10 120",
            "verb 3",
            "; comment",
            "# also comment",
        ]))
        cfg = Config.from_file(str(conf))
        assert cfg.dev == "tun0"
        assert cfg.proto == "udp"
        assert cfg.port == 1194
        assert cfg.server == "10.8.0.0/24"
        assert cfg.ifconfig_pool == "10.8.0.2-10.8.0.100"
        assert cfg.ca == "ca.crt"
        assert cfg.cert == "server.crt"
        assert cfg.key == "server.key"
        assert cfg.cipher == "AES-256-GCM"
        assert cfg.comp_lzo is True
        assert cfg.keepalive_interval == 10
        assert cfg.keepalive_timeout == 120
        assert cfg.verb == 3

    def test_client_config_file(self, tmp_path):
        conf = tmp_path / "client.conf"
        conf.write_text("\n".join([
            "dev tun",
            "proto udp",
            "remote 192.168.1.100",
            "ca ca.crt",
            "cert client.crt",
            "key client.key",
        ]))
        cfg = Config.from_file(str(conf))
        assert cfg.remote == "192.168.1.100"
        assert cfg.get_mode() == "client"

    def test_netmask_to_cidr(self):
        assert _netmask_to_cidr("255.255.255.0") == 24
        assert _netmask_to_cidr("255.255.0.0") == 16
        assert _netmask_to_cidr("255.0.0.0") == 8
        assert _netmask_to_cidr("0.0.0.0") == 0
        assert _netmask_to_cidr("255.255.255.252") == 30

    def test_redirect_gateway(self, tmp_path):
        conf = tmp_path / "redirect.conf"
        conf.write_text("redirect-gateway\n")
        cfg = Config.from_file(str(conf))
        assert cfg.redirect_gateway is True

    def test_extra_options(self, tmp_path):
        conf = tmp_path / "extra.conf"
        conf.write_text("unknown-opt value1\n")
        cfg = Config.from_file(str(conf))
        assert cfg.extra_options.get("unknown-opt") == ["value1"]

    def test_status_directive(self, tmp_path):
        conf = tmp_path / "status.conf"
        conf.write_text("status /tmp/vpn.status\n")
        cfg = Config.from_file(str(conf))
        assert cfg.status_file == "/tmp/vpn.status"
        assert "status" not in cfg.extra_options

    def test_invalid_port_rejected(self):
        import pytest
        with pytest.raises(ValueError, match="port"):
            Config(port=0)
        with pytest.raises(ValueError, match="port"):
            Config(port=70000)

    def test_invalid_proto_rejected(self):
        import pytest
        with pytest.raises(ValueError, match="proto"):
            Config(proto="gre")

    def test_invalid_verb_rejected(self):
        import pytest
        with pytest.raises(ValueError, match="verb"):
            Config(verb=5)
