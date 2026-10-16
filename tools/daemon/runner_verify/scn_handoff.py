"""R11, R14, R15, R16: the handoff on real processes and a real file system and git: quiescence before the
preserve commit, the preserve manifest (one tree function), failures of the preservation that stop in a recoverable
state, and daemon crashes in every handoff phase."""
import json
import os
import shutil
import subprocess
import sys
import time

from .common import read_json, read_jsonl, read_text, write_text
from .harness import BASIC, HANDOFF, OTHER, first_seq, rets, se, tr
from .scn_fence import accepted_pushes, drain_ok, finished, rejected_pushes
from .scn_restart import sent_of

SECRET_NAME = "api" + "_key"


def fake_secret():
    """The shape of a secret (preserve_manifest.secret_patterns), built at run time. Not a real value."""
    return SECRET_NAME + " = '" + "x" * 20 + "'\n"


def prep_handoff(w, task=HANDOFF, extra=None, ignore_term=False, writes=None):
    """A is building; the switch signal waits for the `go` file. Returns (instr, handle, go path)."""
    go = str(w.layout.root / "go")
    writes = writes if writes is not None else [("src/work.py", "print('work')\n"), ("notes.txt", "n\n")]
    script = ([{"op": "ignore_term"}] if ignore_term else []) + [{"op": "write", "path": p, "content": c} for p, c in writes]
    script += (extra or []) + [{"op": "wait_file", "path": go}, {"op": "switch_signal"}, {"op": "sleep", "s": 3600}]
    instr, a, _ = w.lease_to_building(task, script)
    w.wait_log(a, "write", count=len(writes))
    return instr, a, go


def trigger(w, a, go, **kw):
    open(go, "w").close()
    w.wait_log(a, "switch_signal")
    return w.drain(**kw)


def tree_of(w, sha):
    return w.git(["rev-parse", f"{sha}^{{tree}}"]).stdout.strip()


def commits_on(w, instr):
    ref = w.git(["rev-parse", "--verify", "-q", f"refs/heads/{instr['branch']}"], check=False)
    if ref.returncode != 0:
        return 0
    return int(w.git(["rev-list", "--count", f"refs/heads/{instr['branch']}", f"^{instr['base_sha']}"]).stdout.strip())


