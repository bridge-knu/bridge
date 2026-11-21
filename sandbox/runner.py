"""샌드박스 컨테이너 안에서 학생 코드를 컴파일·실행한다.

표준 입력으로 {"lang": "c" | "python", "code": "...", "stdin": "..."} 를 받고,
표준 출력으로 결과 JSON 한 줄을 낸다. 워커가 이 JSON을 그대로 저장한다.

- 실행 시간 5초 (컴파일은 10초)
- 출력은 64KB까지만 돌려준다. 프로그램 출력은 파일(/tmp, 16MB)로 받아서
  무한 출력이 메모리를 채우지 못하게 한다.
- 프로그램이 만든 자식 프로세스까지 한꺼번에 종료한다.
"""

import json
import os
import signal
import subprocess
import sys
import time

WORK_DIR = "/tmp"
RUN_TIMEOUT = 5
COMPILE_TIMEOUT = 10
OUTPUT_LIMIT = 64 * 1024

SIGNAL_MESSAGES = {
    signal.SIGSEGV: "잘못된 메모리 접근 (Segmentation fault)",
    signal.SIGFPE: "0으로 나누기 등 계산 오류 (Floating point exception)",
    signal.SIGABRT: "프로그램이 비정상 종료됨 (Aborted)",
    signal.SIGKILL: "강제 종료됨 (메모리 128MB 초과일 수 있음)",
}


def read_capped(path: str) -> str:
    try:
        with open(path, "rb") as f:
            data = f.read(OUTPUT_LIMIT + 1)
    except FileNotFoundError:
        return ""
    text = data[:OUTPUT_LIMIT].decode("utf-8", errors="replace")
    if len(data) > OUTPUT_LIMIT:
        text += "\n... (출력이 64KB를 넘어 잘림)"
    return text


def run(cmd: list[str], timeout: int, stdin_path: str | None, out_path: str, err_path: str):
    """명령을 실행하고 (종료 코드, 시간 초과 여부, 걸린 ms)를 돌려준다."""
    stdin = open(stdin_path, "rb") if stdin_path else subprocess.DEVNULL
    with open(out_path, "wb") as out, open(err_path, "wb") as err:
        start = time.monotonic()
        proc = subprocess.Popen(cmd, stdin=stdin, stdout=out, stderr=err, start_new_session=True)
        try:
            code = proc.wait(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            code, timed_out = 124, True
        duration = int((time.monotonic() - start) * 1000)
    if stdin_path:
        stdin.close()
    return code, timed_out, duration


def result(stdout="", stderr="", exit_code=0, timed_out=False, duration_ms=0, phase="run"):
    return {
        "stdout": stdout,
        "stderr": stderr,
        "exitCode": exit_code,
        "timedOut": timed_out,
        "durationMs": duration_ms,
        "phase": phase,
    }


def execute(job: dict) -> dict:
    os.chdir(WORK_DIR)
    lang = job["lang"]
    with open("in.txt", "w", encoding="utf-8") as f:
        f.write(job.get("stdin") or "")

    if lang == "c":
        with open("main.c", "w", encoding="utf-8") as f:
            f.write(job["code"])
        code, timed_out, _ = run(
            ["gcc", "main.c", "-o", "main", "-lm"], COMPILE_TIMEOUT, None, "compile.out", "compile.err"
        )
        if timed_out:
            return result(stderr="컴파일 시간 초과 (10초)", exit_code=124, timed_out=True, phase="compile")
        if code != 0:
            return result(stderr=read_capped("compile.err"), exit_code=code, phase="compile")
        cmd = ["./main"]
    elif lang == "python":
        with open("main.py", "w", encoding="utf-8") as f:
            f.write(job["code"])
        cmd = ["python3", "-B", "main.py"]
    else:
        return result(stderr=f"지원하지 않는 언어: {lang}", exit_code=1, phase="compile")

    code, timed_out, duration = run(cmd, RUN_TIMEOUT, "in.txt", "out.txt", "err.txt")
    stderr = read_capped("err.txt")
    if timed_out:
        stderr += ("\n" if stderr else "") + f"시간 초과 ({RUN_TIMEOUT}초)"
    elif code < 0:
        sig = -code
        message = SIGNAL_MESSAGES.get(sig, f"신호 {sig}로 종료됨")
        stderr += ("\n" if stderr else "") + message
        code = 128 + sig
    return result(read_capped("out.txt"), stderr, code, timed_out, duration)


def harden() -> None:
    """학생 프로그램이 /proc/1/fd/1 로 이 프로세스의 출력에 직접 써서 64KB 제한을 우회하지 못하게 한다.

    학생 프로그램도 같은 사용자(1000)로 돌기 때문에 기본으로는 /proc/1/fd 에 접근할 수 있다.
    dumpable을 끄면 /proc/1 아래가 root 소유가 되어 접근할 수 없다 (자식 프로세스에는 영향 없음).
    """
    import ctypes

    PR_SET_DUMPABLE = 4
    ctypes.CDLL(None).prctl(PR_SET_DUMPABLE, 0, 0, 0, 0)


def main() -> None:
    harden()
    job = json.load(sys.stdin)
    try:
        out = execute(job)
    except Exception as e:  # 어떤 경우에도 JSON 한 줄은 낸다
        out = result(stderr=f"실행 환경 오류: {e}", exit_code=1, phase="internal")
    sys.stdout.write(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
