#!/usr/bin/env python3

import requests
import time
import os
import json
import argparse
import sys
import subtitle_decryptor
import collections

def downloadVideo(current_session, url, fileName, stream, quality, savePath):
    if fileName is None:
        fileName = url.split("/")[-1] + ".mp4"
        fileName = os.path.join(savePath, fileName)
    video = stream
    if video is None:
        video = current_session.session.get(url, stream=True)

    block_size = 1024
    file_size = int(video.headers.get('Content-Length', None))
    print("Downloading : " + fileName.split('/')[-1] + " " + "(%.2f MB)" % (file_size * 1024 ** -2) + " " + quality + " quality", " ...")
    n_chunk = 2
    progressbar(0, file_size, 80, True)
    with open(fileName, 'wb') as f:
        for i, chunk in enumerate(video.iter_content(chunk_size = n_chunk * block_size)):
            f.write(chunk)
            progressbar((i + 1) * block_size * n_chunk, file_size, 80, False)

def progressbar(current, max, bar_size, init):
    if not init:
        sys.stdout.write("\033[F\033[K\033[F\033[K")

    percent = str(round(current / max * 100, 2)) + "%"
    chunks = max / bar_size
    filled_boxes = int(current / chunks)
    unfilled_boxes = bar_size - filled_boxes

    progress_bar = ""

    for _ in range(filled_boxes):
        progress_bar += "█"

    for _ in range(unfilled_boxes):
        progress_bar += "░"

    print("%.2f" % (current * 1024 ** -2) + " / " +  "%.2f MB" % (max * 1024 ** -2) + "\n" + progress_bar + " " + percent)

def getSubtitleFromJSON(resObj):
    subtitles = []
    subObj = resObj["subtitles"]
    for i in subObj:
        subtitleList = i["content"]
        for j in ["englishSub", "romajiSub", "hiraganaSub", "japaneseSub", "katakanaSub"]:
            if j in subtitleList.keys():
                subtitles.append((j, subtitle_decryptor.decrypt_subtitle(subtitleList[j])))
    return subtitles

def saveSubtitleToFile(languageSub, content, savePath, videoName:str=""):
    ext = ".ass"
    if content[0:4] == b"\x31\x0A\x30\x30": #srt magicbytes
        ext = ".srt"

    iso = {"englishSub" : "en", 'romajiSub' : "ro", "japaneseSub" : "jp", "hiraganaSub" : "hi", "katakanaSub" : "ka"}
    fileName = os.path.join(savePath, videoName + "." + iso[languageSub] + ext)
    with open(fileName, "wb") as f:
        f.write(content)
    return fileName

def saveSubtitlesFromResObj(resObj, videoName = None, savePath = None):
    fileNames = []
    subtitleList = getSubtitleFromJSON(resObj)
    for sub in subtitleList:
        fileNames.append(saveSubtitleToFile(sub[0], sub[1], savePath=savePath, videoName=videoName))
    return fileNames

def downloadFromResObj(current_session, resObj, fileName, settings):
    title = resObj["title"]
    if fileName is None:
        fileName = os.path.join(settings.save_path, title + ".mp4")

    saveSubtitlesFromResObj(resObj, videoName = os.path.basename(fileName).replace(".mp4", ""), savePath = os.path.dirname(fileName))
    if (settings.subtitles_only):
        return "skipped video"

    video = (resObj["video"])
    videoURLs = video["videoURLsData"]
    time.sleep(5)
    for userAgentKey in videoURLs.keys():
        #animelon will allow us to download the video only if we send the corresponding user agent
        #also idk why the userAgent is formatted that way in the JSON, but we have to replace this.
        current_session.session.headers.update({"User-Agent": userAgentKey.replace("=+(dot)+=", ".")})
        mobileUrlList = videoURLs[userAgentKey]
        videoURLsSublist = mobileUrlList["videoURLs"]
        for quality in settings.quality_priorities:
            if quality in videoURLsSublist.keys():
                videoURL = videoURLsSublist[quality]
                videoStream = current_session.session.get(videoURL, stream=True)
                if videoStream.status_code == 200:
                    downloadVideo(current_session, videoURL, fileName, videoStream, quality, settings.save_path)
                    print ("Finished downloading ", fileName)
                    return fileName
    return None

