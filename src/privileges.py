import grp
import logging
import os
import pwd

logger = logging.getLogger("pyvpn.privileges")

DEFAULT_USER = "nobody"


def is_root() -> bool:
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


def drop_privileges(username: str = DEFAULT_USER, groupname: str | None = None) -> None:
    if not is_root():
        logger.info("Not running as root; skipping privilege drop")
        return

    try:
        pw = pwd.getpwnam(username)
    except KeyError as e:
        raise ValueError(f"Unknown user for privilege drop: {username}") from e

    uid = pw.pw_uid
    gid = pw.pw_gid
    if groupname is not None:
        try:
            gid = grp.getgrnam(groupname).gr_gid
        except KeyError as e:
            raise ValueError(f"Unknown group for privilege drop: {groupname}") from e

    try:
        os.setgroups([])
    except OSError:
        logger.warning("Could not clear supplementary groups; continuing")

    os.setgid(gid)
    os.setuid(uid)

    if pw.pw_dir:
        os.environ["HOME"] = pw.pw_dir
    os.environ["USER"] = username
    logger.info("Dropped privileges to %s (uid=%d, gid=%d)", username, uid, gid)


def maybe_drop_privileges(username: str | None) -> None:
    if not username:
        return
    drop_privileges(username)