# =============================================================== R11
def r11(rep, cx):
    with cx.world() as w:
        extra = [{"op": "spawn_survivor", "name": "writer", "script": [{"op": "loop_write", "path": "src/shared.txt", "interval": 0.005}]},
                 {"op": "spawn_child", "name": "loop", "script": [{"op": "ignore_term"},
                                                                    {"op": "loop_write", "path": "src/loop.txt", "interval": 0.005}]}]
        instr, a, go = prep_handoff(w, ignore_term=True, extra=extra, writes=[("src/shared.txt", "A\n"), ("src/work.py", "print(1)\n")])
        w.wait_log(a, "spawn_survivor")
        w.wait_log(a, "spawn_child")
        time.sleep(0.3)
        rep.ok("시작 전: 빌더 그룹이 실제로 쓰는 중(쓰기 핸들 > 0)이고 stop 요청을 무시한다",
               w.ports().worktree.open_write_handles(instr["worktree"]) > 0 or w.ports().process.alive_count(HANDOFF) > 0)
        m = w.mark()
        res = trigger(w, a, go)
        js = w.journal()[m:]
        hr = w.task(HANDOFF)["handoff_record"]
        branch_sha = hr["wip_commit_sha"]
        s_stop = first_seq(js, "intent_record", action="stop")
        s_iso = first_seq(js, "side_effect_record", id="worktree_readonly")
        s_conf = first_seq(js, "result_record", action="confirm_quiescent", outcome="quiescent")
        s_pc = first_seq(js, "intent_record", action="preserve_commit")
        s_pp = first_seq(js, "intent_record", action="preserve_push")
        order = [s_stop, s_iso, s_conf, s_pc, s_pp]
        rep.eq("기록 순서: stop < isolate < confirm_quiescent(quiescent) < preserve 커밋 < preserve 푸시", True,
               all(x is not None for x in order) and order == sorted(order))
        stop_res = [r for r in js if r["kind"] == "result_record" and r["action"] == "stop"][0]
        rep.eq("stop 결과: 기한 경과(grace_expired) — 프로세스가 요청을 무시했다", "grace_expired", stop_res["outcome"])
        kills = [e for e in w.proc_log() if e["event"] == "terminate_group"]
        rep.eq("isolate가 프로세스 그룹을 실제로 종료(구성원 2 이상, 남은 것 0)", (True, 0),
               (len(kills[0]["members"]) >= 2, kills[0]["left"]))
        w.wait_gone(a, 5)
        rep.eq("정지 확인 시점의 실제 파일 시스템 조건: 생존 프로세스 0, 쓰기 핸들 0", (0, 0),
               (w.ports().process.alive_count(HANDOFF), w.ports().worktree.open_write_handles(instr["worktree"])))
        m1 = w.ports().worktree.max_mtime(instr["worktree"])
        o1 = w.ports().git.git_write_tree_oid(instr["worktree"])
        time.sleep(0.5)
        o2 = w.ports().git.git_write_tree_oid(instr["worktree"])
        rep.eq("격리 뒤 mtime 불변, tree OID 두 번 일치, 둘 다 quiescent_tree_oid와 같다", (m1, hr["quiescent_tree_oid"], hr["quiescent_tree_oid"]),
               (w.ports().worktree.max_mtime(instr["worktree"]), o1, o2))
        rep.eq("보존 커밋의 tree OID == quiescent_tree_oid", hr["quiescent_tree_oid"], tree_of(w, branch_sha))
        writer = a.log(w, "writer")
        rep.ok("다른 세션에 남은 쓰기 프로세스의 격리 뒤 쓰기는 실제로 실패했고(EACCES) 보존본에 섞이지 않았다",
               any(r.get("ok") is False for r in writer if r["op"] == "loop_write"))
        on_disk = read_text(os.path.join(instr["worktree"], "src/shared.txt"))
        in_commit = w.git(["show", f"{branch_sha}:src/shared.txt"]).stdout
        rep.eq("보존 커밋의 파일 내용 == 격리 시점 디스크의 내용(격리 뒤 쓰기 없음)", on_disk, in_commit)
        rep.eq("원격이 수락한 푸시는 데몬 보존 자격 하나뿐, 빌더 토큰·자격으로 푸시된 보존 커밋 0건",
               [("preserve_credential", instr["lease_id"])], [(e["credential_name"], e["lease_id"]) for e in accepted_pushes(w)])
        w.git(["commit", "--allow-empty", "-q", "-m", "late commit of A"], cwd=instr["worktree"])
        late_sha = w.git(["rev-parse", "HEAD"], cwd=instr["worktree"]).stdout.strip()
        probe = w.git(["push", "--force", str(w.remote), f"{late_sha}:refs/heads/{instr['branch']}"], cwd=instr["worktree"], check=False,
                      env={"RV_PUSH_CREDENTIAL": a.token})
        rep.ok("빌더의 (회수된) 자격으로는 지금 푸시해도 거부된다", probe.returncode != 0 and "RV-REJECT" in probe.stderr)

    # the group kill does not reach a writer that left the group: the quiescence check must see it and stop
    with cx.world() as w:
        ghost = str(w.layout.root / "ghost_ready")
        extra = [{"op": "spawn_survivor", "name": "ghost", "script": [{"op": "loop_write_fd", "path": "src/ghost.txt", "interval": 0.005}]}]
        instr, a, go = prep_handoff(w, extra=extra)
        w.wait_log(a, "spawn_survivor")
        time.sleep(0.4)
        refs0 = w.remote_refs()
        m = w.mark()
        res = trigger(w, a, go)
        js = w.journal()[m:]
        t = w.task(HANDOFF)
        reasons = [r["args"].get("reasons") for r in js if r["kind"] == "result_record" and r["action"] == "confirm_quiescent"
                   and r["outcome"] == "not_quiescent"]
        rep.eq("그룹 밖에서 열린 파일로 계속 쓰는 프로세스: 정지 확인이 실패를 반복하다 handoff_blocked(시도 4회)", ("handoff_blocked", 4),
               (t["task_state"]["state"], len(reasons)))
        flat = sorted({x for r in reasons for x in r})
        rep.ok("실패 사유에 열린 쓰기 핸들이 실제 /proc 검사로 잡혔다(open_write_handle)", "open_write_handle" in flat, flat)
        rep.ok("mtime 변화도 실제 파일 시스템에서 잡혔다(mtime_changed)", "mtime_changed" in flat, flat)
        rep.eq("정지 확인 전: 커밋·푸시 0건(로컬 브랜치 없음, 원격 불변, 수락된 푸시 0)", (0, refs0, 0),
               (commits_on(w, instr), w.remote_refs(), len(accepted_pushes(w))))
        rep.eq("새 임대 없음: 세대 1, issue_lease 0건, 두 번째 빌더 inbox 비어 있음", (1, 0, []),
               (t["lease_generation"], len(se(js, "issue_lease")), sorted(p.name for p in (w.layout.inbox / "standin-runner-2").glob("*"))
                if (w.layout.inbox / "standin-runner-2").exists() else []))
        for pid in w.survivors():
            os.kill(pid, 9)
        time.sleep(0.3)
        w.event("recovery_decision", HANDOFF, {"recovery_ref": "REC-R11", "action": "retry"}).result
        t = w.task(HANDOFF)
        rep.eq("원인 제거(프로세스 종료) 뒤 recovery_decision(retry): 정지 확인을 통과해 보존하고 다음 임대(세대 2)", ("leased", 2, 1),
               (t["task_state"]["state"], t["lease_generation"], commits_on(w, instr)))
        rep.eq("보존 커밋의 tree OID == quiescent_tree_oid", t["handoff_record"]["quiescent_tree_oid"], tree_of(w, t["handoff_record"]["wip_commit_sha"]))
    rep.unconfirmed("[R11 실제 CLI 변형] stop을 무시하고 루프로 파일을 쓰는 실제 벤더 CLI 프로세스",
                    "쓰는 프로세스는 스크립트 프로세스(standin)다. 벤더 CLI에게 stop 무시·쓰기 루프를 시키는 방법이 확인되지 않아 시험하지 않았다")
    rep.not_proved("쓰기 금지 격리는 파일 권한(chmod)이다. 같은 사용자의 프로세스는 권한을 되돌릴 수 있으므로 격리만으로 쓰기를 막았다고 말하지 않는다: 이 시험에서 쓰기를 막은 것은 프로세스 그룹 종료와, 그룹 밖 프로세스에 대한 열린 핸들 검사(정지 확인 실패)였다",
                   "lsof는 이 호스트에 없다. /proc/<pid>/fd와 fdinfo 검사로 대신했다(동등 수단)",
                   "쓰는 프로세스는 벤더 CLI가 아니라 스크립트 프로세스(standin)다")


