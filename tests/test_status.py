import pytest
from src.status import StatusFile


class TestStatusFile:
    def test_write_and_read(self, tmp_path):
        path = str(tmp_path / "vpn.status")
        sf = StatusFile(path, interval=0)
        sf.record_in(100)
        sf.record_out(200)
        sf.maybe_write("10.8.0.1:1194", "10.8.0.2", "CONNECTED", force=True)
        content = (tmp_path / "vpn.status").read_text()
        assert "OpenVPN CLIENT LIST" in content
        assert "GLOBAL STATS" in content
        assert "10.8.0.2" in content
        sf.close()
        assert not (tmp_path / "vpn.status").exists()

    def test_stats_accumulate(self, tmp_path):
        path = str(tmp_path / "stats.status")
        sf = StatusFile(path, interval=0)
        sf.record_in(50)
        sf.record_in(150)
        sf.record_out(300)
        sf.maybe_write("server", "10.8.0.2", "CONNECTED", force=True)
        content = (tmp_path / "stats.status").read_text()
        assert "200" in content
        assert "300" in content
        sf.close()

    def test_write_throttle(self, tmp_path):
        path = str(tmp_path / "throttle.status")
        sf = StatusFile(path, interval=60)
        sf.maybe_write("s", "10.8.0.2", "CONNECTED", force=True)
        stats1 = (tmp_path / "throttle.status").read_text()
        sf.maybe_write("s", "10.8.0.2", "CONNECTED")
        stats2 = (tmp_path / "throttle.status").read_text()
        assert stats1 == stats2
        sf.close()
