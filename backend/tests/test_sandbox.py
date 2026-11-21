"""실제 샌드박스 컨테이너로 실행해 보는 테스트.

bridge-sandbox 이미지와 docker 명령이 있어야 한다 (docker compose up -d --build 후).
없으면 건너뛰고, REQUIRE_SANDBOX=1이면 실패한다.
"""

import os
import shutil
import subprocess

import pytest

from app.worker import run_in_container


def sandbox_ready() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "image", "inspect", "bridge-sandbox"], capture_output=True).returncode == 0


if not sandbox_ready():
    if os.environ.get("REQUIRE_SANDBOX") == "1":
        raise RuntimeError("bridge-sandbox 이미지가 없음 (docker compose up -d --build 필요)")
    pytest.skip("bridge-sandbox 이미지가 없음", allow_module_level=True)

counter = iter(range(10**6))


def run(lang, code, stdin=""):
    job_id = f"test{os.getpid()}x{next(counter)}"
    return run_in_container({"jobId": job_id, "lang": lang, "code": code, "stdin": stdin})


def test_c_hello():
    code = r"""
#include <stdio.h>
int main() {
    int a[] = {1, 2, 3, 4, 5}, s = 0;
    for (int i = 0; i < 5; i++) s += a[i];
    printf("%d\n", s);
}
"""
    out = run("c", code)
    assert out["stdout"] == "15\n"
    assert out["exitCode"] == 0
    assert out["timedOut"] is False


def test_python_with_stdin():
    out = run("python", "print(int(input()) * 2)", stdin="21\n")
    assert out["stdout"] == "42\n"


def test_compile_error():
    out = run("c", "int main(){ return 0 }")
    assert out["exitCode"] != 0
    assert "error" in out["stderr"]
    assert out["phase"] == "compile"


def test_infinite_loop_times_out():
    out = run("c", "int main(){ while(1){} }")
    assert out["timedOut"] is True
    assert out["exitCode"] == 124
    assert 5000 <= out["durationMs"] < 7000


def test_infinite_output_is_capped():
    out = run("c", r'#include <stdio.h>' + "\n" + r'int main(){ for(;;) printf("aaaaaaaaaa\n"); }')
    assert len(out["stdout"].encode()) <= 64 * 1024 + 100
    assert "64KB" in out["stdout"]


def test_network_is_blocked():
    code = "import socket\ntry:\n    socket.create_connection(('8.8.8.8', 53), timeout=2)\n    print('connected')\nexcept OSError:\n    print('blocked')\n"
    assert run("python", code)["stdout"] == "blocked\n"


def test_filesystem_is_read_only():
    code = "try:\n    open('/etc/x', 'w')\n    print('written')\nexcept OSError:\n    print('read-only')\n"
    assert run("python", code)["stdout"] == "read-only\n"


def test_fork_bomb_is_contained():
    out = run("c", "#include <unistd.h>\nint main(){ for(;;) fork(); }")
    assert out["timedOut"] is True


def test_memory_bomb_is_killed():
    code = "#include <stdlib.h>\n#include <string.h>\nint main(){ for(;;){ char*p=malloc(1<<20); if(!p) return 3; memset(p,1,1<<20);} }"
    out = run("c", code)
    assert out["exitCode"] != 0


def test_segfault_message():
    out = run("c", "int main(){ int *p = 0; *p = 1; }")
    assert "Segmentation fault" in out["stderr"]


def test_cannot_write_to_runner_stdout():
    # 리뷰 C1: /proc/1/fd/1(러너의 출력)에 직접 써서 64KB 제한을 우회하는 공격
    code = (
        "import os\n"
        "try:\n"
        "    fd = os.open('/proc/1/fd/1', os.O_WRONLY)\n"
        "except OSError:\n"
        "    print('blocked')\n"
        "else:\n"
        "    for _ in range(2000):\n"
        "        os.write(fd, b'X' * 65536)\n"
        "    print('wrote')\n"
    )
    out = run("python", code)
    assert out["stdout"] == "blocked\n"


def test_cannot_read_runner_memory_or_environment():
    code = (
        "for p in ['/proc/1/environ', '/proc/1/mem', '/proc/1/cmdline']:\n"
        "    try:\n"
        "        open(p, 'rb').read(1)\n"
        "        print(p, 'open')\n"
        "    except OSError:\n"
        "        print(p, 'blocked')\n"
    )
    out = run("python", code)
    assert "/proc/1/environ blocked" in out["stdout"]
    assert "/proc/1/mem blocked" in out["stdout"]
