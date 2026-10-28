from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import gpxpy.gpx
from fit_tool.fit_file import FitFile
from fit_tool.profile.messages.lap_message import LapMessage
from fit_tool.profile.messages.session_message import SessionMessage
from fit_tool.profile.messages.record_message import RecordMessage

import download_xingzhe_gpx as download
import gpx2fit as convert


def fixture():
    gpx = gpxpy.gpx.GPX()
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    for offset, latitude in [(0, 30), (120, 40)]:
        track = gpxpy.gpx.GPXTrack()
        segment = gpxpy.gpx.GPXTrackSegment()
        segment.points = [gpxpy.gpx.GPXTrackPoint(
            latitude, 120 + index * 0.001,
            time=start + timedelta(seconds=offset + index * 10)) for index in range(2)]
        track.segments = [gpxpy.gpx.GPXTrackSegment(), segment]
        gpx.tracks.append(track)
    return gpx


class ConversionTests(unittest.TestCase):
    def test_fit_roundtrip_segment_statistics(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / "test.gpx", Path(folder) / "test.fit"
            source.write_text(fixture().to_xml(), encoding="utf-8")
            convert.single_convert(source, target)
            fit = FitFile.from_file(str(target))
        messages = [record.message for record in fit.records if not record.is_definition]
        laps = [m for m in messages if isinstance(m, LapMessage)]
        sessions = [m for m in messages if isinstance(m, SessionMessage)]
        records = [m for m in messages if isinstance(m, RecordMessage)]
        self.assertEqual(len(laps), 2)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(len(records), 4)
        session = sessions[0]
        self.assertEqual(session.total_elapsed_time, 130)
        self.assertEqual(session.total_timer_time, 20)
        self.assertEqual(session.timestamp, records[-1].timestamp)
        self.assertAlmostEqual(session.total_distance, sum(l.total_distance for l in laps), places=1)
        self.assertLess(session.total_distance, 300)
        self.assertEqual(records[1].distance, records[2].distance)

    def test_invalid_tracks(self):
        with self.assertRaises(ValueError):
            convert.gpx_to_fit(gpxpy.gpx.GPX())
        for value in [None, datetime(2020, 1, 1, tzinfo=timezone.utc)]:
            gpx = fixture()
            gpx.tracks[-1].segments[-1].points[-1].time = value
            with self.assertRaises(ValueError):
                convert.gpx_to_fit(gpx)

    def test_naive_timestamp_is_utc(self):
        value = datetime(2025, 1, 1)
        self.assertEqual(convert.timestamp(value), convert.timestamp(value.replace(tzinfo=timezone.utc)))

    def test_batch_failure_and_skip(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "good.gpx").write_text(fixture().to_xml(), encoding="utf-8")
            (root / "bad.gpx").write_text("invalid", encoding="utf-8")
            output = root / "out"
            for workers in (1, 2):
                output = root / f"out-{workers}"
                self.assertEqual(convert.main([folder, "--output", str(output),
                                               "--workers", str(workers)]), 1)
                self.assertTrue((output / "good.fit").exists())
                before = (output / "good.fit").stat().st_mtime_ns
                self.assertEqual(convert.main([str(root / "good.gpx"), "--output", str(output)]), 0)
                self.assertEqual(before, (output / "good.fit").stat().st_mtime_ns)
            self.assertFalse((output / "bad.fit").exists())


class DownloadTests(unittest.TestCase):
    @patch.dict("os.environ", {}, clear=True)
    def test_missing_cookie(self):
        with self.assertRaises(ValueError):
            download.run()

    @patch.object(download.requests, "Session")
    def test_download_validation_and_skip(self, session_class):
        session = session_class.return_value.__enter__.return_value
        listing = Mock()
        listing.json.return_value = {"data": {"data": [
            {"id": 1, "sport": 3, "title": "../ride:a"},
            {"id": 2, "sport": 3, "title": "bad"}]}}
        valid = Mock(content=fixture().to_xml().encode())
        invalid = Mock(content=b"<html>Login</html>")
        session.get.side_effect = [listing, valid, invalid]
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(download.run(folder, cookie="test", delay=0), (1, 0, 1))
            self.assertEqual(len(list(Path(folder).glob("*.gpx"))), 1)
            self.assertFalse(list(Path(folder).glob("*.part")))
            session.get.side_effect = [listing, invalid]
            self.assertEqual(download.run(folder, cookie="test", delay=0), (0, 1, 1))
        self.assertEqual(session.get.call_args.kwargs["timeout"], 30)

    @patch.object(download.requests, "Session")
    def test_invalid_listing(self, session_class):
        response = session_class.return_value.__enter__.return_value.get.return_value
        response.json.return_value = {"data": None}
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError):
            download.run(folder, cookie="test")


if __name__ == "__main__":
    unittest.main()
