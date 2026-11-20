"""전체 Windows 빌드의 교체 경계를 실제 PowerShell과 DB 없는 빌드 대역으로 검증한다."""

from importlib.metadata import version
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows package integration")


@pytest.fixture(scope="module")
def fake_uv(tmp_path_factory):
    folder = tmp_path_factory.mktemp("package_compiler")
    compiler = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    if not compiler.is_file():
        pytest.skip("C# fixture compiler unavailable")
    source = folder / "BuildFixture.cs"
    source.write_text(
        r'''using System;
using System.IO;
using System.Reflection;
using System.Text;
class BuildFixture {
    static string Value(string[] args, string key) { return args[Array.IndexOf(args, key) + 1]; }
    static bool Has(string[] args, string key) { return Array.IndexOf(args, key) >= 0; }
    static int Main(string[] args) {
        Console.OutputEncoding = new UTF8Encoding(false);
        string self = Assembly.GetExecutingAssembly().Location;
        File.AppendAllText(Environment.GetEnvironmentVariable("PACKAGE_TRACE"),
            Path.GetFileName(self) + "\0" + String.Join("\0", args) + "\n", new UTF8Encoding(false));
        if (Path.GetFileName(self) == "SETRON_DB_SETUP.exe") {
            if (args.Length != 1 || args[0] != "--validate-schema") return 91;
            if (Environment.GetEnvironmentVariable("PACKAGE_FAIL") == "validate") {
                Console.WriteLine("FIXTURE_FAIL_validate"); return 24;
            }
            return 0;
        }
        if (args.Length > 0 && args[0] == "sync") return 0;
        if (Has(args, "pyinstaller")) {
            if (Environment.GetEnvironmentVariable("PACKAGE_FAIL") == "gui") {
                Console.WriteLine("FIXTURE_FAIL_gui"); return 22;
            }
            string output = Path.Combine(Value(args, "--distpath"), "SETRON");
            Directory.CreateDirectory(Path.Combine(output, "_internal"));
            File.WriteAllText(Path.Combine(output, "SETRON.exe"), "new-gui");
            File.WriteAllText(Path.Combine(output, "_internal", "runtime.dll"), "new-runtime");
            return 0;
        }
        if (Has(args, "python") && Has(args, "--output-dir")) {
            string output = Value(args, "--output-dir");
            Directory.CreateDirectory(output);
            File.Copy(self, Path.Combine(output, "SETRON_DB_SETUP.exe"));
            if (Environment.GetEnvironmentVariable("PACKAGE_FAIL") == "helper") {
                Console.WriteLine("FIXTURE_FAIL_helper"); return 23;
            }
            Directory.CreateDirectory(Path.Combine(output, "_internal", "database"));
            File.WriteAllText(Path.Combine(output, "_internal", "database", "schema_mysql5619.sql"), "CREATE TABLE fixture (id INT);");
            File.Copy(Path.Combine(Environment.CurrentDirectory, "prepare_schema.bat"),
                Path.Combine(output, "prepare_schema.bat"));
            return 0;
        }
        return 92;
    }
}
''', encoding="utf-8-sig")
    exe = folder / "uv.exe"
    subprocess.run([str(compiler), "/nologo", "/target:exe", f"/out:{exe}", str(source)],
                   capture_output=True, check=True, timeout=30)
    return exe


@pytest.fixture
def package(tmp_path, fake_uv):
    root = tmp_path / "격리 저장소"
    (root / "packaging").mkdir(parents=True)
    shutil.copyfile(ROOT / "packaging/build_windows.ps1", root / "packaging/build_windows.ps1")
    (root / "setron.env.example").write_bytes(b"new-example")
    (root / "prepare_schema.bat").write_bytes((ROOT / "prepare_schema.bat").read_bytes())
    tools = tmp_path / "tools"
    tools.mkdir()
    shutil.copyfile(fake_uv, tools / "uv.exe")
    output = tmp_path / "한글 배포 폴더" / "SETRON 출력"
    output.mkdir(parents=True)
    for name, content in {
        "SETRON.exe": b"old-gui", "SETRON_DB_INIT.exe": b"old-helper",
        "prepare_demo_db.bat": b"old-bat", "setron.env.example": b"old-example",
        "setron.env": b"fixture-only-local-config", "SETRON_DB.sql": b"approved-snapshot\n",
        "_internal/old.dll": b"old-runtime", "backups/nested/original.sql": b"saved-db-backup",
        "database/preserved.sql": b"user-sql", "database/SETRON_DB.sql": b"legacy-duplicate",
        "user notes.txt": b"user-data",
    }.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (output / "backups/empty").mkdir()
    dump = tmp_path / "입력 자료.sql"
    dump.write_bytes((output / "SETRON_DB.sql").read_bytes())
    return SimpleNamespace(root=root, output=output, dump=dump, tools=tools, temp=tmp_path)


def tree_bytes(folder):
    return {str(path.relative_to(folder)): path.read_bytes() for path in folder.rglob("*") if path.is_file()}


