from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import textwrap
import unittest


class PyextBuildTest(unittest.TestCase):
  def setUp(self) -> None:
    self.tmp = tempfile.TemporaryDirectory()
    self.root = pathlib.Path(self.tmp.name)
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    (self.root / "tools").mkdir()
    shutil.copy(repo_root / "tools/pyext-build", self.root / "tools/pyext-build")
    shutil.copy(
      repo_root / "tools/pyext_build_env.sh",
      self.root / "tools/pyext_build_env.sh",
    )
    (self.root / "pkg").mkdir()
    (self.root / "pkg/__init__.py").write_text("")
    (self.root / "pkg/fast.py").write_text("def add(x: int, y: int) -> int:\n  return x + y\n")
    (self.root / "pkg/other.py").write_text("def sub(x: int, y: int) -> int:\n  return x - y\n")
    self.bin_dir = self.root / "bin"
    self.bin_dir.mkdir()
    self.ext_suffix = sysconfig.get_config_var("EXT_SUFFIX") or ".so"
    self._write_fake_mypyc()
    self._write_fake_python_config()

  def tearDown(self) -> None:
    self.tmp.cleanup()

  def _write_fake_mypyc(self) -> None:
    path = self.bin_dir / "mypyc"
    path.write_text(
      textwrap.dedent(
        """\
        #!/usr/bin/env python3
        from __future__ import annotations

        import pathlib
        import sys

        for arg in sys.argv[1:]:
          if arg.endswith(".py"):
            p = pathlib.Path(arg)
            p.with_suffix(".so").write_bytes(b"fake so")
        """
      )
    )
    path.chmod(0o755)

  def _write_fake_python_config(self) -> None:
    path = self.bin_dir / "python3-config"
    path.write_text("#!/usr/bin/env sh\nexit 0\n")
    path.chmod(0o755)

  def _env(self) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
      {
        "REPO_ROOT": str(self.root),
        "REPO_ARCH": "x86_64",
        "PYTHON": shutil.which("python3") or sys.executable,
        "PYTHON_CONFIG": str(self.bin_dir / "python3-config"),
        "MYPYC": str(self.bin_dir / "mypyc"),
        "CC": "cc",
        "CXX": "c++",
      }
    )
    return env

  def test_builds_multiple_modules_preserving_package_paths(self) -> None:
    out_dir = self.root / "stage"
    proc = subprocess.run(
      [
        str(self.root / "tools/pyext-build"),
        "--out-dir",
        str(out_dir),
        "pkg/fast.py",
        "pkg/other.py",
      ],
      cwd=self.root,
      env=self._env(),
      check=False,
      text=True,
      stdout=subprocess.PIPE,
      stderr=subprocess.PIPE,
    )
    self.assertEqual(proc.returncode, 0, proc.stderr)
    outputs = proc.stdout.strip().splitlines()
    self.assertEqual(len(outputs), 2)
    self.assertTrue((out_dir / f"pkg/fast{self.ext_suffix}").is_file())
    self.assertTrue((out_dir / f"pkg/other{self.ext_suffix}").is_file())

  def test_reads_manifest_sources(self) -> None:
    manifest = self.root / "pyext.toml"
    manifest.write_text('sources = ["pkg/fast.py"]\n')
    out_dir = self.root / "stage"
    proc = subprocess.run(
      [
        str(self.root / "tools/pyext-build"),
        "--out-dir",
        str(out_dir),
        "--manifest",
        str(manifest),
      ],
      cwd=self.root,
      env=self._env(),
      check=False,
      text=True,
      stdout=subprocess.PIPE,
      stderr=subprocess.PIPE,
    )
    self.assertEqual(proc.returncode, 0, proc.stderr)
    self.assertEqual(len(proc.stdout.strip().splitlines()), 1)
    self.assertTrue((out_dir / f"pkg/fast{self.ext_suffix}").is_file())


if __name__ == "__main__":
  unittest.main()
