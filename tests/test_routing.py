from src.routing import IpPool


class TestIpPool:
    def test_default_pool(self):
        pool = IpPool("10.8.0.0/24")
        assert pool.server_ip == "10.8.0.1"
        assert pool.allocated_count() == 0

    def test_allocate(self):
        pool = IpPool("10.8.0.0/24")
        ip = pool.allocate("client1")
        assert ip == "10.8.0.2"
        assert pool.allocated_count() == 1

    def test_allocate_multiple(self):
        pool = IpPool("10.8.0.0/24")
        ip1 = pool.allocate("client1")
        ip2 = pool.allocate("client2")
        assert ip1 == "10.8.0.2"
        assert ip2 == "10.8.0.3"

    def test_release(self):
        pool = IpPool("10.8.0.0/24")
        pool.allocate("client1")
        pool.release("client1")
        assert pool.allocated_count() == 0
        ip = pool.allocate("client2")
        assert ip == "10.8.0.2"

    def test_pool_exhaustion(self):
        pool = IpPool("10.8.0.0/30")
        pool.allocate("c1")
        pool.allocate("c2")
        assert pool.allocate("c3") is None

    def test_custom_pool_range(self):
        pool = IpPool("10.8.0.0/24", "10.8.0.10-10.8.0.20")
        ip = pool.allocate("client1")
        assert ip == "10.8.0.10"

    def test_get_client_ip(self):
        pool = IpPool("10.8.0.0/24")
        pool.allocate("test-client")
        assert pool.get_client_ip("test-client") == "10.8.0.2"
        assert pool.get_client_ip("unknown") is None

    def test_get_client_id_by_ip(self):
        pool = IpPool("10.8.0.0/24")
        pool.allocate("test-client")
        assert pool.get_client_id_by_ip("10.8.0.2") == "test-client"
        assert pool.get_client_id_by_ip("10.8.0.99") is None

    def test_allocated_ips(self):
        pool = IpPool("10.8.0.0/24")
        pool.allocate("c1")
        pool.allocate("c2")
        assert pool.allocated_ips() == ["10.8.0.2", "10.8.0.3"]
