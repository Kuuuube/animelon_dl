import requests
import time
import os
import json
import argparse
import sys
import subtitle_decryptor
import collections
import traceback

session_tuple = collections.namedtuple("session", "session headers")
settings_tuple = collections.namedtuple("settings", "save_path subtitles_only quality_priorities sleep")

def download_video(current_session, url, file_name, quality, settings):
    file_size = 0
    if os.path.exists(file_name):
        print(str(file_name) + " previously saved, attempting to resume download")
        current_session.session.headers["Range"] = "bytes=" + str(os.path.getsize(file_name)) + "-"
        current_session.session.headers.update(current_session.session.headers)
        file_size = os.path.getsize(file_name)

    time.sleep(settings.sleep) #decreases liklihood of needing a request retry
    video = current_session.session.get(url, stream = True)
    if video.status_code == 416:
        print(str(file_name) + " download previously completed, not redownloading")
        return True

    if video.status_code not in [200, 206]:
        return False

    file_size = int(video.headers.get('Content-Length', None)) + file_size
    print("Downloading : " + str(file_name.split('/')[-1]) + " " + "(%.2f MB)" % (file_size * 1024 ** -2) + " " + quality + " quality...")
    start_time = time.time()
    progress_bar(0, file_size, start_time, start_time, 80, True)

    write_mode = "wb"
    if os.path.exists(file_name):
        write_mode = "ab"

    with open(file_name, write_mode) as f:
        for chunk in video.iter_content(2048):
            f.write(chunk)
            progress_bar(os.path.getsize(file_name), file_size, start_time, time.time(), 80, False)

    progress_bar(file_size, file_size, start_time, time.time(), 80, False) #show 100% even if the last progress_bar update does not show 100%

    current_session.session.headers.update(current_session.headers) #headers must be reset back to default

    return True

def progress_bar(current, max, start_time, current_time, bar_size, init):
    if not init:
        sys.stdout.write("\033[F\033[K\033[F\033[K")

    percent = str(round(current / max * 100, 2)) + "%"
    chunks = max / bar_size
    filled_boxes = int(current / chunks)
    unfilled_boxes = bar_size - filled_boxes

    elapsed_time = current_time - start_time
    estimated_time = 0
    if current != 0:
        estimated_time = max / current * (current_time - start_time)

    elapesed_time_str = ""
    estimated_time_str = ""
    if elapsed_time < 60:
        elapesed_time_str = "%.2fs" % elapsed_time
    else:
        minutes = elapsed_time / 60
        elapesed_time_str = str(int(minutes)) + "m " + "%.2fs" % (minutes * 60 - int(minutes) * 60)

    if estimated_time < 60:
        estimated_time_str = "%.2fs" % estimated_time
    else:
        minutes = estimated_time / 60
        estimated_time_str = str(int(minutes)) + "m " + "%.2fs" % (minutes * 60 - int(minutes) * 60)

    progress_bar = ""

    for _ in range(filled_boxes):
        progress_bar += "█"

    for _ in range(unfilled_boxes):
        progress_bar += "░"

    print("%.2f" % (current * 1024 ** -2) + " / " +  "%.2f MB" % (max * 1024 ** -2) + " in " + elapesed_time_str + " (est " + estimated_time_str + ")" + "\n" + progress_bar + " " + percent)

def get_subtitle_from_json(res_obj):
    subtitles = []
    sub_obj = res_obj["subtitles"]
    for i in sub_obj:
        subtitle_list = i["content"]
        for j in ["englishSub", "romajiSub", "hiraganaSub", "japaneseSub", "katakanaSub"]:
            if j in subtitle_list.keys():
                subtitles.append((j, subtitle_decryptor.decrypt_subtitle(subtitle_list[j])))
    return subtitles

def save_subtitle_to_file(language_sub, content, save_path, video_name):
    ext = ".ass"
    if content[0:4] == b"\x31\x0A\x30\x30": #srt magicbytes
        ext = ".srt"

    iso = {"englishSub" : "en", 'romajiSub' : "ro", "japaneseSub" : "jp", "hiraganaSub" : "hi", "katakanaSub" : "ka"}
    file_name = os.path.join(save_path, video_name + "." + iso[language_sub] + ext)
    if os.path.exists(file_name):
        print(str(file_name) + " previously saved, not resaving")
    else:
        print("Saved " + str(file_name))
        with open(file_name, "wb") as f:
            f.write(content)

def save_subtitles_from_res_obj(res_obj, video_name, save_path):
    file_names = []
    subtitleList = get_subtitle_from_json(res_obj)
    for sub in subtitleList:
        file_names.append(save_subtitle_to_file(sub[0], sub[1], save_path, video_name))
    return file_names