# =============================================================== R14
def r14(rep, cx):
    with cx.world() as w:
        ports = w.ports()
        # the tree function on a real work tree, one change at a time
        instr0 = None
        w.init_task(OTHER).result
        w.grant(OTHER).result
        instr0 = w.latest_instruction(OTHER)
        base_wt = str(w.layout.root / "scratch")
        w.git(["worktree", "add", "-q", "--detach", base_wt, instr0["base_sha"]])
        git = ports.git
        o0 = git.git_write_tree_oid(base_wt)
        rep.eq("기준: 변경 없는 작업 트리의 tree OID는 기준 커밋의 tree와 같다", w.git(["rev-parse", f"{instr0['base_sha']}^{{tree}}"]).stdout.strip(), o0)
        keep = os.path.join(base_wt, "tools/mock/other/README.md")

        def case(name, mutate, expect):
            wt = str(w.layout.root / f"case{len(rep.checks)}")
            w.git(["worktree", "add", "-q", "--detach", wt, instr0["base_sha"]])
            mutate(wt)
            got = git.git_write_tree_oid(wt)
            rep.eq(name, expect, "same" if got == o0 else "changes")

        case("삭제된 추적 파일: 트리에서 항목이 없다(OID 변화)", lambda p: os.unlink(os.path.join(p, "tools/mock/other/README.md")), "changes")
        case("미추적 파일 추가: 포함(OID 변화)", lambda p: write_text(os.path.join(p, "new.txt"), "u\n"), "changes")
        case("실행 권한 변경: 모드 100755(OID 변화)", lambda p: os.chmod(os.path.join(p, "tools/mock/other/README.md"), 0o755), "changes")
        case("심볼릭 링크: 120000, 대상 경로 문자열(OID 변화)", lambda p: os.symlink("tools/mock/other/README.md", os.path.join(p, "ln")), "changes")

        def excluded(p):
            for rel in ("target/a", "node_modules/b/c", "build/x.o", "dist/y", ".venv/z", "src/__pycache__/m.pyc", ".env", "id.pem", "id.key",
                        "my_secret.txt", "config_credentials.json"):
                os.makedirs(os.path.dirname(os.path.join(p, rel)) or p, exist_ok=True)
                write_text(os.path.join(p, rel), "1")
        case("제외 경로(target/ node_modules/ build/ dist/ .venv/ __pycache__/ .env *.pem *.key *credentials* *secret*): OID 불변", excluded, "same")
        case("빈 디렉터리: OID 불변", lambda p: os.makedirs(os.path.join(p, "empty_dir")), "same")

        def ignored(p):
            write_text(os.path.join(p, ".gitignore"), "*.log\n")
        wt_i = str(w.layout.root / "case_ignored")
        w.git(["worktree", "add", "-q", "--detach", wt_i, instr0["base_sha"]])
        ignored(wt_i)
        o_ign = git.git_write_tree_oid(wt_i)
        write_text(os.path.join(wt_i, "x.log"), "1")
        rep.eq(".gitignore 대상 파일은 트리에 들어가지 않는다(OID 불변)", o_ign, git.git_write_tree_oid(wt_i))

    # the handoff of a tree with all of those, end to end: stop check and preserve commit use the same function
    with cx.world() as w:
        writes = [("src/keep.py", "keep\n"), ("new_untracked.txt", "u\n"), ("run.sh", "#!/bin/sh\n"), ("target/out.bin", "o\n"),
                  ("node_modules/pkg/index.js", "n\n"), ("build/x.o", "b\n"), ("dist/y", "d\n"), (".venv/z", "v\n"),
                  (".env", "A=1\n"), ("id.pem", "k\n"), ("id.key", "k\n"), ("my_secret.txt", "s\n"), ("config_credentials.json", "c\n"),
                  ("src/__pycache__/m.pyc", "p\n"), ("debug.log", "ignored\n"), (".gitignore", "*.log\n")]
        extra = [{"op": "symlink", "path": "link", "target": "src/keep.py"}, {"op": "mkdir", "path": "empty_dir"},
                 {"op": "delete", "path": "tools/mock/handoff/README.md"}]
        go = str(w.layout.root / "go")
        script = [{"op": "write", "path": p, "content": c, **({"mode": 0o755} if p == "run.sh" else {})} for p, c in writes] + extra
        script += [{"op": "wait_file", "path": go}, {"op": "switch_signal"}, {"op": "sleep", "s": 3600}]
        instr, a, _ = w.lease_to_building(HANDOFF, script)
        w.wait_log(a, "delete")
        trigger(w, a, go)
        hr = w.task(HANDOFF)["handoff_record"]
        wip = hr["wip_commit_sha"]
        listing = {}
        for line in w.git(["ls-tree", "-r", "--full-tree", wip]).stdout.splitlines():
            meta, path = line.split("\t", 1)
            listing[path] = meta.split()[0]
        rep.eq("정지 확인의 tree OID == 보존 커밋의 tree OID", hr["quiescent_tree_oid"], tree_of(w, wip))
        rep.eq("커밋의 항목: 미추적 파일 포함, 실행 권한 100755, 심볼릭 링크 120000, .gitignore 포함",
               {"src/keep.py": "100644", "new_untracked.txt": "100644", "run.sh": "100755", "link": "120000", ".gitignore": "100644"},
               {k: listing.get(k) for k in ("src/keep.py", "new_untracked.txt", "run.sh", "link", ".gitignore")})
        rep.eq("심볼릭 링크는 대상 경로 문자열로 저장된다", "src/keep.py", w.git(["show", f"{wip}:link"]).stdout)
        rep.eq("삭제한 추적 파일은 커밋에 없다", False, "tools/mock/handoff/README.md" in listing)
        gone = [p for p in ("target/out.bin", "node_modules/pkg/index.js", "build/x.o", "dist/y", ".venv/z", ".env", "id.pem", "id.key",
                            "my_secret.txt", "config_credentials.json", "src/__pycache__/m.pyc", "debug.log", "empty_dir") if p in listing]
        rep.eq("제외 경로·무시 파일·빈 디렉터리 파일은 커밋에 없다", [], gone)
        rep.eq("원격 ref == 보존 커밋", wip, w.remote_refs().get(f"refs/heads/{instr['branch']}"))

    # a secret-shaped file stops the handoff: nothing is committed or pushed
    with cx.world() as w:
        instr, a, go = prep_handoff(w, task=OTHER, writes=[("src/keep.py", "keep\n"), ("notes/creds_note.txt", fake_secret())])
        refs0 = w.remote_refs()
        m = w.mark()
        trigger(w, a, go)
        js = w.journal()[m:]
        rep.eq("비밀값 모양 파일: handoff → returned(secret_detected, R-10)", ("returned", ["R-10"]), (w.state(OTHER), rets(js)))
        rep.eq("보존 커밋·푸시 0건(로컬 브랜치 없음, 원격 불변, 수락된 푸시 0)", (0, refs0, 0), (commits_on(w, instr), w.remote_refs(), len(accepted_pushes(w))))
        text = json.dumps(w.journal())
        rep.eq("비밀값 원문은 저장소 기록에 남지 않는다", False, "x" * 20 in text)
        rep.eq("새 임대 없음", 0, len(se(js, "issue_lease")))
    rep.not_proved("트리 해시 함수가 하나라는 점(다른 해시 정의 없음)은 정적 검사가 본다. 여기서는 같은 함수의 결과가 실제 git 객체와 같다는 것을 확인했다")


