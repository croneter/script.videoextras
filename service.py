# -*- coding: utf-8 -*-
# *  This Program is free software; you can redistribute it and/or modify
# *  it under the terms of the GNU General Public License as published by
# *  the Free Software Foundation; either version 2, or (at your option)
# *  any later version.
# *
# *  This Program is distributed in the hope that it will be useful,
# *  but WITHOUT ANY WARRANTY; without even the implied warranty of
# *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# *  GNU General Public License for more details.
# *
# *  You should have received a copy of the GNU General Public License
# *  along with XBMC; see the file COPYING.  If not, write to
# *  the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
# *  http://www.gnu.org/copyleft/gpl.html
# *
import sys
import os
import traceback
#Modules XBMC
import xbmc
import xbmcgui
import xbmcvfs
import xbmcaddon

# Add JSON support for queries
if sys.version_info < (2, 7):
    import simplejson
else:
    import json as simplejson


__addon__     = xbmcaddon.Addon(id='script.videoextras')
__addonid__   = __addon__.getAddonInfo('id')
__version__   = __addon__.getAddonInfo('version')
__cwd__       = __addon__.getAddonInfo('path').decode("utf-8")
__profile__   = xbmc.translatePath( __addon__.getAddonInfo('profile') ).decode("utf-8")
__resource__  = xbmc.translatePath( os.path.join( __cwd__, 'resources' ).encode("utf-8") ).decode("utf-8")
__lib__  = xbmc.translatePath( os.path.join( __resource__, 'lib' ).encode("utf-8") ).decode("utf-8")

sys.path.append(__resource__)
sys.path.append(__lib__)

# Import the common settings
from settings import Settings
from settings import log
from settings import os_path_join

# Load the core Video Extras classes
from core import VideoExtrasBase


