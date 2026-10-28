"""Convert timestamped GPX tracks to one FIT activity per file."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import timezone
import logging
from pathlib import Path

import gpxpy
from geopy.distance import geodesic
from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.activity_message import ActivityMessage
from fit_tool.profile.messages.event_message import EventMessage
from fit_tool.profile.messages.lap_message import LapMessage
from fit_tool.profile.messages.session_message import SessionMessage
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.messages.record_message import RecordMessage
from fit_tool.profile.profile_type import FileType, Event, EventType, Sport, SubSport

LOGGER = logging.getLogger(__name__)


def timestamp(value):
    """FIT library expects Unix milliseconds; naive GPX times mean UTC."""
    if value is None:
        raise ValueError("轨迹点缺少时间，无法生成 FIT 活动")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)


def gpx_to_fit(gpx_data, sport=Sport.CYCLING):
    """Use one lap per nonempty segment, without bridging segment gaps."""
    segments = [segment.points for track in gpx_data.tracks
                for segment in track.segments if segment.points]
    if not segments:
        raise ValueError("GPX 中没有轨迹点")
    times = [timestamp(point.time) for points in segments for point in points]
    if any(current < previous for previous, current in zip(times, times[1:])):
        raise ValueError("轨迹点时间必须按先后顺序排列")
    start, end = times[0], times[-1]
    builder = FitFileBuilder(auto_define=True)
    message = FileIdMessage()
    message.type = FileType.ACTIVITY
    message.manufacturer = 255  # Development; no fabricated Garmin device identity.
    message.product = 0
    message.time_created = timestamp(gpx_data.time) if gpx_data.time else start
    builder.add(message)
    distance = timer_time = 0.0
    for index, points in enumerate(segments):
        segment_start, segment_end = timestamp(points[0].time), timestamp(points[-1].time)
        event = EventMessage()
        event.event, event.event_type = Event.TIMER, EventType.START
        event.timestamp = segment_start
        builder.add(event)
        lap_distance = 0.0
        previous = None
        for point in points:
            coordinate = (point.latitude, point.longitude)
            if previous is not None:
                delta = geodesic(previous, coordinate).meters
                distance += delta
                lap_distance += delta
            record = RecordMessage()
            record.timestamp = timestamp(point.time)
            record.position_lat, record.position_long = coordinate
            record.distance = distance
            if point.elevation is not None:
                record.altitude = point.elevation
            builder.add(record)
            previous = coordinate
        event = EventMessage()
        event.event, event.event_type = Event.TIMER, EventType.STOP_ALL
        event.timestamp = segment_end
        builder.add(event)
        duration = (segment_end - segment_start) / 1000
        timer_time += duration
        lap = LapMessage()
        lap.message_index = index
        lap.timestamp, lap.start_time = segment_end, segment_start
        lap.total_elapsed_time = lap.total_timer_time = duration
        lap.total_distance, lap.sport = lap_distance, sport
        lap.start_position_lat, lap.start_position_long = points[0].latitude, points[0].longitude
        lap.end_position_lat, lap.end_position_long = points[-1].latitude, points[-1].longitude
        builder.add(lap)
    session = SessionMessage()
    session.timestamp, session.start_time = end, start
    session.total_elapsed_time = (end - start) / 1000
    session.total_timer_time, session.total_distance = timer_time, distance
    session.sport, session.sub_sport = sport, SubSport.GENERIC
    session.first_lap_index, session.num_laps = 0, len(segments)
    session.event, session.event_type = Event.SESSION, EventType.STOP
    builder.add(session)
    activity = ActivityMessage()
    activity.timestamp, activity.total_timer_time = end, timer_time
    activity.num_sessions = 1
    activity.event, activity.event_type = Event.ACTIVITY, EventType.STOP
    builder.add(activity)
    return builder.build()


def read_gpx_file(file_path):
    with Path(file_path).open(encoding="utf-8-sig") as source:
        return gpxpy.parse(source)


def single_convert(gpx_path, fit_path, sport=Sport.CYCLING):
    fit = gpx_to_fit(read_gpx_file(gpx_path), sport)
    target = Path(fit_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".fit.part")
    try:
        fit.to_file(str(temporary))
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def _convert_task(source, target, sport):
    """Return text errors: some parser exceptions cannot cross process boundaries."""
    try:
        single_convert(source, target, sport)
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description="将 GPX 文件或目录转换为 FIT")
    parser.add_argument("input", nargs="?", default="results/gpx")
    parser.add_argument("--output", default="results/fit", help="输出目录")
    parser.add_argument("--workers", type=int, default=1, help="并行进程数，默认串行")
    parser.add_argument("--sport", choices=("cycling", "running", "walking"), default="cycling")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    if args.workers < 1:
        parser.error("--workers 必须大于 0")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    source, output = Path(args.input), Path(args.output)
    if source.is_file() and source.suffix.lower() == ".gpx":
        files = [source]
    elif source.is_dir():
        files = sorted(p for p in source.iterdir() if p.is_file() and p.suffix.lower() == ".gpx")
    else:
        files = []
    if not files:
        LOGGER.error("未找到 GPX 文件：%s", source)
        return 1
    sport = getattr(Sport, args.sport.upper())
    tasks = [(p, output / (p.stem + ".fit")) for p in files]
    pending = [(p, target) for p, target in tasks if args.overwrite or not target.exists()]
    failed = 0
    if args.workers == 1:
        for path, target in pending:
            try:
                single_convert(path, target, sport)
            except Exception as exc:
                failed += 1
                LOGGER.error("%s 转换失败：%s", path.name, exc)
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(_convert_task, p, target, sport): p for p, target in pending}
            for future in as_completed(futures):
                try:
                    error = future.result()
                except Exception as exc:
                    error = str(exc)
                if error:
                    failed += 1
                    LOGGER.error("%s 转换失败：%s", futures[future].name, error)
    LOGGER.info("转换 %d，跳过 %d，失败 %d", len(pending) - failed, len(tasks) - len(pending), failed)
    return int(failed > 0)


if __name__ == "__main__":
    raise SystemExit(main())
