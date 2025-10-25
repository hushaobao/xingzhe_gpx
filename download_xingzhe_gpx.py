import os
import json
import time
import tqdm
import requests
from fake_useragent import UserAgent


# Paste your cookie string here
COOKIE = ""


# By default, all are obtained at once. Set a larger number of exports.
NUM_EXPORT = 10000
SPORT_TYPE = ""
YEAR = ""
MOUTH = ""

URL_SPORT_LIST = f"https://www.imxingzhe.com/api/v1/pgworkout/?offset=0&limit={NUM_EXPORT}&sport={SPORT_TYPE}&year={YEAR}&month={MOUTH}"


def run(save_dir="results/gpx"):
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    ua = UserAgent()
    header = {"User-Agent": ua.chrome, "Cookie": COOKIE}

    # get sport records list
    ans = requests.get(URL_SPORT_LIST, headers=header)

    if ans.status_code != 200:
        print(f"Failed to fetch sport records, status code: {ans.status_code}")
        return

    sport_records = ans.json()
    with open("sport_records.json", "w", encoding="utf-8") as f:
        json.dump(sport_records, f, ensure_ascii=False, indent=2)

    # download gpx files by recoods-id
    lists = sport_records["data"]["data"]
    for log in tqdm.tqdm(lists):
        id = log["id"]
        sport = log["sport"]
        title = log["title"].replace(" ", "-")
        save_name = f"{title}_{sport}_{id}.gpx"
        save_path = os.path.join(save_dir, save_name)
        url = f"https://www.imxingzhe.com/api/v1/pgworkout/{id}/gpx/"
        ans = requests.get(url, headers=header)
        if ans.status_code != 200:
            print(f"Failed to download GPX for ID {id}, status code: {ans.status_code}")
            continue
        with open(save_path, "wb") as f:
            f.write(ans.content)

        # Avoid being restricted
        time.sleep(0.5)


if __name__ == "__main__":
    save_dir = "results/gpx"
    run()
