from src.cli import parse_args


class TestCliDefaults:
    def test_no_args_uses_config_defaults(self):
        cfg = parse_args([])
        assert cfg.dev == "tun"
        assert cfg.proto == "udp"
        assert cfg.port == 1194
        assert cfg.verb == 1
        assert cfg.keepalive_interval == 10
        assert cfg.keepalive_timeout == 120
        assert cfg.comp_lzo is False
        assert cfg.redirect_gateway is False

    def test_explicit_flags(self):
        cfg = parse_args([
            "--remote", "example.com",
            "--port", "2200",
            "--proto", "tcp",
            "--verb", "4",
            "--comp-lzo",
            "--keepalive", "5", "60",
            "--status", "/tmp/vpn.status",
        ])
        assert cfg.remote == "example.com"
        assert cfg.port == 2200
        assert cfg.proto == "tcp"
        assert cfg.verb == 4
        assert cfg.comp_lzo is True
        assert cfg.keepalive_interval == 5
        assert cfg.keepalive_timeout == 60
        assert cfg.status_file == "/tmp/vpn.status"


class TestCliConfigOverride:
    def _write_conf(self, tmp_path):
        conf = tmp_path / "server.conf"
        conf.write_text("\n".join([
            "port 2200",
            "proto tcp",
            "verb 3",
            "comp-lzo",
            "keepalive 15 300",
            "status /tmp/from-file.status",
            "server 10.9.0.0 255.255.255.0",
        ]))
        return conf

    def test_file_values_preserved_without_flags(self, tmp_path):
        conf = self._write_conf(tmp_path)
        cfg = parse_args(["-c", str(conf)])
        assert cfg.port == 2200, "CLI defaults must not stomp the config file"
        assert cfg.proto == "tcp"
        assert cfg.verb == 3
        assert cfg.comp_lzo is True, "store_true default must not stomp the config file"
        assert cfg.keepalive_interval == 15
        assert cfg.keepalive_timeout == 300
        assert cfg.status_file == "/tmp/from-file.status"
        assert cfg.server == "10.9.0.0/24"

    def test_explicit_flags_override_file(self, tmp_path):
        conf = self._write_conf(tmp_path)
        cfg = parse_args(["-c", str(conf), "--port", "3300", "--verb", "2"])
        assert cfg.port == 3300
        assert cfg.verb == 2
        # Untouched values still come from the file:
        assert cfg.proto == "tcp"
        assert cfg.comp_lzo is True

    def test_keepalive_override(self, tmp_path):
        conf = self._write_conf(tmp_path)
        cfg = parse_args(["-c", str(conf), "--keepalive", "1", "2"])
        assert cfg.keepalive_interval == 1
        assert cfg.keepalive_timeout == 2