#####################################
# Main class for the Extras Service
#####################################
class VideoExtrasService():

    # Load all the cached data
    def loadCached(self):
        self.loadCacheToProperty('movies')
        self.loadCacheToProperty('tvshows')
        self.loadCacheToProperty('musicvideos')

    # Load a given cache into a property
    def loadCacheToProperty(self, target):
        log("VideoExtrasService: Loading cache for %s" % target)
        extrasCacheFile = self._getCacheFilenameForTarget(target)

        # check if the cached file exists
        if not xbmcvfs.exists(extrasCacheFile):
            log("VideoExtrasService: Cached file does not exist: %s" % extrasCacheFile)
            return
        
        # Read the contents of the file
        fileHandle = xbmcvfs.File(extrasCacheFile, 'r')
        cachedValues = fileHandle.read()
        fileHandle.close()
        
        # Split the list into each of the DBID values
        dbids = cachedValues.split(os.linesep)
        
        for dbid in dbids:
            # Generate the tag name
            propertyTag = ("HasVideoExtras_%s_%s" % (target.upper(),dbid) )
        
            # Now store the cached list as a property
            xbmcgui.Window( 12000 ).setProperty( propertyTag, "true" )

    # Regenerates all of the cached extras
    def cacheAllExtras(self):
        self.createExtrasCache('GetMovies', 'movies', 'movieid')
        self.createExtrasCache('GetTVShows', 'tvshows', 'tvshowid')
        self.createExtrasCache('GetMusicVideos', 'musicvideos', 'musicvideoid')

    # Checks all the given movies/TV/music videos to see if they have any extras
    # and if they do, then cretaes a cached file containing the titles of the video
    # that owns them
    def createExtrasCache(self, jsonGet, target, dbid):
        log("VideoExtrasService: Creating cache for %s" % target)
        json_query = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "VideoLibrary.%s", "params": { "properties": ["title", "file"] },  "id": 1}' % jsonGet)
        json_query = unicode(json_query, 'utf-8', errors='ignore')
        json_query = simplejson.loads(json_query)
    
        extrasCacheString = ""
    
        if "result" in json_query and json_query['result'].has_key(target):
            # Get the list of movies paths from the movie list returned
            items = json_query['result'][target]
            for item in items:
                # Check to see if exit has been called, if so stop
                if xbmc.getCondVisibility("Window.IsVisible(shutdownmenu)") or xbmc.abortRequested:
                    sys.exit()
                
                log("VideoExtrasService: %s detected: %s = %s" % (target, item['title'], item['file']))
                videoExtras = VideoExtrasBase(item['file'])
                firstExtraFile = videoExtras.findExtras(True)
                # Check if any extras exist for this movie
                if firstExtraFile:
                    log("VideoExtrasService: Extras found for (%d) %s" % (item[dbid], item['title']))
                    extrasCacheString = ("%s[%d]%s" % (extrasCacheString, item[dbid], os.linesep))

        extrasCacheFile = self._getCacheFilenameForTarget(target)

        self._saveToFile(extrasCacheFile, extrasCacheString)

    # Generate the name used for the cache
    def _getCacheFilenameForTarget(self, target):
        filename = ("%s_extras_cache.txt" % target)
        fullFilename = os_path_join(__profile__, filename)
        return fullFilename


    # Saves data to a file in the users addon area
    def _saveToFile(self, filename, fileData):
        log("VideoExtrasService: Saving to file %s" % filename)
    
        # If the file already exists, delete it
        if xbmcvfs.exists(filename):
            xbmcvfs.delete(filename)

        if (fileData != None) and (fileData != ""): 
            # Now save the new file list
            fileHandle = xbmcvfs.File(filename, 'w')
            try:
                fileHandle.write(fileData.encode("UTF-8"))
            except:
                log("VideoExtrasService: Failed to write: %s" % filename)
                log("VideoExtrasService: %s" % traceback.format_exc())
                # Make sure we close the file handle
                fileHandle.close()
                # Do not leave a corrupt file
                xbmcvfs.delete(filename)
                return
            fileHandle.close()

    def _createOverlayFile(self, target, dbid):
        # Get the path where the file exists
        rootPath = os_path_join(__profile__, target)
        if not xbmcvfs.exists(rootPath):
            # Directory does not exist yet, create one
            xbmcvfs.mkdirs(rootPath)
        
        # Generate the name of the file that the overlay will be copied to
        targetFile = os_path_join(rootPath, ("%d.png" % dbid))
        
        # TODO: Move this section to the init of the class
        # special://skin - This path points to the currently active skin's root directory. 
        skinExtrasOverlay = xbmc.translatePath( "special://skin" ).decode("utf-8")
        skinExtrasOverlay = os_path_join(skinExtrasOverlay, "videoextras_overlay.png")

        if not xbmcvfs.exists(rootPath):
            log("VideoExtrasService: No custom image, using default")
            # TODO: Add default image setting to skinExtrasOverlay

        # Now the path exists, need to copy the file over to it, giving it the name of the DBID
        xbmcvfs.copy("WHERE THE ORIGINAL IMAGE FILE IS", targetFile)
        

#########################################
# Change needed to skin
#########################################
# ViewsFileMode.xml - Line 554
#<control type="image">
#    <posx>950</posx>
#    <posy>14</posy>
#    <width>16</width>
#    <height>16</height>
#    <texture fallback="blank.png">special://profile/addon_data/script.videoextras/movies/$INFO[ListItem.DBID].png</texture>
#    <visible>System.HasAddon(script.videoextras) + Window.IsVisible(Videos) + Container.Content(Movies)</visible>
#</control>
            


###################################
# Main of the Video Extras Service
###################################
if __name__ == '__main__':
    log("VideoExtrasService: Starting service (version %s)" % __version__)

    log("VideoExtrasService: Directory for overlay images is %s" % __profile__)

    # Make sure that the service option is enabled    
    if Settings.isServiceEnabled():
        # Construct the service class
        service = VideoExtrasService()
    
        # Start by loading the last cached version into the properties
        service.loadCached()
        
        # Now refresh the caches
        service.cacheAllExtras()
        
        # Reload the refreshed caches
        service.loadCached()
    else:
        # Service not enabled
        log("VideoExtrasService: Service disabled in settings")
    
    # Now just let the service exit - it has done it's job

