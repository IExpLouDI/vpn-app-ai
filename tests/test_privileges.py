from unittest.mock import MagicMock, patch

import pytest

from src.privileges import (
    DEFAULT_USER,
    drop_privileges,
    is_root,
    maybe_drop_privileges,
)


def test_is_root_returns_bool():
    with patch("src.privileges.os.geteuid", return_value=0):
        assert is_root() is True
    with patch("src.privileges.os.geteuid", return_value=1000):
        assert is_root() is False


def test_drop_unknown_user_raises():
    with patch("src.privileges.is_root", return_value=True), \
         patch("src.privileges.pwd.getpwnam", side_effect=KeyError("nope")):
        with pytest.raises(ValueError):
            drop_privileges("this_user_does_not_exist_xyz")


def test_drop_unknown_group_raises():
    fake_pw = MagicMock()
    fake_pw.pw_uid = 65534
    fake_pw.pw_gid = 65534
    fake_pw.pw_dir = "/nonexistent"
    with patch("src.privileges.is_root", return_value=True), \
         patch("src.privileges.pwd.getpwnam", return_value=fake_pw), \
         patch("src.privileges.grp.getgrnam", side_effect=KeyError("nope")):
        with pytest.raises(ValueError):
            drop_privileges(DEFAULT_USER, "this_group_does_not_exist_xyz")


def test_maybe_drop_none_is_noop():
    with patch("src.privileges.os.setuid") as setuid, \
         patch("src.privileges.os.setgid") as setgid:
        maybe_drop_privileges(None)
        setuid.assert_not_called()
        setgid.assert_not_called()


def test_drop_when_not_root_is_noop():
    fake_pw = MagicMock()
    fake_pw.pw_uid = 65534
    fake_pw.pw_gid = 65534
    fake_pw.pw_dir = "/nonexistent"
    with patch("src.privileges.is_root", return_value=False), \
         patch("src.privileges.pwd.getpwnam", return_value=fake_pw), \
         patch("src.privileges.os.setuid") as setuid, \
         patch("src.privileges.os.setgid") as setgid:
        drop_privileges(DEFAULT_USER)
        setuid.assert_not_called()
        setgid.assert_not_called()


def test_drop_calls_setuid_setgid():
    fake_pw = MagicMock()
    fake_pw.pw_uid = 65534
    fake_pw.pw_gid = 65534
    fake_pw.pw_dir = "/nonexistent"
    with patch("src.privileges.is_root", return_value=True), \
         patch("src.privileges.pwd.getpwnam", return_value=fake_pw), \
         patch("src.privileges.os.setgroups") as setgroups, \
         patch("src.privileges.os.setgid") as setgid, \
         patch("src.privileges.os.setuid") as setuid, \
         patch.dict("src.privileges.os.environ", {}, clear=True):
        drop_privileges(DEFAULT_USER)
        setgroups.assert_called_once_with([])
        setgid.assert_called_once_with(65534)
        setuid.assert_called_once_with(65534)
        assert "USER" in __import__("os").environ
        assert __import__("os").environ["USER"] == DEFAULT_USER