# =============================================================== R15
def gitdir_of(w, wt):
    return os.path.realpath(os.path.join(wt, w.git(["rev-parse", "--git-dir"], cwd=wt).stdout.strip()))


def userns_wrapper(cx_dir):
    """A mount namespace with a 64 KiB tmpfs for git's new objects: the disk fills up for real."""
    mnt = os.path.join(cx_dir, "smalldisk")
    script = 'mnt="$1"; shift; mkdir -p "$mnt" && mount -t tmpfs -o size=64k tmpfs "$mnt" && mkdir "$mnt/objects" && exec "$@"'
    return ["unshare", "-rm", "sh", "-c", script, "sh", mnt], mnt


def userns_available():
    try:
        res = subprocess.run(["unshare", "-rm", "sh", "-c", "mkdir -p /tmp/rv-probe-mnt && mount -t tmpfs -o size=64k tmpfs /tmp/rv-probe-mnt"],
                             capture_output=True, text=True, timeout=20)
        return res.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def blocked_invariants(rep, label, w, instr, a, js, refs0, attempts_event, attempts_n, revoked_tokens):
    t = w.task(HANDOFF)
    hr = t["handoff_record"]
    rep.eq(f"[{label}] 한도 안 재시도 뒤 handoff_blocked, 시도 횟수", ("handoff_blocked", attempts_n),
           (t["task_state"]["state"], hr["attempts"].get(attempts_event)))
    rep.eq(f"[{label}] 정지 사유(failure_log의 마지막 사건)", attempts_event, (hr["failure_log"] or [{}])[-1].get("event"))
    rep.eq(f"[{label}] 자격 세 가지 모두 회수 기록, 작업 트리 쓰기 금지 기록", (["builder_token", "builder_write_credential", "preserve_credential"], True),
           (sorted(hr["credentials_revoked"]), hr["worktree_readonly"]))
    store = read_json(w.layout.creds / "tokens.json")
    live = [k for k, v in store.items() if v["task_id"] == HANDOFF and not v.get("revoked_ns")]
    rep.eq(f"[{label}] 자격 저장소에 살아 있는 자격 0", [], live)
    from .adapters import token_sha
    reg = {}
    for rec in read_jsonl(w.remote / "rv" / "tokens.jsonl"):
        e = reg.setdefault(rec["token_sha"], {"name": rec.get("name"), "revoked": False})
        if rec["op"] == "revoke":
            e["revoked"] = True
    codes = [(name, reg.get(token_sha(token), {}).get("revoked")) for name, token in revoked_tokens.items() if token]
    rep.ok(f"[{label}] 원격의 자격 기록에서도 세 자격 모두 revoked(저장소 쪽 회수 확인)", bool(codes) and all(ok for _n, ok in codes), codes)
    rep.eq(f"[{label}] 작업 트리 쓰기 금지가 실제로 유지된다", True, not os.access(instr["worktree"], os.W_OK))
    rep.eq(f"[{label}] 새 임대·봉투 0: 세대 1, issue_lease 0, 지시 봉투 하나뿐", (1, 0, 1), (t["lease_generation"], len(se(js, "issue_lease")), len(sent_of(w, HANDOFF))))
    m = w.mark()
    w.restart().result
    w.tick().result
    rep.eq(f"[{label}] 재시작·시간 경과로는 재개되지 않는다(recovery_decision 전)", ([], "handoff_blocked"), (tr(w.journal()[m:]), w.state(HANDOFF)))


