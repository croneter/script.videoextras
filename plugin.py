# -*- coding: utf-8 -*-
# Reference:
# http://wiki.xbmc.org/index.php?title=Audio/Video_plugin_tutorial
import sys
import os
import traceback
import re
import urllib
import urlparse
import xbmcgui
import xbmcplugin
import xbmcaddon
import xbmcvfs

if sys.version_info < (2, 7):
    import simplejson
else:
    import json as simplejson


__addon__    = xbmcaddon.Addon(id='script.videoextras')
__icon__     = __addon__.getAddonInfo('icon')
__fanart__   = __addon__.getAddonInfo('fanart')
__cwd__      = __addon__.getAddonInfo('path').decode("utf-8")
__profile__   = xbmc.translatePath( __addon__.getAddonInfo('profile') ).decode("utf-8")
__resource__ = xbmc.translatePath( os.path.join( __cwd__, 'resources' ).encode("utf-8") ).decode("utf-8")
__lib__      = xbmc.translatePath( os.path.join( __resource__, 'lib' ).encode("utf-8") ).decode("utf-8")


sys.path.append(__resource__)
sys.path.append(__lib__)

# Import the common settings
from settings import Settings
from settings import log
from settings import os_path_join
from settings import os_path_split


# Load the database interface
from database import ExtrasDB

# Load the core Video Extras classes
from core import ExtrasItem
from core import SourceDetails
from core import VideoExtrasBase

# Load the Video Extras Player that handles playing the extras files
from ExtrasPlayer import ExtrasPlayer

###################################################################
# Class to handle the navigation information for the plugin
###################################################################
class MenuNavigator():
    MOVIES = 'movies'
    TVSHOWS = 'tvshows'
    MUSICVIDEOS = 'musicvideos'

    def __init__(self, base_url, addon_handle):
        self.base_url = base_url
        self.addon_handle = addon_handle

    # Creates a URL for a directory
    def _build_url(self, query):
        return self.base_url + '?' + urllib.urlencode(query)

    # Display the default list of items in the root menu
    def showRootMenu(self):
        # Movies
        url = self._build_url({'mode': 'folder', 'foldername': MenuNavigator.MOVIES})
        li = xbmcgui.ListItem(__addon__.getLocalizedString(32110), iconImage=__icon__)
        li.setProperty( "Fanart_Image", __fanart__ )
        li.addContextMenuItems( [], replaceItems=True )
        xbmcplugin.addDirectoryItem(handle=self.addon_handle, url=url, listitem=li, isFolder=True)
    
        # TV Shows
        url = self._build_url({'mode': 'folder', 'foldername': MenuNavigator.TVSHOWS})
        li = xbmcgui.ListItem(__addon__.getLocalizedString(32111), iconImage=__icon__)
        li.setProperty( "Fanart_Image", __fanart__ )
        li.addContextMenuItems( [], replaceItems=True )
        xbmcplugin.addDirectoryItem(handle=self.addon_handle, url=url, listitem=li, isFolder=True)

        # Music Videos
        url = self._build_url({'mode': 'folder', 'foldername': MenuNavigator.MUSICVIDEOS})
        li = xbmcgui.ListItem(__addon__.getLocalizedString(32112), iconImage=__icon__)
        li.setProperty( "Fanart_Image", __fanart__ )
        li.addContextMenuItems( [], replaceItems=True )
        xbmcplugin.addDirectoryItem(handle=self.addon_handle, url=url, listitem=li, isFolder=True)
     
        xbmcplugin.endOfDirectory(self.addon_handle)

    # Show the list of videos in a given set
    def showFolder(self, foldername):
        # Check for the special case of manually defined folders
        if foldername == MenuNavigator.TVSHOWS:
            self.setVideoList('GetTVShows', MenuNavigator.TVSHOWS, 'tvshowid')
        elif foldername == MenuNavigator.MOVIES:
            self.setVideoList('GetMovies', MenuNavigator.MOVIES, 'movieid')
        elif foldername == MenuNavigator.MUSICVIDEOS:
            self.setVideoList('GetMusicVideos', MenuNavigator.MUSICVIDEOS, 'musicvideoid')


    # Produce the list of videos and flag which ones have themes
    def setVideoList(self, jsonGet, target, dbid):
        videoItems = self.getVideos(jsonGet, target, dbid)
        
        for videoItem in videoItems:
            if not self.hasVideoExtras(target, videoItem['dbid'], videoItem['file']):
                continue
            # Create the list-item for this video            
            li = xbmcgui.ListItem(videoItem['title'], iconImage=videoItem['thumbnail'])
            # Remove the default context menu
            li.addContextMenuItems( [], replaceItems=True )
            # Set the background image
            if videoItem['fanart'] != None:
                li.setProperty( "Fanart_Image", videoItem['fanart'] )
            url = self._build_url({'mode': 'listextras', 'foldername': target, 'path': videoItem['file'].encode("utf-8")})
            xbmcplugin.addDirectoryItem(handle=self.addon_handle, url=url, listitem=li, isFolder=True)

        xbmcplugin.endOfDirectory(self.addon_handle)


    # Do a lookup in the database for the given type of videos
    def getVideos(self, jsonGet, target, dbid):
        json_query = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "VideoLibrary.%s", "params": {"properties": ["title", "file", "thumbnail", "fanart"], "sort": { "method": "title" } }, "id": 1}' % jsonGet)
        json_query = unicode(json_query, 'utf-8', errors='ignore')
        json_response = simplejson.loads(json_query)
        log( json_response )
        Videolist = []
        if "result" in json_query and json_response['result'].has_key(target):
            for item in json_response['result'][target]:
                videoItem = {}
                videoItem['title'] = item['title']
                # The file is actually the path for a TV Show, the video file for movies
                videoItem['file'] = item['file']
                
                if item['thumbnail'] == None:
                    item['thumbnail'] = 'DefaultFolder.png'
                else:
                    videoItem['thumbnail'] = item['thumbnail']
                videoItem['fanart'] = item['fanart']

                videoItem['dbid'] = item[dbid]

                Videolist.append(videoItem)
        return Videolist

    def hasVideoExtras(self, target, dbid, file):
        # If the service is on, then we can just check to see if the overlay image exists
        if Settings.isServiceEnabled():
            # Get the path where the file exists
            rootPath = os_path_join(__profile__, target)
            if not xbmcvfs.exists(rootPath):
                # Directory does not exist yet, so can't have extras
                return False
            
            # Generate the name of the file that the overlay will be copied to
            targetFile = os_path_join(rootPath, ("%d.png" % dbid))
            if xbmcvfs.exists(targetFile):
                return True
        
        # Otherwise, need to do the lookup the old fashioned way of looking for the 
        # extras files on the file system (This is much slower)
        else:
            videoExtras = VideoExtrasBase(file)
            firstExtraFile = videoExtras.findExtras(True)
            if firstExtraFile:
                log("MenuNavigator: Extras found for (%d) %s" % (dbid, file))
                return True

        return False

    # Shows all the extras for a given movie or TV Show
    def showExtras(self, path, target):
        # Check if the use database setting is enabled
        extrasDb = None
        if Settings.isDatabaseEnabled():
            extrasDb = ExtrasDB()

        # Create the extras class that will be used to process the extras
        videoExtras = VideoExtrasBase(path)

        # Perform the search command
        files = videoExtras.findExtras(extrasDb=extrasDb)

        # Add each of the extras to the list to display
        for anExtra in files:
            # Create the list item
            li = anExtra.createListItem()

            li.addContextMenuItems( [], replaceItems=True )
            url = self._build_url({'mode': 'playextra', 'foldername': target, 'path': path, 'filename': anExtra.getFilename().encode("utf-8")})
            xbmcplugin.addDirectoryItem(handle=self.addon_handle, url=url, listitem=li, isFolder=False)

        xbmcplugin.endOfDirectory(self.addon_handle)


    def playExtra(self, path, filename):
         # Check if the use database setting is enabled
        extrasDb = None
        if Settings.isDatabaseEnabled():
            extrasDb = ExtrasDB()

        # Create the extras class that will be used to process the extras
        videoExtras = VideoExtrasBase(path)

        # Perform the search command
        files = videoExtras.findExtras(extrasDb=extrasDb)
        for anExtra in files:
            if anExtra.isFilenameMatch( filename ):
                log("MenuNavigator: Found  = %s" % filename)
                ExtrasPlayer.performPlayAction(anExtra)
       


