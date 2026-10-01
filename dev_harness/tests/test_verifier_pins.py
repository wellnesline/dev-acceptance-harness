"""Verifier pinning: in-flight jobs keep the verifier they started with.

Real LangGraph, real OpenSpec CLI and the real gate run in a throwaway copy of
the shared verifier set, driven through the same job CLI the orchestrators use.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ops_harness import verifier_pins  # noqa: E402
from ops_harness.workflow import WorkflowRuntime  # noqa: E402

PROFILE = {"change": "safe-relative-output", "sample": False, "source_paths": ["app/artifact_path.py"],
           "test_paths": ["app/tests/test_artifact_path.py"], "runner": "unittest", "cwd": "app",
           "timeout_seconds": 60}
REGISTRY = {"schema_version": 1, "services": [], "workflows": []}
# Every shared file a job's evidence or fingerprint depended on before pinning.
SHARED_UPDATES = ("dev_harness/gate.py", "dev_harness/unittest_runner.py", "integrations/visual_workflow/policy.py",
                  "integrations/visual_workflow/viewer.py", "ops_harness/workflow.py", "ops_harness/workflow_actions.py",
                  "ops_harness/development.py", "ops_harness/workflow_cli.py", "scripts/qa_memory_md_lint.py")
CLI = ("import sys; sys.path.insert(0, sys.argv[1]); from ops_harness.workflow_cli import main; "
       "raise SystemExit(main(sys.argv[3:], root=sys.argv[1], legacy_pin=sys.argv[2] or None))")


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    base = tmp_path_factory.mktemp("template") / "repo"
    for relative, source in verifier_pins.members(ROOT).items():
        target = base / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    (base / "config/ops_harness.json").write_text(json.dumps(REGISTRY), encoding="utf-8")
    shutil.copytree(ROOT / "dev_harness/project/openspec", base / "openspec")
    (base / "app/tests").mkdir(parents=True)
    shutil.copyfile(ROOT / "dev_harness/project/artifact_path.py", base / "app/artifact_path.py")
    shutil.copyfile(ROOT / "dev_harness/project/tests/test_artifact_path.py", base / "app/tests/test_artifact_path.py")
    (base / "dev_harness/profiles.json").write_text(json.dumps({"profiles": {"demo": PROFILE}}), encoding="utf-8")
    policy = base / "dev_harness/workflow_delivery_policy.json"
    data = json.loads(policy.read_text(encoding="utf-8"))
    data["historical_profiles"]["demo"] = "safe-relative-output"
    policy.write_text(json.dumps(data, indent=2), encoding="utf-8")
    verifier_pins.create(base, base / ".harness")  # copied with each repo; later creates only re-verify
    return base


@pytest.fixture
def repo(template, tmp_path):
    # Hard links keep each test's repository cheap; every edit below replaces files instead of
    # writing through a link, so tests never alter the shared template.
    target = tmp_path / "repo"
    for current, _dirs, names in os.walk(template):
        destination = target / Path(current).relative_to(template)
        destination.mkdir(parents=True, exist_ok=True)
        for name in names:
            try:
                os.link(Path(current) / name, destination / name)
            except OSError:
                shutil.copy2(Path(current) / name, destination / name)
    return target


def cli(root, *args, legacy_pin=""):
    proc = subprocess.run([sys.executable, "-B", "-X", "utf8", "-c", CLI, str(root), legacy_pin, *map(str, args)],
                          cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=600)
    out = json.loads(proc.stdout) if proc.stdout.strip() else None
    return proc.returncode, out, proc.stderr


def request_file(root, name):
    path = root / ("request-" + name + ".json")
    path.write_text(json.dumps({
        "workflow": "software-development", "objective": "Keep the sample behavior verified",
        "checks": ["registry.paths"], "authorization_scope": "local test only",
        "criteria": [{"id": "behavior", "description": "Specification implemented"}],
        "artifacts": [{"path": "evidence/" + name + ".json", "kind": "openspec",
                       "change": "safe-relative-output", "profile": "demo"}]}), encoding="utf-8")
    return path


def start_and_submit(root, name):
    code, state, err = cli(root, "start", "--job-id", name, "--request", request_file(root, name))
    assert code == 3 and state["status"] == "awaiting_work", err
    assert state["verifier_pin"] and verifier_pins.pin_path(root / ".harness", state["verifier_pin"]).is_dir()
    code, made, err = cli(root, "gate", name)
    assert code == 0, err
    assert made["verifier_pin"] == state["verifier_pin"]
    submission = root / ("submission-" + name + ".json")
    submission.write_text(json.dumps({"token": state["token"], "worker_id": "builder",
                                      "artifacts": [{"path": a["path"], "sha256": a["sha256"]} for a in made["artifacts"]]}),
                          encoding="utf-8")
    code, state, err = cli(root, "submit", name, "--submission", submission)
    return code, state, err


def approve(root, state):
    review = root / ("review-" + state["job_id"] + ".json")
    review.write_text(json.dumps({"token": state["token"], "reviewer_id": "independent-reviewer", "decision": "approve",
                                  "criteria": [{"id": c["id"], "passed": True, "note": "Checked against fresh evidence"}
                                               for c in state["criteria"]]}), encoding="utf-8")
    return cli(root, "review", state["job_id"], "--review", review)


def append(path, text):
    content = Path(path).read_bytes() + text.encode("utf-8")
    os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
    os.unlink(path)
    Path(path).write_bytes(content)


def rewrite(path, text):
    os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
    os.unlink(path)
    Path(path).write_text(text, encoding="utf-8")


def update_shared_verifier(root):
    """What a verifier maintainer does while other jobs are in flight."""
    for relative in SHARED_UPDATES:
        append(root / relative, "\n# shared verifier updated\n")
    for relative in ("dev_harness/workflow_delivery_policy.json", "dev_harness/tools/package-lock.json",
                     "config/ops_harness.json"):
        append(root / relative, "\n")
    append(next((root / "dev_harness/tools/node_modules/@fission-ai/openspec/dist").rglob("*.js")), "\n// updated\n")
    profiles = root / "dev_harness/profiles.json"
    data = json.loads(profiles.read_text(encoding="utf-8"))
    data["profiles"]["someone-else"] = {**PROFILE, "change": "other-change"}
    rewrite(profiles, json.dumps(data))


def test_pin_is_content_addressed_read_only_and_tamper_evident(repo):
    state = repo / "fresh-state"
    first = verifier_pins.create(repo, state)
    assert verifier_pins.create(repo, state) == first
    pin = verifier_pins.pin_path(state, first)
    assert hashlib.sha256((pin / "manifest.json").read_bytes()).hexdigest() == first
    gate = pin / "files/dev_harness/gate.py"
    assert not os.access(gate, os.W_OK)
    assert set(verifier_pins.verify(pin)) == set(verifier_pins.members(repo))
    append(gate, "# tampered\n")
    with pytest.raises(verifier_pins.PinError):
        verifier_pins.verify(pin)
    with pytest.raises(verifier_pins.PinError):
        verifier_pins.create(repo, state)  # an existing pin is re-verified, never silently trusted or replaced


def test_extra_file_and_manifest_edit_are_detected(repo):
    state = repo / ".harness"
    pin = verifier_pins.pin_path(state, verifier_pins.create(repo, state))
    planted = pin / "files/ops_harness/__pycache__/workflow.cpython-312.pyc"
    planted.parent.mkdir()
    planted.write_bytes(b"compiled bypass")
    with pytest.raises(verifier_pins.PinError):
        verifier_pins.verify(pin, only=("ops_harness",))
    shutil.rmtree(planted.parent)
    verifier_pins.verify(pin)
    append(pin / "manifest.json", " ")
    with pytest.raises(verifier_pins.PinError):
        verifier_pins.verify(pin)


def test_shared_verifier_update_does_not_stale_in_flight_job(repo):
    code, state, err = start_and_submit(repo, "inflight")
    assert code == 3 and state["status"] == "awaiting_review", err
    pin = state["verifier_pin"]
    update_shared_verifier(repo)
    assert verifier_pins.manifest(repo)[0] != pin, "the repository now holds a newer verifier"
    code, state, err = approve(repo, state)
    assert code == 0 and state["status"] == "completed", err
    assert state["verifier_pin"] == pin
    assert state["verification"]["checks"][0] == {"id": "verifier-pin", "passed": True,
                                                  "detail": "Pinned verifier " + pin + " matches its manifest"}
    # Only a new job uses the new version.
    code, fresh, err = cli(repo, "start", "--job-id", "next", "--request", request_file(repo, "next"))
    assert code == 3 and fresh["verifier_pin"] == verifier_pins.manifest(repo)[0] != pin, err


@pytest.mark.parametrize("change", ["source", "own-profile"])
def test_own_input_change_still_stales_the_job(repo, change):
    code, state, err = start_and_submit(repo, "own")
    assert code == 3 and state["status"] == "awaiting_review", err
    if change == "source":
        append(repo / "app/artifact_path.py", "\n# unreviewed edit\n")
    else:
        profiles = repo / "dev_harness/profiles.json"
        data = json.loads(profiles.read_text(encoding="utf-8"))
        data["profiles"]["demo"]["timeout_seconds"] = 61
        rewrite(profiles, json.dumps(data))
    code, state, err = approve(repo, state)
    assert state["status"] == "awaiting_work" and state["attempt"] == 2, err
    assert not state["verification"]["passed"]


def gate_hashes(root, pin):
    proc = subprocess.run([sys.executable, "-B", "-X", "utf8", str(pin / "files/dev_harness/gate.py"), "--root", str(root),
                           "--change", "safe-relative-output", "--profile", "demo"],
                          cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=300)
    report = json.loads(proc.stdout)
    assert report["status"] == "passed", report
    return report["artifact_hashes"]


def test_pinned_gate_binds_own_inputs_but_not_shared_files(repo):
    state = repo / ".harness"
    pin = verifier_pins.pin_path(state, verifier_pins.create(repo, state))
    before = gate_hashes(repo, pin)
    assert before["verifier-pin"] == pin.name
    update_shared_verifier(repo)
    assert gate_hashes(repo, pin) == before, "unrelated profiles and shared files are outside a pinned job's evidence"
    edits = {"app/tests/test_artifact_path.py": "\n# own test edit\n",
             "openspec/changes/safe-relative-output/design.md": "\nOwn change edit.\n",
             "openspec/config.yaml": "\n# workspace spec config\n"}
    for relative, text in edits.items():
        append(repo / relative, text)
        after = gate_hashes(repo, pin)
        assert after[relative] != before[relative], relative
        before = after


PLANTED = "import sys\nsys.modules.pop('argparse', None)\nraise SystemExit('planted module executed')\n"


@pytest.mark.parametrize("tamper", ["edit-gate", "plant-top-level-module", "edit-runtime"])
def test_modified_pin_cannot_pass_and_job_can_still_be_closed(repo, tamper):
    code, state, err = cli(repo, "start", "--job-id", "tamper", "--request", request_file(repo, "tamper"))
    pin = verifier_pins.pin_path(repo / ".harness", state["verifier_pin"])
    code, made, err = cli(repo, "gate", "tamper")
    assert code == 0, err
    if tamper == "edit-gate":
        append(pin / "files/dev_harness/gate.py", "\n# weakened\n")
    elif tamper == "plant-top-level-module":
        # Independent review: a module planted beside the pinned packages shadows the
        # standard library, because <pin>/files is first on the pinned process's sys.path.
        (pin / "files/argparse.py").write_text(PLANTED, encoding="utf-8")
    else:
        append(pin / "files/ops_harness/workflow.py", "\n# bypass\n")
    code, report, err = cli(repo, "pin", "tamper")
    assert code == 2 and report["intact"] is False, (report, err)
    submission = repo / "submission-tamper.json"
    submission.write_text(json.dumps({"token": state["token"], "worker_id": "builder",
                                      "artifacts": [{"path": a["path"], "sha256": a["sha256"]} for a in made["artifacts"]]}),
                          encoding="utf-8")
    code, out, err = cli(repo, "submit", "tamper", "--submission", submission)
    assert code == 2 and "was modified" in err and "planted module executed" not in err, err
    for command in ("continue", "gate"):
        code, out, err = cli(repo, command, "tamper")
        assert code == 2 and "was modified" in err, err
    code, state, err = cli(repo, "status", "tamper")
    assert state["status"] == "awaiting_work" and state["attempt"] == 1 and not state["verification"], err
    code, state, err = cli(repo, "cancel", "tamper")
    assert state["status"] == "cancelled", err


def test_pinned_verification_records_a_pin_modified_after_dispatch(repo):
    """Defense in depth: the pinned runtime re-verifies the whole pin before it verifies artifacts."""
    code, state, err = cli(repo, "start", "--job-id", "late", "--request", request_file(repo, "late"))
    pin = verifier_pins.pin_path(repo / ".harness", state["verifier_pin"])
    append(pin / "files/dev_harness/unittest_runner.py", "\n# weakened after dispatch\n")
    script = ("import sys, json; sys.path.insert(0, sys.argv[1]); from pathlib import Path; "
              "from ops_harness.workflow import WorkflowRuntime; r = WorkflowRuntime(Path(sys.argv[2])); "
              "s = r.inspect('late'); print(json.dumps(r._verified_evidence({'request': s['request'], "
              "'submission': {'artifacts': []}})))")
    proc = subprocess.run([sys.executable, "-I", "-B", "-c", script, str(pin / "files"), str(repo)], cwd=repo,
                          capture_output=True, text=True, encoding="utf-8", timeout=120)
    evidence = json.loads(proc.stdout)
    assert evidence["passed"] is False and evidence["checks"][0]["id"] == "verifier-pin", proc.stderr


def test_pin_cannot_be_swapped_mid_job(repo):
    code, state, err = cli(repo, "start", "--job-id", "bound", "--request", request_file(repo, "bound"))
    assert code == 3, err
    update_shared_verifier(repo)
    other = verifier_pins.pin_path(repo / ".harness", verifier_pins.create(repo, repo / ".harness"))
    proc = subprocess.run([sys.executable, "-I", "-B", "-X", "utf8", "-c",
                           "import sys; sys.path.insert(0, sys.argv[1]); from ops_harness.pinned_entry import main; "
                           "raise SystemExit(main(sys.argv[2:]))", str(other / "files"), str(repo), "continue", "bound"],
                          cwd=repo, capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert proc.returncode == 2 and "bound to verifier pin" in proc.stderr
    with pytest.raises(RuntimeError, match="bound to verifier pin"):
        WorkflowRuntime(repo).continue_job("bound")  # repository code cannot adopt a pinned job either
    code, again, err = cli(repo, "start", "--job-id", "bound", "--request", request_file(repo, "bound"))
    assert code == 2 and "already exists" in err
    assert cli(repo, "status", "bound")[1]["verifier_pin"] == state["verifier_pin"]


def test_unpinned_fingerprint_tracks_lockfile_spec_config_and_registry(tmp_path):
    for relative in ("dev_harness/gate.py", "dev_harness/unittest_runner.py", "dev_harness/tools/package-lock.json",
                     "openspec/config.yaml", "config/ops_harness.json", "dev_harness/profiles.json"):
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_text("{}", encoding="utf-8")
    runtime = WorkflowRuntime(tmp_path)
    previous = runtime.fingerprint()
    (tmp_path / "dev_harness/profiles.json").write_text('{"profiles": {"other": {}}}', encoding="utf-8")
    assert runtime.fingerprint() == previous
    for relative in ("dev_harness/tools/package-lock.json", "openspec/config.yaml", "config/ops_harness.json"):
        (tmp_path / relative).write_text('{"changed": true}', encoding="utf-8")
        assert runtime.fingerprint() != previous, relative
        previous = runtime.fingerprint()


def test_legacy_job_survives_cutover_on_frozen_runtime(repo):
    start = ("import sys, json; sys.path.insert(0, sys.argv[1]); from pathlib import Path; "
             "from ops_harness.workflow import WorkflowRuntime; "
             "s = WorkflowRuntime(Path(sys.argv[1])).start('legacy', json.loads(sys.argv[2])); print(s['token'])")
    (repo / "out").mkdir()
    request = {"workflow": "business-support", "objective": "Write hello", "checks": ["registry.paths"],
               "criteria": [{"id": "c1", "description": "Says hello"}],
               "artifacts": [{"path": "out/result.txt", "kind": "file", "contains": ["hello"]}]}
    token = subprocess.run([sys.executable, "-I", "-B", "-c", start, str(repo), json.dumps(request)], cwd=repo,
                           capture_output=True, text=True, timeout=120, check=True).stdout.strip()
    extra = {"ops_harness/pinned_entry.py": (ROOT / "scripts/ops/verifier_pin_legacy_entry.py").read_bytes(),
             "openspec/config.yaml": (repo / "openspec/config.yaml").read_bytes()}
    legacy = verifier_pins.create(repo, repo / ".harness", extra=extra)
    update_shared_verifier(repo)
    append(repo / "openspec/config.yaml", "\n# cutover edit\n")
    (repo / "out/result.txt").write_text("hello reader", encoding="utf-8")
    submission = repo / "submission-legacy.json"
    submission.write_text(json.dumps({"token": token, "worker_id": "builder", "artifacts": [
        {"path": "out/result.txt", "sha256": hashlib.sha256((repo / "out/result.txt").read_bytes()).hexdigest()}]}),
        encoding="utf-8")
    code, out, err = cli(repo, "submit", "legacy", "--submission", submission)
    assert code == 2 and "changed" in err, "without the frozen runtime the cutover would stale the job"
    code, state, err = cli(repo, "submit", "legacy", "--submission", submission, legacy_pin=legacy)
    assert code == 3 and state["status"] == "awaiting_review", err
    assert state["verifier_pin"] is None