def tokens_now(w):
    store = read_json(w.layout.creds / "tokens.json")
    return {k.split("|")[0]: v["token"] for k, v in store.items() if v["task_id"] == HANDOFF}


def r15(rep, cx):
    def run_case(label, event, attempts_n, inject, recover, resume_stage, drain_kw=None, setup=None, wait_extra=None):
        with cx.world() as w:
            instr, a, go = prep_handoff(w)
            if setup:
                setup(w, instr)
            inject(w, instr)
            refs0 = w.remote_refs()
            m = w.mark()
            res = trigger(w, a, go, **(drain_kw(w) if drain_kw else {}))
            js = w.journal()[m:]
            blocked_invariants(rep, label, w, instr, a, js, refs0, event, attempts_n, tokens_now(w))
            commits_before = commits_on(w, instr)
            recover(w, instr)
            m = w.mark()
            w.event("recovery_decision", HANDOFF, {"recovery_ref": "REC-R15", "action": "retry"}).result
            js = w.journal()[m:]
            t = w.task(HANDOFF)
            phases = [r["args"]["value"] for r in js if r["kind"] == "side_effect_record" and r["id"] == "set_handoff_field"
                      and r["args"]["field"] == "phase"][:1]
            rep.eq(f"[{label}] 복구: recovery_decision 뒤 {resume_stage}부터 재개해 끝낸다(새 임대, 세대 2)", ([resume_stage], "leased", 2),
                   (phases, t["task_state"]["state"], t["lease_generation"]))
            rep.eq(f"[{label}] 복구 뒤 보존: 커밋 1개, tree == quiescent_tree_oid, 원격 ref == WIP",
                   (1, t["handoff_record"]["quiescent_tree_oid"], t["handoff_record"]["wip_commit_sha"]),
                   (commits_on(w, instr), tree_of(w, t["handoff_record"]["wip_commit_sha"]), w.remote_refs().get(f"refs/heads/{instr['branch']}")))
            if resume_stage == "preserve_remote":
                rep.eq(f"[{label}] 복구: 푸시만 다시 했다(새 커밋 없음)", commits_before, commits_on(w, instr))
            return w

    def lock_path(w, instr):
        return os.path.join(gitdir_of(w, instr["worktree"]), "index.lock")

    run_case("index.lock(남은 잠금 파일, 소유 프로세스 없음)", "index_lock", 4,
             lambda w, i: open(lock_path(w, i), "w").close(), lambda w, i: os.unlink(lock_path(w, i)), "isolate")

    holders = []

    def hold(w, i):
        p = lock_path(w, i)
        holders.append(subprocess.Popen([sys.executable, "-I", "-c", f"import time;f=open({p!r},'w');time.sleep(600)"],
                                        start_new_session=True))
        deadline = time.time() + 10
        while not os.path.exists(p) and time.time() < deadline:
            time.sleep(0.05)

    def release(w, i):
        for h in holders:
            h.kill()
            h.wait()
        with __import__("contextlib").suppress(FileNotFoundError):
            os.unlink(lock_path(w, i))
    run_case("index.lock(소유 프로세스가 살아 있음)", "index_lock", 4, hold, release, "isolate")

    if userns_available():
        wrapper_holder = {}

        def big_file(w, instr):
            with open(os.path.join(instr["worktree"], "big.bin"), "wb") as f:
                f.write(os.urandom(300_000))

        def dkw(w):
            wrapper, mnt = userns_wrapper(str(w.layout.root))
            return {"wrapper": wrapper, "git_env": [f"GIT_OBJECT_DIRECTORY={mnt}/objects",
                                                    f"GIT_ALTERNATE_OBJECT_DIRECTORIES={w.layout.clone}/.git/objects"]}
        run_case("가득 찬 디스크(64 KiB tmpfs 마운트에 새 git 객체)", "disk_full", None, lambda w, i: big_file(w, i), lambda w, i: None,
                 "isolate", drain_kw=dkw)
    else:
        rep.unconfirmed("[가득 찬 디스크] 제한 마운트(user namespace + tmpfs)를 만들 수 없는 호스트", "unshare -rm 마운트가 실패했다")

    run_case("네트워크 차단(닫힌 포트로 간 원격 주소)", "preserve_push_failed", 4, lambda w, i: None, lambda w, i: None, "preserve_remote",
            drain_kw=lambda w: {"net_block": True})

    def force(w, i):
        (w.remote / "rv" / "force_reject").write_text(json.dumps({"reason": "permission_denied"}))
    run_case("권한 거부(원격이 보존 자격의 푸시를 거부)", "preserve_push_failed", 1, force,
             lambda w, i: (w.remote / "rv" / "force_reject").unlink(), "preserve_remote")

    def protect(w, i):
        (w.remote / "rv" / "extra_protected.json").write_text(json.dumps(["^refs/heads/task/T-MOCK-HANDOFF-"]))
    run_case("보호 브랜치 거부(원격이 그 브랜치를 보호)", "preserve_push_failed", 1, protect,
             lambda w, i: (w.remote / "rv" / "extra_protected.json").unlink(), "preserve_remote")
    rep.not_proved("원격 푸시 실패 네 가지 중 '네트워크 차단'은 닫힌 로컬 포트로 간 주소이고 '권한·보호 규칙 거부'는 hook의 시험용 제어 파일이 만든 거부다. 실제 호스트의 거부 응답 형식은 확인하지 못했다",
                   "'가득 찬 디스크'는 새 git 객체가 쓰이는 디렉터리를 64 KiB tmpfs로 바꾼 것이다(같은 프로세스의 마운트 네임스페이스에서만). 저장소 전체가 찬 경우의 다른 실패 지점은 보지 않았다")


