# -*- coding: utf-8 -*-


class Config:
    LAST_SESSION_PATH = "last_fest.txt"
    PROJECTOR_SCREEN = "Projector Screen"
    FILENAME_RE = "Filename RegEx"
    BG_TRACKS_DIR = "Background Tracks Dir"
    BG_ZAD_PATH = "Background ZAD Path"
    FILES_DIRS = "Files Dirs"
    VLC_ARGUMENTS = "VLC CLI Arguments"
    VLC_AOUT = "VLC Audio Output"
    BG_FADE_STOP_DELAYS = "BG Player Stop Fade In/Out Delays"
    BG_FADE_PAUSE_DELAYS = "BG Player Pause Fade In/Out Delays"
    COUNTDOWN_TIME_FMT = "Countdown Time Format"
    C2_DATABASE_PATH = "Cosplay2 Database Path"
    TEXT_WIN_FIELDS = "Main Fields in Text Window"
    COUNTDOWN_OPENING_TEXT = "Countdown Opening Text"
    COUNTDOWN_INTERMISSION_TEXT = "Countdown Intermission Text"
    API_POST_ENABLED = "API Post Enabled"
    API_POST_URL = "API Post URL"
    THEME = "Theme"


class Columns:
    NUM = u'№'
    FILES = 'files'
    NOTES = 'notes'
    NAME = 'name'
    C2_REQUEST_ID = 'req_id'


class Strings:
    APP_NAME = "Fest Engine"
    COUNTDOWN_ROW_TEXT_FULL = "break"
    COUNTDOWN_ROW_TEXT_SHORT = "brk"


class Colors:
    @staticmethod
    def is_dark():
        import wx
        try:
            return wx.SystemSettings.GetAppearance().IsDark()
        except:
            return False

    @staticmethod
    def get(light, dark):
        return dark if Colors.is_dark() else light

    # Dynamic Colors - Using properties
    @property
    def DUP_ROW(self): return Colors.get((128, 255, 255), (60, 100, 100))
    @property
#    def COUNTDOWN_ROW(self): return Colors.get((128, 255, 200), (60, 100, 80))
    def COUNTDOWN_ROW(self): return Colors.get((128, 255, 200), (80, 120, 100))
    @property
    def FILTERED_GRID(self): return Colors.get((255, 255, 200), (100, 100, 60))
    @property
    def ROW_PLAYING_NOW(self): return Colors.get((200, 200, 255), (90, 90, 140))
    @property
    def ROW_PLAYED_TO_END(self): return Colors.get((200, 200, 200), (80, 80, 80))
    @property
    def ROW_SKIPPED(self): return Colors.get((255, 200, 200), (120, 80, 80))
    @property
    def COUNTDOWN_TEXT_COLOR(self): return Colors.get((0, 0, 0), (255, 255, 255))



class FileTypes:
    video_extensions = {'avi', 'mp4', 'm4v', 'mov', 'wmv', 'mkv', 'm3u'}
    audio_extensions = {'mp3', 'wav', 'flac', 'ogg', 'm4a', 'aac', 'wma'}
    img_extensions = {'jpeg', 'png', 'jpg', 'zad.mp4'}


class wxWidgetsConstants:
    # https://github.com/wxWidgets/wxWidgets/blob/master/include/wx/image.h#L463
    wxImageLoad_Verbose = 1