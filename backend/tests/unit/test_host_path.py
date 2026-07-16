# backend/tests/unit/test_host_path.py
from backend.tools.host_path import resolve_host_path


def test_passthrough_under_host_fs_mount():
    assert resolve_host_path("/host/Users/me/Desktop/x.md",
                             fs_mount="/host", home_mount="/host_home") == "/host/Users/me/Desktop/x.md"


def test_passthrough_under_host_home_mount():
    assert resolve_host_path("/host_home/Desktop/x.md",
                             fs_mount="/host", home_mount="/host_home") == "/host_home/Desktop/x.md"


def test_tilde_expands_to_home_mount():
    assert resolve_host_path("~/Desktop/x.md",
                             fs_mount="/host", home_mount="/host_home") == "/host_home/Desktop/x.md"


def test_tmp_stays_container_local():
    assert resolve_host_path("/tmp/foo.txt",
                             fs_mount="/host", home_mount="/host_home") == "/tmp/foo.txt"


def test_relative_stays_container_local():
    assert resolve_host_path("foo/bar.txt",
                             fs_mount="/host", home_mount="/host_home") == "foo/bar.txt"


def test_absolute_path_goes_under_host_fs():
    assert resolve_host_path("/etc/hosts",
                             fs_mount="/host", home_mount="/host_home") == "/host/etc/hosts"


def test_empty_returns_empty():
    assert resolve_host_path("") == ""