# =============================================================== R16
POINTS = [("stop 단계", "handoff:stop:start"), ("isolate 단계", "handoff:isolate:start"),
          ("confirm_quiescent 단계", "handoff:confirm_quiescent:start"), ("preserve 단계(로컬 커밋 전)", "handoff:preserve:start"),
          ("로컬 커밋 직후·기록 전", "handoff:preserve:after_local_commit_unrecorded"),
          ("로컬 커밋 기록 뒤·푸시 전", "handoff:preserve:after_local_commit_recorded"),
          ("푸시 직후·기록 전", "handoff:preserve:after_push_unrecorded"),
          ("issue_next_lease 단계(토큰 폐기 뒤·다음 발급 전)", "handoff:issue_next_lease:start")]


def preserve_issues(w):
    return len([e for e in w.cred_log() if e["op"] == "issue" and e["name"] == "preserve_credential"])


def r16(rep, cx):
    for label, point in POINTS:
        with cx.world() as w:
            instr, a, go = prep_handoff(w)
            m = w.mark()
            res = trigger(w, a, go, die_at=[point])
            rep.ok(f"[{label}] 실제 데몬 프로세스가 {point}에서 SIGKILL로 죽었다", res.killed, res.rc)
            before = w.task(HANDOFF)["handoff_record"]["phase"]
            res = w.restart()
            js = w.journal()[m:]
            t = w.task(HANDOFF)
            hr = t["handoff_record"]
            rep.eq(f"[{label}] 재시작 사건이 한 번 기록되고 phase부터 재개되어 완료(세대 2, restart_count 1, remote_pushed)",
                   (True, "leased", 2, 1, "remote_pushed"),
                   (res.ok, t["task_state"]["state"], t["lease_generation"], hr["restart_count"], hr["preservation_state"]))
            rep.eq(f"[{label}] 세대는 마지막 issue_lease 한 번만 바뀌고 새 세대 지시 봉투는 하나", (1, [2]),
                   (len(se(js, "issue_lease")), [s["lease_generation"] for s in sent_of(w, HANDOFF) if s["lease_generation"] == 2]))
            wip = hr["wip_commit_sha"]
            rep.eq(f"[{label}] 커밋 1개, 원격이 수락한 푸시 1건(이미 있는 것은 tree OID·ref로 확인해 다시 하지 않음)", (1, 1),
                   (commits_on(w, instr), len(accepted_pushes(w))))
            rep.eq(f"[{label}] 원격 ref == 보존 커밋, 커밋 tree == quiescent_tree_oid", (wip, hr["quiescent_tree_oid"]),
                   (w.remote_refs().get(f"refs/heads/{instr['branch']}"), tree_of(w, wip)))
            store = read_json(w.layout.creds / "tokens.json")
            rep.eq(f"[{label}] 쓰기 금지 유지, 보존 자격 회수, preserve_credential 발급 2회 이하(재발급은 1회까지)",
                   (True, True, True), (hr["worktree_readonly"], all(v.get("revoked_ns") for k, v in store.items() if k.startswith("preserve_credential")),
                                        preserve_issues(w) <= 2))

    # a second restart inside the same handoff exceeds daemon_restart_during_handoff = 1
    with cx.world() as w:
        instr, a, go = prep_handoff(w)
        trigger(w, a, go, die_at=["handoff:confirm_quiescent:start"])
        res = w.restart(die_at=["handoff:preserve:start"])
        rep.ok("[두 번째 재시작] 첫 재시작도 인계 도중(preserve 시작)에 실제로 죽었다", res.killed, res.rc)
        issues_before = preserve_issues(w)
        m = w.mark()
        w.restart().result
        js = w.journal()[m:]
        t = w.task(HANDOFF)
        hr = t["handoff_record"]
        rep.eq("[두 번째 재시작] 한도 초과: handoff_blocked", [("handoff", "handoff_blocked", "daemon_restart_during_handoff")], tr(js))
        rep.eq("[두 번째 재시작] 자격 전부 회수·쓰기 금지·issue_lease 0·새 봉투 0", (["builder_token", "builder_write_credential", "preserve_credential"], True, 0, 1),
               (sorted(hr["credentials_revoked"]), hr["worktree_readonly"], len(se(js, "issue_lease")), len(sent_of(w, HANDOFF))))
        rep.eq("[두 번째 재시작] preserve_credential 발급은 더 늘지 않았다(재발급 1회 한도)", issues_before, preserve_issues(w))
        rep.eq("[두 번째 재시작] 쓰기 금지가 실제로 유지된다", True, not os.access(instr["worktree"], os.W_OK))

    # the phase cannot be read: stop instead of guessing
    with cx.world() as w:
        instr, a, go = prep_handoff(w)
        trigger(w, a, go, die_at=["handoff:confirm_quiescent:start"])
        w.tamper(lambda d: d["tasks"][HANDOFF]["handoff_record"].update(phase=None))
        m = w.mark()
        w.restart().result
        js = w.journal()[m:]
        rep.eq("[phase 확인 불가] handoff_blocked, issue_lease 0, 세대 불변", ([("handoff", "handoff_blocked", "daemon_restart_during_handoff")], 0, 1),
               (tr(js), len(se(js, "issue_lease")), w.task(HANDOFF)["lease_generation"]))
    rep.not_proved("재시작 시점은 데몬 코어의 fault 지점(SIGKILL로 죽는 위치)이다. 지점 사이에서 임의 시각에 죽는 경우는 R18의 저장 지점 훑기와 같은 방식으로만 보았다")
