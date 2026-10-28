"""Download Xingzhe activities as GPX files."""
import argparse
import json
import logging
import os
from pathlib import Path
import re
import time
import xml.etree.ElementTree as ET

import requests

LOGGER = logging.getLogger(__name__)
BASE_URL = "https://www.imxingzhe.com/api/v1/pgworkout/"


def safe_filename(value):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f\s]+', "-", str(value))
    return name.strip(" .-")[:120] or "activity"


def run(save_dir="results/gpx", *, cookie=None, limit=10000, sport="",
        year="", month="", timeout=30, delay=0.5, overwrite=False):
    """Download up to limit activities; return (downloaded, skipped, failed)."""
    cookie = cookie or os.environ.get("XINGZHE_COOKIE", "")
    if not cookie.strip():
        raise ValueError("请通过 XINGZHE_COOKIE 环境变量设置登录 Cookie")
    if limit <= 0 or timeout <= 0 or delay < 0:
        raise ValueError("limit、timeout 必须大于 0，delay 不能小于 0")
    output = Path(save_dir)
    output.mkdir(parents=True, exist_ok=True)
    downloaded = skipped = failed = 0
    with requests.Session() as session:
        session.headers.update({"User-Agent": "xingzhe-gpx/0.1", "Cookie": cookie})
        response = session.get(BASE_URL, params={"offset": 0, "limit": limit,
                               "sport": sport, "year": year, "month": month},
                               timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        try:
            records = payload["data"]["data"]
            if not isinstance(records, list):
                raise TypeError
        except (KeyError, TypeError) as exc:
            raise ValueError("运动列表响应格式异常，请检查 Cookie 是否有效") from exc
        (output / "sport_records.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        for record in records:
            temporary = None
            try:
                activity_id = str(record["id"])
                if not activity_id.isascii() or not activity_id.isdigit():
                    raise ValueError("运动 ID 必须为数字")
                name = "_".join(safe_filename(record[key]) for key in ("title", "sport", "id"))
                target = output / f"{name}.gpx"
                if target.exists() and not overwrite:
                    skipped += 1
                    continue
                response = session.get(f"{BASE_URL}{activity_id}/gpx/", timeout=timeout)
                response.raise_for_status()
                root = ET.fromstring(response.content)
                if root.tag.split("}")[-1] != "gpx":
                    raise ValueError("下载响应不是 GPX")
                temporary = target.with_suffix(".gpx.part")
                temporary.write_bytes(response.content)
                temporary.replace(target)
                downloaded += 1
                LOGGER.info("已下载 %s", target.name)
            except (requests.RequestException, ValueError, KeyError, TypeError,
                    OSError, ET.ParseError) as exc:
                failed += 1
                LOGGER.error("下载失败：%s", exc)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
                time.sleep(delay)
    return downloaded, skipped, failed


def main(argv=None):
    parser = argparse.ArgumentParser(description="下载行者运动记录为 GPX")
    parser.add_argument("--output", default="results/gpx", help="保存目录")
    parser.add_argument("--limit", type=int, default=10000, help="最多获取的记录数")
    parser.add_argument("--sport", default="", help="行者运动类型编号")
    parser.add_argument("--year", type=int)
    parser.add_argument("--month", type=int, choices=range(1, 13))
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        downloaded, skipped, failed = run(
            args.output, limit=args.limit, sport=args.sport, year=args.year or "",
            month=args.month or "", timeout=args.timeout, delay=args.delay,
            overwrite=args.overwrite)
    except (requests.RequestException, ValueError, OSError) as exc:
        LOGGER.error("下载终止：%s", exc)
        return 1
    LOGGER.info("下载 %d，跳过 %d，失败 %d", downloaded, skipped, failed)
    return int(failed > 0)


if __name__ == "__main__":
    raise SystemExit(main())
