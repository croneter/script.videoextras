# -*- coding: utf-8 -*-
import sys
import os
import traceback
import xbmc
import xbmcaddon
import xbmcgui

__addon__     = xbmcaddon.Addon(id='script.videoextras')
__addonid__   = __addon__.getAddonInfo('id')
__cwd__       = __addon__.getAddonInfo('path').decode("utf-8")
__resource__  = xbmc.translatePath( os.path.join( __cwd__, 'resources' ).encode("utf-8") ).decode("utf-8")
__lib__  = xbmc.translatePath( os.path.join( __resource__, 'lib' ).encode("utf-8") ).decode("utf-8")

sys.path.append(__resource__)
sys.path.append(__lib__)

# Import the common settings
from settings import Settings
from settings import log
from settings import os_path_join

# Load the core Video Extras classes
from core import ExtrasItem
from core import SourceDetails


###################################
# Custom Player to play the extras
###################################
class ExtrasPlayer(xbmc.Player):
    def __init__(self, *args):
        self.isPlayAll = True
        self.currentlyPlaying=None
        xbmc.Player.__init__(self, *args)

    # Play the given Extras File
    def playExtraItem(self, extrasItem):
        playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
        listitem = self._getListItem(extrasItem)
        playlist.clear()
        playlist.add(extrasItem.getMediaFilename(), listitem)
        self.play(playlist)

    # Play a list of extras
    def playAll(self, extrasItems):
        log("ExtrasPlayer: playAll")
        playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
        playlist.clear()

        for exItem in extrasItems:
            # Get the list item, but not any resume information
            listitem = self._getListItem(exItem, True)
            playlist.add(exItem.getMediaFilename(), listitem)

        self.play(playlist)

        # Now the list of videos is playing we need to keep track of
        # where they are and then save their current status
        currentTime = 0
        currentlyPlayingFile = ""
        currentExtrasItem = None
        while self.isPlayingVideo():
            try:
                # Check if the same file as last time has started playing
                if currentlyPlayingFile != self.getPlayingFile():
                    # If there was previously a playing file, need to save it's state
                    if (currentlyPlayingFile != "") and (currentExtrasItem != None):
                        # Record the time that the player actually stopped
                        log("ExtrasPlayer: Played %s to time = %d" % (currentlyPlayingFile, currentTime))
                        if currentTime > 5:
                            currentExtrasItem.setResumePoint(currentTime)
                            # Now update the database with the fact this has now been watched
                            currentExtrasItem.saveState()
                        else:
                            log("ExtrasPlayer: Only played to time = %d (Not saving state)" % currentTime)

                    currentlyPlayingFile = ""
                    currentExtrasItem = None
                    currentTime = 0
                    # Last operation may have taken a bit of time as it might have written to
                    # the database, so just make sure we are still playing
                    if self.isPlayingVideo():
                        # Get the name of the currently playing file
                        currentlyPlayingFile = self.getPlayingFile()
                        for exItem in extrasItems:
                            if exItem.getMediaFilename() == currentlyPlayingFile:
                                currentExtrasItem = exItem
                                break

                # Keep track of where the current video is up to
                if self.isPlayingVideo():
                    currentTime = int(self.getTime())
            except:
                log("ExtrasPlayer: Failed to follow progress %s" % currentlyPlayingFile)
                log("ExtrasPlayer: %s" % traceback.format_exc())

            xbmc.sleep(100)
            
            # If the user selected the "Play All" option, then we do not want to
            # stop between the two videos, so do an extra wait
            if not self.isPlayingVideo():
                xbmc.sleep(3000)

        # Need to save the final file state
        if (currentlyPlayingFile != None) and (currentExtrasItem != None):
            # Record the time that the player actually stopped
            log("ExtrasPlayer: Played final %s to time = %d" % (currentlyPlayingFile, currentTime))
            if currentTime > 5:
                currentExtrasItem.setResumePoint(currentTime)
                # Now update the database with the fact this has now been watched
                currentExtrasItem.saveState()
            else:
                log("ExtrasPlayer: Only played to time = %d (Not saving state)" % currentTime)


    def onPlayBackStarted(self):
        log("ExtrasPlayer: onPlayBackStarted %s" % self.getPlayingFile())
        xbmc.Player.onPlayBackStarted(self)

    def onPlayBackEnded(self):
        log("ExtrasPlayer: onPlayBackEnded")
#        log("ExtrasPlayer: %s" % self.getPlayingFile())
        xbmc.Player.onPlayBackEnded(self)

    def onPlayBackStopped(self):
        log("ExtrasPlayer: onPlayBackStopped")
#        log("ExtrasPlayer: %s" % self.getPlayingFile())
        xbmc.Player.onPlayBackStopped(self)

    def onQueueNextItem(self):
        log("ExtrasPlayer: onQueueNextItem")
        xbmc.Player.onQueueNextItem(self)
        

    # Calls the media player to play the selected item
    @staticmethod
    def performPlayAction(extraItem):
        log("ExtrasPlayer: Playing extra video = %s" % extraItem.getFilename())
        extrasPlayer = ExtrasPlayer()
        extrasPlayer.playExtraItem( extraItem )
        
        # Don't allow this to loop forever
        loopCount = 1000
        while (not extrasPlayer.isPlayingVideo()) and (loopCount > 0):
            xbmc.sleep(1)
            loopCount = loopCount - 1

        # Looks like the video never started for some reason, do not go any further
        if loopCount == 0:
            return
        
        # Get the total duration and round it down to the nearest second
        videoDuration = int(extrasPlayer.getTotalTime())
        log("ExtrasPlayer: TotalTime of video = %d" % videoDuration)
        extraItem.setTotalDuration(videoDuration)

        currentTime = 0
        # Wait for the player to stop
        while extrasPlayer.isPlayingVideo():
            # Keep track of where the current video is up to
            currentTime = int(extrasPlayer.getTime())
            xbmc.sleep(100)

        # Record the time that the player actually stopped
        log("ExtrasPlayer: Played to time = %d" % currentTime)
        extraItem.setResumePoint(currentTime)
        
        # Now update the database with the fact this has now been watched
        extraItem.saveState()


    # Create a list item from an extras item
    def _getListItem(self, extrasItem, ignoreResume=False):
        listitem = xbmcgui.ListItem()
        # Set the display title on the video play overlay
        listitem.setInfo('video', {'studio': __addon__.getLocalizedString(32001) + " - " + SourceDetails.getTitle()})
        listitem.setInfo('video', {'Title': extrasItem.getDisplayName()})
        
        # If both the Icon and Thumbnail is set, the list screen will choose to show
        # the thumbnail
        if extrasItem.getIconImage() != "":
            listitem.setIconImage(extrasItem.getIconImage())
        # For the player OSD if there is no thumbnail, then show the VideoExtras icon
        if extrasItem.getThumbnailImage() != "":
            listitem.setThumbnailImage(extrasItem.getThumbnailImage())
        else:
            listitem.setThumbnailImage(__addon__.getAddonInfo('icon'))

        # Record if the video should start playing part-way through
        if extrasItem.isResumable() and not ignoreResume:
            if extrasItem.getResumePoint() > 1:
                listitem.setProperty('StartOffset', str(extrasItem.getResumePoint()))
        return listitem