def download_from_res_obj(current_session, res_obj, file_name, settings):
    title = res_obj["title"]
    if file_name is None:
        file_name = os.path.join(settings.save_path, title + ".mp4")

    save_subtitles_from_res_obj(res_obj, os.path.basename(file_name).replace(".mp4", ""), os.path.dirname(file_name))
    if (settings.subtitles_only):
        return "skipped video"

    video = (res_obj["video"])
    video_urls = video["videoURLsData"]
    for user_agent_key in video_urls.keys():
        #animelon will allow us to download the video only if we send the corresponding user agent
        #also idk why the userAgent is formatted that way in the JSON, but we have to replace this.
        current_session.session.headers.update({"User-Agent": user_agent_key.replace("=+(dot)+=", ".")})
        mobile_url_list = video_urls[user_agent_key]
        video_urls_sublist = mobile_url_list["videoURLs"]
        for quality in settings.quality_priorities:
            if quality in video_urls_sublist.keys():
                video_url = video_urls_sublist[quality]
                download_status = download_video(current_session, video_url, file_name, quality, settings)
                if not download_status:
                    return
                print("Finished downloading " + str(file_name))
                return file_name

def get_episode_list(current_session, series_url, settings):
    series_name = series_url.rsplit('/', 1)[-1]
    url = "https://animelon.com/api/series/" + series_name
    status_code = 403
    tries = 0
    while tries < 5 and status_code != 200:
        response = current_session.session.get(url)
        status_code = response.status_code
        tries += 1
        if status_code == 200:
            break
        time.sleep(settings.sleep)
    if (status_code != 200):
        print("Error getting anime info")
        return None
    try:
        jsoned = json.loads(response.text)
        res_obj = jsoned["resObj"]
        if res_obj is None and '\\' in series_url:
            series_url = series_url.replace('\\', '')
            return get_episode_list(current_session, series_url, settings)
    except Exception:
        print("Error: Could not parse anime info :\n", traceback.format_exc(), url, "\n", response, response.content, file=sys.stderr)
        return None
    return res_obj

def download_from_video_page(current_session, url, settings, id = None, file_name = None):
    if url is None:
        url = "https://animelon.com/video/" + id
    if id is None:
        id = url.split("/")[-1]

    api_url = "https://animelon.com/api/languagevideo/findByVideo?videoId=%s&learnerLanguage=en&subs=1&cdnLink=1&viewCounter=1" % (id)
    for tries in range(5):
        response = requests.get(api_url, headers = current_session.headers)
        if response.status_code == 200:
            jsonsed = json.loads(response.content)
            file = download_from_res_obj(current_session, jsonsed["resObj"], file_name, settings)
            if file is not None or (file == "skipped video" and settings.subtitles_only):
                return file
        print ("Failed to download " + str(file_name) + " retrying ... ( " + str(5 - tries) + " tries left)"),
        time.sleep(settings.sleep)
    print("Failed to download " + str(file_name))

def download_episodes(current_session, episodes, title, season_number, settings):
    index = 0
    for episode in episodes:
        index += 1
        url = "https://animelon.com/video/" + episode
        file_name = title + " S" + str(season_number) + "E" + str(index) + ".mp4"
        os.makedirs(settings.save_path, exist_ok=True)
        file_name = os.path.join(settings.save_path, file_name)
        print(str(file_name) + " : " + url)
        try:
            download_from_video_page(current_session, url, settings, file_name = file_name)
        except Exception:
            print("Error: Failed to download " + url, file=sys.stderr)
            print(traceback.format_exc())

def download_series(current_session, url, settings):
    res_obj = get_episode_list(current_session, url, settings)
    if res_obj is None:
        return
    title = res_obj["_id"]
    print("Title: " + str(title))
    series_save_path = os.path.join(settings.save_path, title)
    seasons = res_obj["seasons"]
    for season in seasons:
        season_number = int(season["number"])
        season_save_path = os.path.join(series_save_path, "S%.2d" % season_number)
        settings = settings_tuple(season_save_path, settings.subtitles_only, settings.quality_priorities, settings.sleep)
        os.makedirs(season_save_path, exist_ok=True)
        print("Season %d:" % (season_number))
        episodes = season["episodes"]
        download_episodes(current_session, episodes, title, season_number, settings)

parser = argparse.ArgumentParser()
parser.add_argument("urls", metavar="", type=str, nargs="+", help="One or more series or video page URLs")
parser.add_argument("--dir", metavar="PATH", help="Directory path to save files to", type=str, default="./")
parser.add_argument("--subs_only", help="Only download subtitles", action="store_true", default=False)
parser.add_argument("--quality", metavar="", help="List of quality priorities from highest to lowest priority (ozez stz tsz)", default=["ozez", "stz", "tsz"], type=str, nargs="+")
parser.add_argument("--sleep", metavar="", help="Time in seconds to sleep between requests", default=5, type=int)
args = parser.parse_args()

current_session = session_tuple(requests.Session(), { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36" })
current_session.session.headers.update(current_session.headers)

settings = settings_tuple(args.dir, args.subs_only, args.quality, args.sleep)

dlEpisodes = []
for url in args.urls:
    try:
        type = url.split('/')[3]
    except IndexError:
        print('Error: Bad URL : "%s"' % url)
        sys.exit()
    try:
        if type == 'series':
            download_series(current_session, url, settings)
        elif type == 'video':
            download_from_video_page(current_session, url, settings)
        else:
            print('Error: Unknown URL type "%"' % type, file=sys.stderr)
    except KeyboardInterrupt:
        sys.exit()