def build(package, *, failure=None, rename_failures=(), output=None, omit_output=False, reuse=False):
    output = output or package.output
    runner = package.temp / "RunBuild.ps1"
    # 실행 중인 사용자 앱에는 관여하지 않도록 프로세스 조회를 대역으로 바꾼다.
    script = '''param($BuildScript, $RepositoryRoot, $OutputDir, $ReuseGuiFrom)
$ErrorActionPreference = "Stop"
function Get-Process { @() }
'''
    if rename_failures:
        failures = ",".join(str(value) for value in rename_failures)
        script += '''. $BuildScript -OutputDir $OutputDir
$script:ActualMove = ${function:Move-PackageDirectory}
$script:MoveCount = 0
function Move-PackageDirectory($source, $destination) {
    $script:MoveCount++
    if ($script:MoveCount -in @(''' + failures + ''')) { throw "injected publish rename failure" }
    & $script:ActualMove $source $destination
}
Invoke-WindowsPackageBuild -RepositoryRoot $RepositoryRoot -OutputDir $OutputDir
'''
    else:
        script += ('& $BuildScript\n' if omit_output else
                   '& $BuildScript -OutputDir $OutputDir -ReuseGuiFrom $ReuseGuiFrom\n')
    runner.write_text(script, encoding="utf-8-sig")
    env = os.environ.copy()
    for name in tuple(env):
        if name.startswith(("SETRON_DB_", "SETRON_AI_", "OPENAI_", "PACKAGE_")):
            env.pop(name)
    env["PATH"] = str(package.tools) + os.pathsep + env["PATH"]
    env["PACKAGE_TRACE"] = str(package.temp / "build_trace.txt")
    if failure:
        env["PACKAGE_FAIL"] = failure
    return subprocess.run([
        "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(runner),
        "-BuildScript", str(package.root / "packaging/build_windows.ps1"),
        "-RepositoryRoot", str(package.root), "-OutputDir", str(output),
        "-ReuseGuiFrom", str(package.output) if reuse else "",
    ], cwd=package.temp, env=env, capture_output=True, timeout=40)


def test_full_build_preserves_user_data_and_replaces_runtime_without_merging(package):
    previous = tree_bytes(package.output)
    result = build(package)
    assert result.returncode == 0, result.stdout + result.stderr
    for name in ("setron.env", "backups\\nested\\original.sql", "database\\preserved.sql", "user notes.txt"):
        assert (package.output / name).read_bytes() == previous[name]
    assert (package.output / "backups/empty").is_dir()
    assert (package.output / "SETRON.exe").read_bytes() == b"new-gui"
    assert (package.output / "SETRON_DB_SETUP.exe").read_bytes() == (package.tools / "uv.exe").read_bytes()
    assert (package.output / "prepare_schema.bat").read_bytes() == (ROOT / "prepare_schema.bat").read_bytes()
    archive = package.output.parent / "SETRON-demo-archive"
    for name in ("SETRON_DB_INIT.exe", "prepare_demo_db.bat", "SETRON_DB.sql", "database\\SETRON_DB.sql"):
        assert not (package.output / name).exists()
        assert (archive / name).read_bytes() == previous[name]
    assert (package.output / "_internal/runtime.dll").read_bytes() == b"new-runtime"
    assert not (package.output / "_internal/old.dll").exists()
    trace = (package.temp / "build_trace.txt").read_text(encoding="utf-8").splitlines()
    assert len(trace) == 4 and trace[-1] == "SETRON_DB_SETUP.exe\0--validate-schema"
    helper_args = trace[2].split("\0")
    assert "packaging\\build_schema_db.py" in helper_args and "--dump" not in helper_args
    assert not list(package.output.parent.glob("setron-stage-*"))


@pytest.mark.parametrize("failure", ["gui", "helper", "validate"])
def test_failed_build_or_validation_leaves_original_bundle_unchanged(package, failure):
    previous = tree_bytes(package.output)
    result = build(package, failure=failure)
    assert result.returncode != 0
    assert ("FIXTURE_FAIL_" + failure).encode() in result.stdout
    assert tree_bytes(package.output) == previous
    assert not list(package.output.parent.glob("setron-stage-*"))


def test_publish_second_rename_failure_restores_original_bundle(package):
    previous = tree_bytes(package.output)
    result = build(package, rename_failures=(2,))
    assert result.returncode != 0
    assert b"injected publish rename failure" in result.stderr
    assert tree_bytes(package.output) == previous
    assert not list(package.output.parent.glob("setron-stage-*"))


def test_failed_rollback_retains_original_bundle_in_recovery_stage(package):
    previous = tree_bytes(package.output)
    result = build(package, rename_failures=(2, 3))
    assert result.returncode != 0
    stages = list(package.output.parent.glob("setron-stage-*"))
    assert len(stages) == 1
    assert not package.output.exists()
    assert tree_bytes(stages[0] / "previous-SETRON") == previous


