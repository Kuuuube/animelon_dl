#!/usr/bin/env python3

import requests
import time
import os
import json
import argparse
import sys
import subtitle_decryptor

class AnimelonDownloader():
    def __init__(self, sleepTime:int=0, maxTries:int=5, savePath:str="./", subtitlesTypes:list=["englishSub", "romajiSub", "hiraganaSub", "japaneseSub"], sleepTimeRetry=5, qualityPriorities=["ozez", "stz", "tsz"], subtitlesOnly=False):
        self.session = requests.Session()
        self.headers = { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36" }
        self.session.headers.update(self.headers)
        self.processList = []
        self.sleepTime = sleepTime
        self.sleepTimeRetry = sleepTimeRetry
        self.maxTries = maxTries
        self.savePath = savePath
        self.subtitlesTypes = subtitlesTypes
        self.qualityPriorities = qualityPriorities
        self.subtitlesOnly = subtitlesOnly

def downloadVideo(downloader, url, fileName=None, stream=None, quality="unknown"):
    if fileName is None:
        fileName = url.split("/")[-1] + ".mp4"
        fileName = os.path.join(downloader.savePath, fileName)
    video = stream
    if video is None:
        video = downloader.session.get(url, stream=True)

    block_size = 1024
    file_size = int(video.headers.get('Content-Length', None))
    print("Downloading : " + fileName.split('/')[-1] + " " + "(%.2f MB)" % (file_size * 1024 ** -2) + " " + quality + " quality", " ...")
    n_chunk = 2
    progressbar(0, file_size, 80, True)
    with open(fileName, 'wb') as f:
        for i, chunk in enumerate(video.iter_content(chunk_size = n_chunk * block_size)):
            f.write(chunk)
            progressbar(i * block_size, file_size, 80, False)
    return fileName

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

def getSubtitleFromJSON(downloader, resObj, languageSubList:list=None):
    if languageSubList is None:
        languageSubList = downloader.subtitlesTypes
    subtitles = []
    subObj = resObj["subtitles"]
    for i in subObj:
        subtitleList = i["content"]
        for j in languageSubList:
            if j in subtitleList.keys():
                subtitles.append((j, subtitle_decryptor.decrypt_subtitle(subtitleList[j])))
    return subtitles

def saveSubtitleToFile(downloader, languageSub, content, videoName:str="", savePath:str=None):
    if savePath is None:
        savePath = downloader.savePath

    ext = ".ass"
    if content[0:4] == b"\x31\x0A\x30\x30": #srt magicbytes
        ext = ".srt"

    iso = {"englishSub" : "en", 'romajiSub' : "ro", "japaneseSub" : "jp", "hiraganaSub" : "hi"}
    fileName = os.path.join(savePath, videoName + "." + iso[languageSub] + ext)
    with open(fileName, "wb") as f:
        f.write(content)
    return fileName

def saveSubtitlesFromResObj(downloader, resObj, videoName=None, languageSubList:list=None, savePath:str=None):
    fileNames = []
    subtitleList = getSubtitleFromJSON(downloader, resObj, languageSubList)
    for sub in subtitleList:
        fileNames.append(saveSubtitleToFile(downloader, sub[0], sub[1], savePath=savePath, videoName=videoName))
    return fileNames

def downloadFromResObj(downloader, resObj, fileName=None, saveSubtitle=True, subtitlesOnly=False):
    title = resObj["title"]
    if fileName is None:
        fileName = os.path.join(downloader.savePath, title + ".mp4")
    if (saveSubtitle):
        saveSubtitlesFromResObj(downloader, resObj, videoName=os.path.basename(fileName).replace(".mp4", ""),
            savePath=os.path.dirname(fileName))
    if (downloader.subtitlesOnly):
        return "skipped video"
    video = (resObj["video"])
    videoURLs = video["videoURLsData"]
    time.sleep(downloader.sleepTime)
    for userAgentKey in videoURLs.keys():
        #animelon will allow us to download the video only if we send the corresponding user agent
        #also idk why the userAgent is formatted that way in the JSON, but we have to replace this.
        downloader.session.headers.update({"User-Agent": userAgentKey.replace("=+(dot)+=", ".")})
        mobileUrlList = videoURLs[userAgentKey]
        videoURLsSublist = mobileUrlList["videoURLs"]
        for quality in downloader.qualityPriorities:
            if quality in videoURLsSublist.keys():
                videoURL = videoURLsSublist[quality]
                videoStream = downloader.session.get(videoURL, stream=True)
                if videoStream.status_code == 200:
                    downloadVideo(downloader, videoURL, fileName=fileName, stream=videoStream, quality=quality)
                    print ("Finished downloading ", fileName)
                    return fileName
    return None

def getEpisodeList(downloader, seriesURL):
    seriesName = seriesURL.rsplit('/', 1)[-1]
    url = "https://animelon.com/api/series/" + seriesName
    statusCode = 403
    tries = 0
    while statusCode != 200 and tries < downloader.maxTries:
        response = downloader.session.get(url)
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
            return downloader.getEpisodeList(seriesURL)
    except Exception as e:
        print ("Error: Could not parse anime info :\n", e, url , "\n", response, response.content, file=sys.stderr)
        return None
    return resObj

def initSavePath(downloader, name):
    if downloader.savePath == "./" or name == "":
        downloader.savePath = name
    if downloader.savePath == "":
        downloader.savePath = "./"
    os.makedirs(downloader.savePath, exist_ok=True)
    return downloader.savePath

def downloadFromVideoPage(downloader, url=None, id=None, fileName=None, saveSubtitle=True):
    assert(url is not None or id is not None)
    if url is None:
        url = "https://animelon.com/video/" + id
    if id is None:
        id = url.split("/")[-1]

    apiUrl = "https://animelon.com/api/languagevideo/findByVideo?videoId=%s&learnerLanguage=en&subs=1&cdnLink=1&viewCounter=1" % (id)
    for tries in range(downloader.maxTries):
        response = requests.get(apiUrl, headers=downloader.headers)
        if response.status_code == 200:
            jsonsed = json.loads(response.content)
            file = downloadFromResObj(downloader, jsonsed["resObj"], fileName=fileName, saveSubtitle=saveSubtitle)
            if file is not None:
                return file
            if file == "skipped video" and downloader.subtitlesOnly:
                return "skipped video"
            print ("Failed to download ", fileName, "retrying ... (", downloader.maxTries - tries, " tries left)"),
            time.sleep(downloader.sleepTime * tries)
    print ("Failed to download ", fileName)
    return None

def downloadEpisodes(downloader, episodes:dict, title:str, seasonNumber:int=0, savePath:str="./"):
    index = 0
    downloadedEpisodes = []
    for episode in episodes:
        index += 1
        url = "https://animelon.com/video/" + episode
        fileName = title + " S" + str(seasonNumber) + "E" + str(index) + ".mp4"
        os.makedirs(savePath, exist_ok=True)
        fileName = os.path.join(savePath, fileName)
        print(fileName, " : ", url)
        try:
            downloadFromVideoPage(downloader, url, fileName=fileName)
            downloadedEpisodes.append(index)
        except Exception as e:
            print("Error: Failed to download " + url, file=sys.stderr)
            print(e)

def downloadSeries(downloader, url, savePath):
    resObj = downloader.getEpisodeList(url)
    if resObj is None:
        return
    title = resObj["_id"]
    print("Title: ", title)
    seriesSavePath = os.path.join(savePath, title)
    seasons = resObj["seasons"]
    for season in seasons:
        seasonNumber = int(season["number"])
        seasonSavePath = os.path.join(seriesSavePath, "S%.2d" % seasonNumber)
        os.makedirs(seasonSavePath, exist_ok=True)
        print("Season %d:" % (seasonNumber))
        episodes = season["episodes"]
        downloadEpisodes(downloader, episodes, title, seasonNumber=seasonNumber, savePath=seasonSavePath)

parser = argparse.ArgumentParser(description='Downloads videos from animelon.com')
parser.add_argument('videoURLs', metavar='videoURLs', type=str, nargs='+', help='A series or video page URL, eg: https://animelon.com/series/Death%%20Note or https://animelon.com/video/579b1be6c13aa2a6b28f1364')
parser.add_argument("--sleepTime", '-d', metavar='delay', help="Sleep time between each download (defaults to 5)", type=float, default=5)
parser.add_argument("--savePath", '-f', metavar='savePath', help='Path to save', type=str, default="")
parser.add_argument('--forks', metavar='forks', help='Number of worker process for simultaneous downloads (defaults to 1)', type=int, default=1)
parser.add_argument('--maxTries', metavar='maxTries', help='Maximum number of retries in case of failed requests (defaults to 5)', type=int, default=5)
parser.add_argument('--sleepTimeRetry', metavar='sleepTimeRetry', help='Sleep time between retries (defaults to 5)', type=float, default=5)
parser.add_argument('--subtitlesType', metavar='subtitlesType', help='Subtitles types to download (englishSub, romajiSub, hiraganaSub, japaneseSub, none)', type=str, default=("englishSub", "romajiSub", "hiraganaSub", "japaneseSub"), nargs='+')
parser.add_argument('--subtitlesOnly', help='Only downloads subtitles', action='store', default=False, const=True, nargs='?')
parser.add_argument('--qualityPriorities', help='Set quality priorities (ozez, stz, tsz)', default=["ozez", "stz", "tsz"], type=str, nargs='+')
args = parser.parse_args()

downloader = AnimelonDownloader(savePath=args.savePath, maxTries=args.maxTries, sleepTime=args.sleepTime, sleepTimeRetry=args.sleepTimeRetry, subtitlesTypes=args.subtitlesType, subtitlesOnly=args.subtitlesOnly, qualityPriorities=args.qualityPriorities)
initSavePath(downloader, args.savePath)

dlEpisodes = []
for url in args.videoURLs:
    try:
        type = url.split('/')[3]
    except IndexError:
        print('Error: Bad URL : "%s"' % url)
        sys.exit()
    if type == 'series':
        downloadSeries(downloader, url, args.savePath)
    elif type == 'video':
        downloadFromVideoPage(downloader, url)
    else:
        print('Error: Unknown URL type "%"' % type, file=sys.stderr)