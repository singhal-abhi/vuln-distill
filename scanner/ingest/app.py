"""Load a decompiled Android app: manifest, the app's own code, key resources and its libraries."""

import shutil
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from scanner.config import resolve

# The library list is shown to models as this file, so findings about dependencies have a location.
LIBRARIES_FILE = "third-party-libraries.txt"


# Classes the Android build generates in every app.
GENERATED_CLASSES = {"BuildConfig", "Manifest", "R", "BR"}


@dataclass
class App:
    package: str
    manifest: str
    sources: dict[str, str]      # path relative to sources/ -> code
    resources: dict[str, str]    # path relative to resources/ -> content
    libraries: list[str]

    def to_prompt(self) -> str:
        parts = [f"# App package: {self.package}", _file_block("AndroidManifest.xml", self.manifest)]
        parts += [_file_block(path, text) for path, text in self.resources.items()]
        parts += [_file_block(path, text) for path, text in self.sources.items()]
        parts.append(_file_block(LIBRARIES_FILE, "\n".join(self.libraries)))
        return "\n\n".join(parts)

    def identifiers(self) -> set[str]:
        """Names specific to this app. Lessons that mention any of them are not general."""
        names = {self.package, self.package.rsplit(".", 1)[-1]} | {Path(path).stem for path in self.sources}
        names -= GENERATED_CLASSES   # in every Android app, so a lesson naming them is still general
        # Resource file names are left out: most are conventional (network_security_config, file_paths, strings),
        # so a lesson naming one is still general.
        return {name for name in names if len(name) >= 4}


def decompile(apk: Path, out_dir: Path) -> None:
    # Into a temp dir first, so an interrupted jadx never leaves a half-written input_dir that looks done.
    temp = out_dir.with_name(out_dir.name + ".partial")
    shutil.rmtree(temp, ignore_errors=True)
    if not shutil.which("jadx"):
        raise RuntimeError("jadx is not installed (brew install jadx)")
    # jadx exits non-zero when a few methods fail to decompile, which is normal; check the output instead.
    result = subprocess.run(["jadx", "-q", "-d", str(temp), str(apk)], capture_output=True, text=True)
    if not (temp / "resources" / "AndroidManifest.xml").exists():
        raise RuntimeError(f"jadx did not produce a manifest for {apk}:\n{result.stderr[-2000:]}")
    temp.rename(out_dir)


def load_app(config: dict) -> App:
    input_dir = resolve(config, config["app"]["input_dir"])
    if not input_dir.exists():
        decompile(resolve(config, config["app"]["apk"]), input_dir)

    settings = config["ingest"]
    manifest = (input_dir / "resources" / "AndroidManifest.xml").read_text()
    package = ET.fromstring(manifest).attrib["package"]
    app_packages = [package, *settings["extra_app_packages"]]
    sources = _load_sources(input_dir / "sources", app_packages, settings)
    if not sources:
        print(f"Warning: no code found under {', '.join(app_packages)}. If the app's code lives in another "
              "package, add it to ingest.extra_app_packages in config.yaml.")

    return App(
        package=package,
        manifest=manifest,
        sources=sources,
        resources=_load_resources(input_dir / "resources", settings),
        libraries=_load_libraries(input_dir, app_packages),
    )


def _load_sources(sources_dir: Path, app_packages: list[str], settings: dict) -> dict[str, str]:
    sources = {}
    for package in app_packages:
        for path in sorted((sources_dir / package.replace(".", "/")).rglob("*.java")):
            relative = path.relative_to(sources_dir)
            if path.name in settings["exclude_files"] or set(relative.parts) & set(settings["exclude_dirs"]):
                continue
            sources[relative.as_posix()] = path.read_text()
    return sources


def _load_resources(resources_dir: Path, settings: dict) -> dict[str, str]:
    resources = {}
    for pattern in settings["resource_globs"]:
        for path in sorted(resources_dir.glob(pattern)):
            resources[path.relative_to(resources_dir).as_posix()] = path.read_text()[: settings["max_resource_bytes"]]
    return resources


def _load_libraries(input_dir: Path, app_packages: list[str]) -> list[str]:
    """Versioned artifacts from META-INF, plus any other top-level code packages (libraries without version files)."""
    libraries = []
    for path in sorted((input_dir / "resources" / "META-INF").glob("*.version")):
        group, _, artifact = path.stem.partition("_")
        libraries.append(f"{group}:{artifact} {path.read_text().strip()}")

    sources_dir = input_dir / "sources"
    app_roots = {tuple(p.split(".")[:2]) for p in app_packages}
    tops = sorted(d for d in sources_dir.iterdir() if d.is_dir()) if sources_dir.is_dir() else []
    for top in tops:
        for second in sorted(d for d in top.iterdir() if d.is_dir()):
            package = f"{top.name}.{second.name}"
            already_versioned = any(lib.startswith((package + ".", package + ":")) for lib in libraries)
            if (top.name, second.name) not in app_roots and not already_versioned:
                libraries.append(f"{package} (package, version unknown)")
    return libraries


def _file_block(path: str, text: str) -> str:
    language = {".xml": "xml", ".java": "java"}.get(Path(path).suffix, "text")
    return f"### FILE: {path}\n```{language}\n{text.strip()}\n```"