def test_different_existing_archive_aborts_before_any_rename(package):
    archive = package.output.parent / "SETRON-demo-archive"
    archive.mkdir()
    (archive / "SETRON_DB.sql").write_bytes(b"different-user-snapshot")
    previous = tree_bytes(package.output)
    result = build(package)
    assert result.returncode != 0
    assert b"SETRON_DB.sql" in result.stderr
    assert len((package.temp / "build_trace.txt").read_text(encoding="utf-8").splitlines()) == 3
    assert tree_bytes(package.output) == previous
    assert not list(package.output.parent.glob("setron-stage-*"))


def test_default_output_is_repository_dist_without_demo_data(package):
    result = build(package, omit_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    output = package.root / "dist/SETRON"
    assert not (output / "SETRON_DB.sql").exists()
    assert (output / "SETRON_DB_SETUP.exe").exists()
    assert (output / "SETRON.exe").read_bytes() == b"new-gui"
    assert not (output / "setron.env").exists()


def test_explicit_gui_reuse_preserves_gui_and_excludes_demo_files(package):
    result = build(package, reuse=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (package.output / "SETRON.exe").read_bytes() == b"old-gui"
    assert (package.output / "_internal/old.dll").read_bytes() == b"old-runtime"
    assert (package.output / "setron.env").read_bytes() == b"fixture-only-local-config"
    assert (package.output / "SETRON_DB_SETUP.exe").exists()
    assert not (package.output / "SETRON_DB_INIT.exe").exists()
    assert not (package.output / "database/SETRON_DB.sql").exists()
    trace = (package.temp / "build_trace.txt").read_text(encoding="utf-8")
    assert "pyinstaller" not in trace


@pytest.mark.parametrize("relative", ["src/target", ".git/target", "packaging/target"])
def test_output_inside_repository_source_or_metadata_is_rejected_before_build(package, relative):
    output = package.root / relative
    output.mkdir(parents=True)
    (output / "keep.txt").write_bytes(b"repository-data")
    result = build(package, output=output)
    assert result.returncode != 0
    assert tree_bytes(output) == {"keep.txt": b"repository-data"}
    assert not (package.temp / "build_trace.txt").exists()


def test_nonempty_arbitrary_output_is_not_treated_as_a_windows_bundle(package):
    output = package.temp / "unrelated-folder"
    (output / "_internal").mkdir(parents=True)
    (output / "_internal/keep.txt").write_bytes(b"unrelated-user-data")
    previous = tree_bytes(output)
    result = build(package, output=output)
    assert result.returncode != 0
    assert tree_bytes(output) == previous
    assert not list(output.parent.glob("setron-stage-*"))


def test_preserved_junction_is_rejected_without_following_outside_target(package):
    outside = package.temp / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_bytes(b"outside-must-not-change")
    junction = package.output / "backups/linked"
    subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(outside)],
                   check=True, capture_output=True)
    try:
        result = build(package)
        assert result.returncode != 0
        assert (package.output / "SETRON.exe").read_bytes() == b"old-gui"
        assert (outside / "keep.txt").read_bytes() == b"outside-must-not-change"
        assert junction.is_dir()
    finally:
        os.rmdir(junction)


def test_spec_builds_only_gui_and_never_creates_obsolete_initializer(monkeypatch):
    calls = []
    hooks = SimpleNamespace(collect_data_files=lambda *_: [], collect_submodules=lambda *_: [],
                            copy_metadata=lambda *_: [("metadata", "setron.dist-info")])
    monkeypatch.setitem(sys.modules, "PyInstaller.utils.hooks", hooks)

    def analysis(scripts, **kwargs):
        calls.append(("analysis", scripts, kwargs))
        return SimpleNamespace(scripts=[("entry", scripts[0], "PYSOURCE")], pure=[], binaries=[], datas=[])

    def exe(*args, **kwargs):
        calls.append(("exe", args, kwargs))
        return "gui-executable"

    def collect(*args, **kwargs):
        calls.append(("collect", args, kwargs))

    runpy.run_path(str(ROOT / "packaging/setron.spec"), init_globals={
        "SPECPATH": str(ROOT / "packaging"), "Analysis": analysis,
        "PYZ": lambda *_: "pyz", "EXE": exe, "COLLECT": collect,
    })
    analyses = [value for kind, value, _ in calls if kind == "analysis"]
    assert len(analyses) == 1 and len(analyses[0]) == 1
    assert Path(analyses[0][0]).name == "run_setron.py"
    executables = [kwargs for kind, _, kwargs in calls if kind == "exe"]
    resource = executables[0].pop("version")
    strings = {field.name: field.val for field in resource.kids[0].kids[0].kids}
    assert strings["ProductVersion"] == strings["FileVersion"] == version("setron")
    assert strings["OriginalFilename"] == "SETRON.exe"
    assert executables == [{"exclude_binaries": True, "name": "SETRON", "console": False,
                            "icon": str(ROOT / "src/setron/ui/assets/setron-window-icon.ico")}]
