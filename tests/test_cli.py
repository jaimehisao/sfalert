import unittest
from io import StringIO
from unittest.mock import patch

from sfalert.__main__ import build_parser, main


class CliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = build_parser()

    def test_default_serve_flags(self) -> None:
        args = self.parser.parse_args([])
        self.assertIsNone(args.cmd)
        self.assertEqual(args.port, 8765)
        self.assertEqual(args.days, 30)
        self.assertFalse(args.no_poll)

    def test_ingest_subcommand(self) -> None:
        args = self.parser.parse_args(["ingest", "--days", "7", "--no-realtime"])
        self.assertEqual(args.cmd, "ingest")
        self.assertEqual(args.days, 7)
        self.assertTrue(args.no_realtime)

    def test_serve_subcommand(self) -> None:
        args = self.parser.parse_args(["serve", "--port", "9000", "--no-poll"])
        self.assertEqual(args.cmd, "serve")
        self.assertEqual(args.port, 9000)
        self.assertTrue(args.no_poll)

    def test_root_flags_before_subcommand_are_honored(self) -> None:
        # Subparser defaults must not clobber root-parsed values.
        args = self.parser.parse_args(["--days", "60", "ingest"])
        self.assertEqual(args.days, 60)
        args = self.parser.parse_args(["--port", "9000", "serve"])
        self.assertEqual(args.port, 9000)
        args = self.parser.parse_args(["--host", "0.0.0.0", "serve"])
        self.assertEqual(args.host, "0.0.0.0")
        args = self.parser.parse_args(["--no-poll", "serve"])
        self.assertTrue(args.no_poll)

    def test_subcommand_defaults_still_apply(self) -> None:
        self.assertEqual(self.parser.parse_args(["ingest"]).days, 30)
        self.assertEqual(self.parser.parse_args(["serve"]).port, 8765)
        self.assertFalse(self.parser.parse_args(["serve"]).no_poll)
        self.assertEqual(self.parser.parse_args(["ingest", "--days", "7"]).days, 7)

    def test_main_ingest_returns_cleanly(self) -> None:
        with patch("sfalert.__main__.ingest") as ingest_mock:
            main(["ingest", "--no-realtime", "--no-backfill"])
        ingest_mock.assert_called_once_with(days=30, realtime=False, backfill=False)

    def test_serve_subcommand_invokes_serve(self) -> None:
        with patch("sfalert.__main__.serve") as serve_mock:
            main(["serve", "--port", "9000"])
        serve_mock.assert_called_once_with(
            host="127.0.0.1", port=9000, poll=True
        )

    def test_default_path_skips_browser_when_disabled(self) -> None:
        with patch("sfalert.__main__.ensure_data") as ensure, patch(
            "sfalert.__main__.serve"
        ) as serve, patch("sfalert.__main__.webbrowser.open") as opener:
            main(["--no-browser", "--port", "9001"])
        ensure.assert_called_once()
        opener.assert_not_called()
        serve.assert_called_once_with(
            host="127.0.0.1", port=9001, poll=True
        )

    def test_browser_failure_is_ignored(self) -> None:
        with patch("sfalert.__main__.ensure_data"), patch(
            "sfalert.__main__.serve"
        ), patch(
            "sfalert.__main__.webbrowser.open",
            side_effect=Exception("no display"),
        ):
            main([])  # must not raise

    def test_ingest_failure_exits_cleanly(self) -> None:
        with patch("sfalert.__main__.ingest", side_effect=RuntimeError("feed down")), patch(
            "sys.stderr", new_callable=StringIO
        ) as err:
            with self.assertRaises(SystemExit) as ctx:
                main(["ingest", "--no-realtime"])
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("feed down", err.getvalue())

    def test_serve_bind_failure_exits_cleanly(self) -> None:
        with patch("sfalert.__main__.ensure_data"), patch(
            "sfalert.__main__.webbrowser.open"
        ), patch(
            "sfalert.__main__.serve",
            side_effect=OSError("[Errno 98] Address already in use"),
        ), patch("sys.stderr", new_callable=StringIO) as err:
            with self.assertRaises(SystemExit) as ctx:
                main([])
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("Address already in use", err.getvalue())

    def test_python_dash_m_entrypoint_runs(self) -> None:
        # Executes the __main__ guard end-to-end and proves the documented
        # `python -m sfalert` entry point works.
        import runpy

        with patch("sys.argv", ["sfalert", "--help"]), patch(
            "sys.stdout", new_callable=StringIO
        ) as out:
            with self.assertRaises(SystemExit) as ctx:
                runpy.run_module("sfalert", run_name="__main__")
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("ingest", out.getvalue())
        self.assertIn("serve", out.getvalue())
