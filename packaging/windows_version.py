"""Build a Windows version resource from the installed project metadata."""

from importlib.metadata import version

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable,
    VarFileInfo, VarStruct, VSVersionInfo,
)


def version_info(executable: str) -> VSVersionInfo:
    release = version("setron")
    numeric = tuple(int(part) for part in release.split(".")) + (0,)
    strings = [
        StringStruct("ProductName", "SETRON"),
        StringStruct("ProductVersion", release),
        StringStruct("FileVersion", release),
        StringStruct("OriginalFilename", f"{executable}.exe"),
    ]
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=numeric, prodvers=numeric),
        kids=[
            StringFileInfo([StringTable("040904B0", strings)]),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )
