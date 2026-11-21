"""cli 模块单元测试：退出码、默认值、错误提示与输出内容。"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from spirodraw.cli import main
from spirodraw.model import SpirodrawError

ROOT = Path(__file__).resolve().parent.parent


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "spirodraw"] + list(args),
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )


class MainSuccessTest(unittest.TestCase):
    def test_generates_html(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "book.html"
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(
                    ["--curves", "3", "--seed", "7", "-o", str(target)]
                )
            self.assertEqual(code, 0)
            self.assertTrue(target.exists())
            page = target.read_text(encoding="utf-8")
            self.assertEqual(page.count("<article"), 3)
            self.assertEqual(page.count("<section class="), 3)
            self.assertIn("3 条曲线", buffer.getvalue())
            self.assertIn("共 3 页", buffer.getvalue())

    def test_default_title(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "book.html"
            with redirect_stdout(io.StringIO()):
                code = main(["--curves", "2", "-o", str(target)])
            self.assertEqual(code, 0)
            self.assertIn(
                "万花尺描摹画册", target.read_text(encoding="utf-8")
            )

    def test_custom_title_is_escaped(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "book.html"
            with redirect_stdout(io.StringIO()):
                code = main(
                    [
                        "--curves",
                        "1",
                        "--title",
                        "<b>画册</b>",
                        "-o",
                        str(target),
                    ]
                )
            self.assertEqual(code, 0)
            page = target.read_text(encoding="utf-8")
            self.assertNotIn("<b>画册</b>", page)
            self.assertIn("&lt;b&gt;画册&lt;/b&gt;", page)

    def test_same_seed_outputs_identical_files(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            first = Path(folder) / "a.html"
            second = Path(folder) / "b.html"
            with redirect_stdout(io.StringIO()):
                main(["--curves", "4", "--seed", "42", "-o", str(first)])
                main(["--curves", "4", "--seed", "42", "-o", str(second)])
            self.assertEqual(
                first.read_text(encoding="utf-8"),
                second.read_text(encoding="utf-8"),
            )


class MainFailureTest(unittest.TestCase):
    def test_output_path_is_directory(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "blocked.html"
            target.mkdir()
            with redirect_stderr(io.StringIO()):
                code = main(["--curves", "2", "-o", str(target)])
            self.assertEqual(code, 1)

    def test_missing_parent_directory(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "no-such-dir" / "book.html"
            with redirect_stderr(io.StringIO()):
                code = main(["--curves", "2", "-o", str(target)])
            self.assertEqual(code, 1)

    def test_generation_error_returns_2(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "book.html"
            error = SpirodrawError("曲线无法闭合")
            buffer = io.StringIO()
            with mock.patch(
                "spirodraw.cli.generate_params", side_effect=error
            ):
                with redirect_stderr(buffer):
                    code = main(["--curves", "2", "-o", str(target)])
            self.assertEqual(code, 2)
            self.assertIn("错误", buffer.getvalue())
            self.assertIn("曲线无法闭合", buffer.getvalue())
            self.assertFalse(target.exists())

    def test_render_error_returns_2(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "book.html"
            buffer = io.StringIO()
            with mock.patch(
                "spirodraw.cli.render_html",
                side_effect=SpirodrawError("标题过长"),
            ):
                with redirect_stderr(buffer):
                    code = main(["--curves", "2", "-o", str(target)])
            self.assertEqual(code, 2)
            self.assertIn("标题过长", buffer.getvalue())


class ArgumentParsingTest(unittest.TestCase):
    def test_invalid_curve_counts_exit_2(self) -> None:
        for value in ("0", "13", "abc"):
            with self.subTest(value=value):
                with redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as ctx:
                        main(["--curves", value])
                self.assertEqual(ctx.exception.code, 2)

    def test_invalid_seed_exits_2(self) -> None:
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                main(["--seed", "abc"])
        self.assertEqual(ctx.exception.code, 2)

    def test_help_exits_zero(self) -> None:
        with redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                main(["--help"])
        self.assertEqual(ctx.exception.code, 0)

    def test_version_exits_zero(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            with self.assertRaises(SystemExit) as ctx:
                main(["--version"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("spirodraw 0.1.0", buffer.getvalue())


class SubprocessCliTest(unittest.TestCase):
    def test_smoke_generation(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "book.html"
            result = _run_cli(
                "--curves", "2", "--seed", "3", "-o", str(target)
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(target.exists())
            self.assertEqual(
                target.read_text(encoding="utf-8").count("<article"), 2
            )

    def test_out_of_range_curves_exit_2(self) -> None:
        result = _run_cli("--curves", "0")
        self.assertEqual(result.returncode, 2)
        self.assertIn("曲线数量", result.stderr)

    def test_non_integer_curves_exit_2(self) -> None:
        result = _run_cli("--curves", "abc")
        self.assertEqual(result.returncode, 2)
        self.assertIn("整数", result.stderr)

    def test_non_integer_seed_exit_2(self) -> None:
        result = _run_cli("--seed", "abc")
        self.assertEqual(result.returncode, 2)
        self.assertIn("随机种子", result.stderr)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