def getEpisodeList(current_session, seriesURL):
    seriesName = seriesURL.rsplit('/', 1)[-1]
    url = "https://animelon.com/api/series/" + seriesName
    statusCode = 403
    tries = 0
    while statusCode != 200 and tries < 5:
        response = current_session.session.get(url)
        statusCode = response.status_code
        tries += 1
        time.sleep(0.5)
    if (statusCode != 200):
        print ("Error getting anime info")
        return None
    try:
        jsoned = json.loads(response.text)
        resObj = jsoned["resObj"]
        if resObj is None and '\\' in seriesURL:
            seriesURL = seriesURL.replace('\\', '')
            return getEpisodeList(seriesURL)
    except Exception as e:
        print ("Error: Could not parse anime info :\n", e, url , "\n", response, response.content, file=sys.stderr)
        return None
    return resObj

def downloadFromVideoPage(current_session, url, settings, id = None, fileName = None):
    assert(url is not None or id is not None)
    if url is None:
        url = "https://animelon.com/video/" + id
    if id is None:
        id = url.split("/")[-1]

    apiUrl = "https://animelon.com/api/languagevideo/findByVideo?videoId=%s&learnerLanguage=en&subs=1&cdnLink=1&viewCounter=1" % (id)
    for tries in range(5):
        response = requests.get(apiUrl, headers = current_session.headers)
        if response.status_code == 200:
            jsonsed = json.loads(response.content)
            file = downloadFromResObj(current_session, jsonsed["resObj"], fileName, settings)
            if file is not None:
                return file
            if file == "skipped video" and settings.subtitles_only:
                return "skipped video"
            print ("Failed to download ", fileName, "retrying ... (", 5 - tries, " tries left)"),
            time.sleep(5 * tries)
    print ("Failed to download ", fileName)

def downloadEpisodes(current_session, episodes:dict, title:str, seasonNumber:int=0, savepath:str="./"):
    index = 0
    downloadedEpisodes = []
    for episode in episodes:
        index += 1
        url = "https://animelon.com/video/" + episode
        fileName = title + " S" + str(seasonNumber) + "E" + str(index) + ".mp4"
        os.makedirs(savepath, exist_ok=True)
        fileName = os.path.join(savepath, fileName)
        print(fileName, " : ", url)
        try:
            downloadFromVideoPage(current_session, url, savepath, fileName = fileName)
            downloadedEpisodes.append(index)
        except Exception as e:
            print("Error: Failed to download " + url, file=sys.stderr)
            print(e)

def downloadSeries(current_session, url, settings):
    resObj = getEpisodeList(url)
    if resObj is None:
        return
    title = resObj["_id"]
    print("Title: ", title)
    seriesSavePath = os.path.join(settings.save_path, title)
    seasons = resObj["seasons"]
    for season in seasons:
        seasonNumber = int(season["number"])
        seasonSavePath = os.path.join(seriesSavePath, "S%.2d" % seasonNumber)
        os.makedirs(seasonSavePath, exist_ok=True)
        print("Season %d:" % (seasonNumber))
        episodes = season["episodes"]
        downloadEpisodes(current_session, episodes, title, seasonNumber = seasonNumber, savePath = seasonSavePath)

parser = argparse.ArgumentParser(description='Downloads videos from animelon.com')
parser.add_argument('videoURLs', metavar='videoURLs', type=str, nargs='+', help='A series or video page URL, eg: https://animelon.com/series/Death%%20Note or https://animelon.com/video/579b1be6c13aa2a6b28f1364')
parser.add_argument("--save_path", '-f', metavar='savePath', help='Path to save', type=str, default="")
parser.add_argument('--subtitles_only', help='Only downloads subtitles', action='store', default=False, const=True, nargs='?')
parser.add_argument('--quality_priorities', help='Set quality priorities (ozez, stz, tsz)', default=["ozez", "stz", "tsz"], type=str, nargs='+')
args = parser.parse_args()

session_tuple = collections.namedtuple("session", "session headers")
current_session = session_tuple(requests.Session(), { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36" })
current_session.session.headers.update(current_session.headers)

settings_tuple = collections.namedtuple("settings", "save_path subtitles_only quality_priorities")
settings = settings_tuple(args.save_path, args.subtitles_only, args.quality_priorities)

dlEpisodes = []
for url in args.videoURLs:
    try:
        type = url.split('/')[3]
    except IndexError:
        print('Error: Bad URL : "%s"' % url)
        sys.exit()
    if type == 'series':
        downloadSeries(current_session, url, settings)
    elif type == 'video':
        downloadFromVideoPage(current_session, url, settings)
    else:
        print('Error: Unknown URL type "%"' % type, file=sys.stderr)