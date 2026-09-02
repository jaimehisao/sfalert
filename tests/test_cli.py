import unittest

from sfalert.__main__ import build_parser


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
