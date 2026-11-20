# PyInstaller 설정: Windows 실행 파일 폴더(dist/SETRON)를 만든다 (Jira S15P31B106-77).
# 빌드: packaging/build_windows.ps1

from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

block_cipher = None

spec_dir = Path(SPECPATH).resolve()
sys.path.insert(0, str(spec_dir))
from windows_version import version_info

database_dir = spec_dir.parent / "database"
gui_script = spec_dir / "run_setron.py"
metadata_dir, metadata_target = copy_metadata("setron")[0]

analysis = Analysis(
    [str(gui_script)],
    pathex=[str(spec_dir.parent / "src")],
    datas=[
        (str(Path(metadata_dir) / "METADATA"), metadata_target),
        *collect_data_files("setron"),  # ui/assets의 아이콘·폰트
        (str(database_dir / "schema_mysql5619.sql"), "database"),
    ],
    # DB 드라이버와 최초 사용 시 불러오는 AI·Excel SDK도 배포 폴더에 포함한다.
    hiddenimports=["pymysql", "openai", "xlwings", *collect_submodules("sqlalchemy.dialects.mysql")],
    excludes=["pytest", "tkinter"],
    noarchive=False,
)
# 공통 런타임 훅은 유지하고 각 EXE에는 자기 시작 스크립트만 넣는다.
scripts = {Path(script[1]).resolve(): script for script in analysis.scripts}
runtime_hooks = [script for path, script in scripts.items() if path != gui_script]
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    [*runtime_hooks, scripts[gui_script]],
    [],
    exclude_binaries=True,
    name="SETRON",
    version=version_info("SETRON"),
    console=False,
    icon=str(spec_dir.parent / "src" / "setron" / "ui" / "assets" / "setron-window-icon.ico"),
)
# 빈 DB 스키마 설치 도구는 build_schema_db.py에서 별도 생성한다.
# PyInstaller also collects distribution metadata when it detects version("setron").
# Only METADATA is needed at runtime; editable install records contain local paths.
public_data = [
    entry for entry in analysis.datas
    if Path(entry[0]).parts[0] != metadata_target or Path(entry[0]).name == "METADATA"
]
coll = COLLECT(exe, analysis.binaries, public_data, name="SETRON")