################################
# Main of the VideoExtras Plugin
################################
if __name__ == '__main__':
    # Get all the arguments
    base_url = sys.argv[0]
    addon_handle = int(sys.argv[1])
    args = urlparse.parse_qs(sys.argv[2][1:])

    # Record what the plugin deals with, files in our case
    xbmcplugin.setContent(addon_handle, 'files')

    # Get the current mode from the arguments, if none set, then use None
    mode = args.get('mode', None)
    
    log("VideoExtrasPlugin: Called with addon_handle = %d" % addon_handle)
    
    # If None, then at the root
    if mode == None:
        log("VideoExtrasPlugin: Mode is NONE - showing root menu")
        menuNav = MenuNavigator(base_url, addon_handle)
        menuNav.showRootMenu()
    elif mode[0] == 'folder':
        log("VideoExtrasPlugin: Mode is FOLDER")

        # Get the actual folder that was navigated to
        foldername = args.get('foldername', None)

        if (foldername != None) and (len(foldername) > 0):
            menuNav = MenuNavigator(base_url, addon_handle)
            menuNav.showFolder(foldername[0])

    elif mode[0] == 'listextras':
        log("VideoExtrasPlugin: Mode is LIST EXTRAS")

        # Get the actual path that was navigated to
        path = args.get('path', None)
        foldername = args.get('foldername', None)
        
        if (path != None) and (len(path) > 0) and (foldername != None) and (len(foldername) > 0):
            log("VideoExtrasPlugin: Path to load extras for %s" % path[0])
    
            menuNav = MenuNavigator(base_url, addon_handle)
            menuNav.showExtras(path[0], foldername[0])

    elif mode[0] == 'playextra':
        log("VideoExtrasPlugin: Mode is PLAY EXTRA")

        # Get the actual path that was navigated to
        path = args.get('path', None)
        filename = args.get('filename', None)
        
        if (path != None) and (len(path) > 0) and (filename != None) and (len(filename) > 0):
            log("VideoExtrasPlugin: Path to play extras for %s" % path[0])
            log("VideoExtrasPlugin: Extras file to play %s" % filename[0])
    
            menuNav = MenuNavigator(base_url, addon_handle)
            menuNav.playExtra(path[0], filename[0])


 