"""데이터 없이 관리 테이블만 생성하는 Windows 설치 도구를 만든다."""

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
NAME = "SETRON_DB_SETUP"


def schema_text() -> str:
    sys.path[:0] = [str(ROOT / "src"), str(ROOT / "database")]
    from init_schema import _split_sql, schema_statements
    original = (ROOT / "database/schema_mysql5619.sql").read_text(encoding="utf-8-sig")
    sql = ";\n\n".join(statement for statement in _split_sql(original)
                        if re.match(r"CREATE\s+TABLE\b", statement, re.I)) + ";\n"
    schema_statements(sql)
    return sql


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist/SETRON")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    sql = schema_text()
    with tempfile.TemporaryDirectory(prefix="setron-schema-build-") as temporary:
        stage = Path(temporary)
        schema = stage / "schema_mysql5619.sql"
        schema.write_text(sql, encoding="utf-8")
        separator = ";" if sys.platform == "win32" else ":"
        from windows_version import version_info

        resource = stage / "version.txt"
        resource.write_text(str(version_info(NAME)), encoding="utf-8")
        subprocess.run([
            sys.executable, "-m", "PyInstaller", "--onefile", "--console", "--name", NAME,
            "--version-file", str(resource),
            "--distpath", str(stage / "dist"), "--workpath", str(stage / "work"), "--specpath", str(stage),
            "--paths", str(ROOT / "src"), "--paths", str(ROOT / "database"),
            "--add-data", f"{schema}{separator}database",
            "--exclude-module", "pandas", "--exclude-module", "openai",
            "--exclude-module", "xlwings", "--exclude-module", "PySide6",
            str(ROOT / "database/init_schema.py"),
        ], cwd=ROOT, check=True)
        output.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(stage / "dist" / f"{NAME}.exe", output / f"{NAME}.exe")
        asset = output / "_internal/database/schema_mysql5619.sql"
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_text(sql, encoding="utf-8")
        batch = (ROOT / "prepare_schema.bat").read_text(encoding="ascii")
        (output / "prepare_schema.bat").write_bytes(
            batch.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n").encode("ascii"))
    print(output)


if __name__ == "__main__":
    main()
