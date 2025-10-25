import os
# from tqdm import tqdm
from multiprocessing import Pool

import gpxpy
from geopy.distance import geodesic
from datetime import datetime
from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.event_message import EventMessage
from fit_tool.profile.messages.lap_message import LapMessage

# from fit_tool.profile.messages.activity_message import ActivityMessage
from fit_tool.profile.messages.session_message import SessionMessage
from fit_tool.profile.messages.device_info_message import DeviceInfoMessage
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.messages.record_message import RecordMessage
from fit_tool.profile.profile_type import (
    FileType,
    TimerTrigger,
    Event,
    EventType,
    # LapTrigger,
    Sport,
    SubSport,
    SessionTrigger,
)

# 设备常量
MANUFACTURER = 1  # Garmin
GARMIN_PRODUCT = 3415  # Forerunner 245
GARMIN_SOFTWARE_VERSION = 3.58
GARMIN_SERIAL_NUMBER = 1234567890


def gpx_to_fit(gpx_data):
    """将GPX数据转换为FIT格式"""
    builder = FitFileBuilder(auto_define=True, min_string_size=50)

    # 获取时间信息 - 处理 gpx_data.time 为 None 的情况
    if gpx_data.time is not None:
        time_create = int(gpx_data.time.timestamp() * 1000)
    else:
        # 如果没有全局时间，使用第一个轨迹点的时间或当前时间
        first_point_time = None
        for track in gpx_data.tracks:
            for segment in track.segments:
                if segment.points and segment.points[0].time:
                    first_point_time = segment.points[0].time
                    break
            if first_point_time:
                break

        if first_point_time:
            time_create = int(first_point_time.timestamp() * 1000)
        else:
            time_create = int(datetime.now().timestamp() * 1000)

    # 文件ID
    message = FileIdMessage()
    message.local_id = 0
    message.type = FileType.ACTIVITY
    message.manufacturer = MANUFACTURER
    message.product = GARMIN_PRODUCT
    message.time_created = time_create
    message.serial_number = GARMIN_SERIAL_NUMBER
    builder.add(message)

    # 设备信息
    message = DeviceInfoMessage()
    message.local_id = 1
    message.serial_number = GARMIN_SERIAL_NUMBER
    message.manufacturer = MANUFACTURER
    message.garmin_product = GARMIN_PRODUCT
    message.software_version = GARMIN_SOFTWARE_VERSION
    message.device_index = 0
    message.source_type = 5
    message.product = GARMIN_PRODUCT
    builder.add(message)

    # 开始事件
    message = EventMessage()
    message.local_id = 2
    message.event = Event.TIMER
    message.event_type = EventType.START
    message.event_group = 0
    message.timer_trigger = TimerTrigger.MANUAL
    message.timestamp = time_create
    builder.add(message)

    # 记录点和距离计算
    distance = 0.0
    timestamp = time_create
    records = []
    prev_coordinate = None
    prev_time = None
    moving_time = 0

    for track in gpx_data.tracks:
        total_distance = 0.0

        for segment in track.segments:
            for track_point in segment.points:
                current_coordinate = (track_point.latitude, track_point.longitude)
                current_time = track_point.time

                # 计算距离和移动时间
                if prev_coordinate and prev_time:
                    delta = geodesic(prev_coordinate, current_coordinate).meters
                    time_diff = (current_time - prev_time).total_seconds()

                    # 只计算小于60秒的时间间隔
                    # if 0 < time_diff < 60:
                    moving_time += time_diff
                    distance += delta
                    total_distance = distance

                message = RecordMessage()
                message.local_id = 3
                message.position_lat = track_point.latitude
                message.position_long = track_point.longitude
                message.distance = distance
                message.altitude = track_point.elevation
                message.timestamp = int(track_point.time.timestamp() * 1000)
                records.append(message)

                prev_coordinate = current_coordinate
                prev_time = current_time

        # Lap信息
        start_point = track.segments[0].points[0]
        end_point = track.segments[-1].points[-1]

        message = LapMessage()
        message.local_id = 4
        message.timestamp = timestamp
        message.message_index = 0
        message.start_time = int(start_point.time.timestamp() * 1000)
        message.total_elapsed_time = moving_time
        message.total_timer_time = moving_time
        message.start_position_lat = start_point.latitude
        message.start_position_long = start_point.longitude
        message.end_position_lat = end_point.latitude
        message.end_position_long = end_point.longitude
        message.total_distance = total_distance
        message.sport = Sport.CYCLING
        builder.add(message)

        # Session信息
        message = SessionMessage()
        message.local_id = 5
        message.timestamp = timestamp
        message.start_time = int(start_point.time.timestamp() * 1000)
        message.total_elapsed_time = moving_time
        message.total_timer_time = moving_time
        message.start_position_lat = start_point.latitude
        message.start_position_long = start_point.longitude
        message.sport = Sport.CYCLING
        message.sub_sport = SubSport.GENERIC
        message.first_lap_index = 0
        message.num_laps = 1
        message.trigger = SessionTrigger.ACTIVITY_END
        message.event = Event.SESSION
        message.event_type = EventType.STOP
        message.total_distance = total_distance
        builder.add(message)

    builder.add_all(records)

    # 结束事件
    message = EventMessage()
    message.local_id = 2
    message.event = Event.TIMER
    message.event_type = EventType.STOP
    message.event_group = 0
    message.timer_trigger = TimerTrigger.MANUAL
    message.timestamp = timestamp
    builder.add(message)

    return builder.build()


def read_gpx_file(file_path):
    """读取GPX文件并返回GPX对象"""
    with open(file_path, "r") as gpx_file:
        gpx = gpxpy.parse(gpx_file)
    return gpx


def single_convert(gpx_path, fit_path):
    gpx = read_gpx_file(gpx_path)
    fit_file = gpx_to_fit(gpx)
    fit_file.to_file(fit_path)


if __name__ == "__main__":
    NUM_PROC = 12
    pools = Pool(NUM_PROC)

    gpx_dir = "results/gpx"
    save_dir = "results/fit"

    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    files = os.listdir(gpx_dir)

    print(f"Total GPX files to convert: {len(files)}")

    for file in files:
        if not file.endswith(".gpx"):
            continue
        gpx_path = os.path.join(gpx_dir, file)
        save_path = os.path.join(save_dir, file.replace(".gpx", ".fit"))

        pools.apply_async(single_convert, args=(gpx_path, save_path))
        # pools.apply(single_convert, args=(gpx_path, save_path))
    pools.close()
    pools.join()
