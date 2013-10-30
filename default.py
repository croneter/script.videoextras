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
import re
import random
import sqlite3
import traceback
import xml.etree.ElementTree as ET
#Modules XBMC
import xbmcplugin
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

def log(txt):
    if __addon__.getSetting( "logEnabled" ) == "true":
        if isinstance (txt,str):
            txt = txt.decode("utf-8")
            message = u'%s: %s' % (__addonid__, txt)
            xbmc.log(msg=message.encode("utf-8"), level=xbmc.LOGDEBUG)

##############################
# Stores Various Settings
##############################
class Settings():
    @staticmethod
    def getExcludeFiles():
        return __addon__.getSetting( "excludeFiles" )

    @staticmethod
    def getExtrasDirName():
        return __addon__.getSetting( "extrasDirName" )

    @staticmethod
    def getExtrasFileTag():
        if  __addon__.getSetting( "enableFileTag" ) != "true":
            return ""
        return __addon__.getSetting( "extrasFileTag" )

    @staticmethod
    def isSearchNested():
        return __addon__.getSetting( "searchNested" ) == "true"

    @staticmethod
    def isMenuReturnVideoSelection():
        return __addon__.getSetting( "extrasReturn" ) == __addon__.getLocalizedString(32007)

    @staticmethod
    def isMenuReturnHome():
        return __addon__.getSetting( "extrasReturn" ) == __addon__.getLocalizedString(32009)

    @staticmethod
    def isMenuReturnInformation():
        return __addon__.getSetting( "extrasReturn" ) == __addon__.getLocalizedString(32008)

    @staticmethod
    def isForceButtonDisplay():
        return __addon__.getSetting( "forceButtonDisplay" ) == "true"

    @staticmethod
    def getAddonVersion():
        return __addon__.getAddonInfo('version')

    @staticmethod
    def isDatabaseEnabled():
        return __addon__.getSetting( "enableDB" ) == "true"

    @staticmethod
    def isCustomPathEnabled():
        return __addon__.getSetting("custom_path_enable") == 'true'
    
    @staticmethod
    def getCustomPath():
        if Settings.isCustomPathEnabled():
            return __addon__.getSetting("custom_path")
        else:
            return None

    @staticmethod
    def getCustomPathMoviesDir():
        if Settings.isCustomPathEnabled():
            return __addon__.getSetting("custom_path_movies")
        else:
            return ""

    @staticmethod
    def getCustomPathTvShowsDir():
        if Settings.isCustomPathEnabled():
            return __addon__.getSetting("custom_path_tvshows")
        else:
            return ""


########################################################
# Class to store all the details for a given extras file
########################################################
class ExtrasItem():
    def __init__( self, directory, filename, isFileMatchExtra=False ):
        self.directory = directory
        self.filename = filename
        # Record if the match was by filename rather than in Extras sub-directory
        self.isFileMatchingExtra = isFileMatchExtra
        # Check if there is an NFO file to process
        if not self._loadNfoInfo(filename):
            # Get the ordering and display details from the filename
            (self.orderKey, self.displayName) = self._generateOrderAndDisplay(filename)

    # eq and lt defined for sorting order only
    def __eq__(self, other):
        # Check key, display then filename - all need to be the same for equals
        return ((self.orderKey, self.displayName, self.directory, self.filename, self.isFileMatchingExtra) ==
                (other.orderKey, other.displayName, other.directory, other.filename, other.isFileMatchingExtra))

    def __lt__(self, other):
        # Order in key, display then filename 
        return ((self.orderKey, self.displayName, self.directory, self.filename, self.isFileMatchingExtra) <
                (other.orderKey, other.displayName, other.directory, other.filename, other.isFileMatchingExtra))

    # Returns the name to display to the user for the file
    def getDisplayName(self):
        # Update the display name to allow for : in the name
        return self.displayName.replace(".sample","").replace("&#58;", ":")

    # Return the filename for the extra
    def getFilename(self):
        return self.filename

    def getDirectory(self):
        return self.directory

    def isFileMatchExtra(self):
        return self.isFileMatchingExtra
    
    def getOrderKey(self):
        return self.orderKey

    # Parses the filename to work out the display name and order key
    def _generateOrderAndDisplay(self, filename):
        # First thing is to trim the display name from the filename
        # Get just the filename, don't need the full path
        displayName = os.path.split(filename)[1]
        # Remove the file extension (e.g .avi)
        displayName = os.path.splitext( displayName )[0]
        # Remove anything before the -extras- tag (if it exists)
        extrasTag = Settings.getExtrasFileTag()
        if (extrasTag != "") and (extrasTag in displayName):
            justDescription = displayName.split(extrasTag,1)[1]
            if len(justDescription) > 0:
                displayName = justDescription
        
        result = ( displayName, displayName )
        # Search for the order which will be written as [n]
        # Followed by the display name
        match = re.search("^\[(?P<order>.+)\](?P<Display>.*)", displayName)
        if match:
            orderKey = match.group('order')
            if orderKey != "":
                result = ( orderKey, match.group('Display') )
        return result

    # Check for an NFO file for this video and reads details out of it
    # if it exists
    def _loadNfoInfo(self, filename):
        # Find out the name of the NFO file
        nfoFileName = os.path.splitext( filename )[0] + ".nfo"
        
        log("ExtrasItem: Searching for NFO file: " + nfoFileName)
        
        # Return False if file does not exist
        if not xbmcvfs.exists( nfoFileName ):
            log("ExtrasItem: No NFO file found: " + nfoFileName)
            return False

        returnValue = False

        try:
            # Need to first load the contents of the NFO file into
            # a string, this is because the XML File Parse option will
            # not handle formats like smb://
            nfoFile = xbmcvfs.File(nfoFileName)
            nfoFileStr = nfoFile.read()
            nfoFile.close()

            # Create an XML parser
            nfoXml = ET.ElementTree(ET.fromstring(nfoFileStr))
            rootElement = nfoXml.getroot()
            
            log("ExtrasItem: Root element is = " + rootElement.tag)
            
            # Check which format if being used
            if rootElement.tag == "movie":
                log("ExtrasItem: Movie format NFO detected")
                #    <movie>
                #        <title>Who knows</title>
                #        <sorttitle>Who knows 1</sorttitle>
                #    </movie>
                
                # Get the title
                self.displayName = nfoXml.findtext('title')
                # Get the sort key
                self.orderKey = nfoXml.findtext('sorttitle')
    
            elif rootElement.tag == "tvshow":
                log("ExtrasItem: TvShow format NFO detected")
                #    <tvshow>
                #        <title>Who knows</title>
                #        <sorttitle>Who knows 1</sorttitle>
                #    </tvshow>
    
                # Get the title
                self.displayName = nfoXml.findtext('title')
                # Get the sort key
                self.orderKey = nfoXml.findtext('sorttitle')
    
            elif rootElement.tag == "episodedetails":
                log("ExtrasItem: TvEpisode format NFO detected")
                #    <episodedetails>
                #        <title>Who knows</title>
                #        <season>2</season>
                #        <episode>1</episode>
                #    </episodedetails>
    
                # Get the title
                self.displayName = nfoXml.findtext('title')
                # Get the sort key
                season = nfoXml.findtext('season')
                episode = nfoXml.findtext('episode')
                
                # Need to use the season and episode to order the list
                if (season == None) or (season == ""):
                    season = "0"
                if (episode == None) or (episode == ""):
                    episode = "0"
                self.orderKey = "%02d_%02d" % (int(season), int(episode))
    
            else:
                self.displayName = None
                self.orderKey = None
                log("ExtrasItem: Unknown NFO format")
    
            del nfoXml

            if (self.displayName != None) and (self.displayName != ""):
                returnValue = True
                # If there is no order specified, use the display name
                if (self.orderKey == None) or (self.orderKey == ""):
                    self.orderKey = self.displayName
                log("ExtrasItem: Using sort key " + self.orderKey + " for " + self.displayName)
        except:
            log("ExtrasItem: Failed to process NFO: " + nfoFileName)
            log("ExtrasItem: " + traceback.format_exc())
            returnValue = False

        return returnValue


####################################################
# Class to control displaying and playing the extras
####################################################
class VideoExtrasWindow(xbmcgui.Window):
    def showList(self, exList):
        # Get the list of display names
        displayNameList = []
        for anExtra in exList:
            log("VideoExtrasWindow: adding: " + anExtra.getDisplayName() + " filename: " + anExtra.getFilename())
            displayNameList.append(anExtra.getDisplayName())

        addPlayAll = (len(exList) > 1)
        if addPlayAll:
            # Play All Selection Option
            displayNameList.insert(0, __addon__.getLocalizedString(32101) )

        # Show the list to the user
        select = xbmcgui.Dialog().select('Extras', displayNameList)
        
        infoDialogId = xbmcgui.getCurrentWindowDialogId();
        # USer has made a selection, -1 is exit
        if select != -1:
            xbmc.executebuiltin("Dialog.Close(all, true)", True)
            extrasPlayer = xbmc.Player();
            waitLoop = 0
            while extrasPlayer.isPlaying() and waitLoop < 10:
                xbmc.sleep(100)
                waitLoop = waitLoop + 1
            extrasPlayer.stop()
            # Give anything that was already playing time to stop
            while extrasPlayer.isPlaying():
                xbmc.sleep(100)
            if select == 0 and addPlayAll == True:
                playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
                playlist.clear()
                for item in exList:
                    log( "VideoExtrasWindow: Start playing " + item.getFilename() )
                    playlist.add( item.getFilename() )
                extrasPlayer.play( playlist )
            else:
                itemToPlay = select
                # If we added the PlayAll option to the list need to allow for it
                # in the selection, so add one
                if addPlayAll == True:
                    itemToPlay = itemToPlay - 1
                log( "VideoExtrasWindow: Start playing " + exList[itemToPlay].getFilename() )
                extrasPlayer.play( exList[itemToPlay].getFilename() )
            while extrasPlayer.isPlayingVideo():
                xbmc.sleep(100)
            
            # The video selection will be the default return location
            if not Settings.isMenuReturnVideoSelection():
                if Settings.isMenuReturnHome():
                    xbmc.executebuiltin("xbmc.ActivateWindow(home)", True)
                else:
                    # Put the information dialog back up
                    xbmc.executebuiltin("xbmc.ActivateWindow(" + str(infoDialogId) + ")")
                    if not Settings.isMenuReturnInformation():
                        # Wait for the Info window to open, it can take a while
                        # this is to avoid the case where the exList dialog displays
                        # behind the info dialog
                        while( xbmcgui.getCurrentWindowDialogId() != infoDialogId):
                            xbmc.sleep(100)
                        # Allow time for the screen to load - this could result in an
                        # action such as starting TvTunes
                        xbmc.sleep(1000)
                        # Before showing the list, check if someone has quickly
                        # closed the info screen while it was opening and we were waiting
                        if xbmcgui.getCurrentWindowDialogId() == infoDialogId:
                            # Reshow the exList that was previously generated
                            self.showList(exList)

    def showError(self):
        # "Info", "No extras found"
        xbmcgui.Dialog().ok(__addon__.getLocalizedString(32102), __addon__.getLocalizedString(32103))


################################################
# Class to control Searching for the extra files
################################################
class VideoExtrasFinder():
    # Controls the loading of the information for Extras Files
    def loadExtras(self, path, filename, exitOnFirst=False):
        # Check if the files are stored in a custom path
        if Settings.isCustomPathEnabled():
            filename = None
            path = self._getCustomPathDir(path)
            
            if path == None:
                return []
            else:
                log("VideoExtrasFinder: Searching in custom path " + path)
        return self.findExtras(path, filename, exitOnFirst)

    # Calculates and checks the path that files should be in
    # if using a custom path
    def _getCustomPathDir(self, path):
        # Work out which section to look in
        typeSection = Settings.getCustomPathMoviesDir()
        if not xbmc.getCondVisibility("Container.Content(movies)"):
            typeSection = Settings.getCustomPathTvShowsDir()

        # Get the last element of the path
        pathLastDir = os.path.split(path)[1]

        # Create the path with this added
        custPath = os.path.join(Settings.getCustomPath(), typeSection, pathLastDir)
        log("VideoExtrasFinder: Checking existence of custom path " + custPath)

        # Check if this path exists
        if not xbmcvfs.exists(custPath):
            # If it doesn't exist, check the path before that, this covers the
            # case where there is a TV Show with each season in it's own directory
            path2ndLastDir = os.path.split((os.path.split(path)[0]))[1]
            custPath = os.path.join(Settings.getCustomPath(), typeSection, path2ndLastDir, pathLastDir)
            log("VideoExtrasFinder: Checking existence of custom path " + custPath)
            if not xbmcvfs.exists(custPath):
                # If it still does not exist then check just the 2nd to last path
                custPath = os.path.join(Settings.getCustomPath(), typeSection, path2ndLastDir)
                log("VideoExtrasFinder: Checking existence of custom path " + custPath)
                if not xbmcvfs.exists(custPath):
                    custPath = None

        return custPath
        
    
    # Searches a given path for extras files
    def findExtras(self, path, filename, exitOnFirst=False):
        # Get the extras that are stored in the extras directory i.e. /Extras/
        files = self.getExtrasDirFiles(path, exitOnFirst)
        
        # Check if we only want the first entry, in which case exit after
        # we find the first
        if files and (exitOnFirst == True):
            return files
        
        # Then add the files that have the extras tag in the name i.e. -extras-
        files.extend( self._getExtrasFiles( path, filename, exitOnFirst ) )

        # Check if we only want the first entry, in which case exit after
        # we find the first
        if files and (exitOnFirst == True):
            return files
        
        if Settings.isSearchNested():
            files.extend( self._getNestedExtrasFiles( path, filename, exitOnFirst ) )
        files.sort()
        return files

    # Gets any extras files that are in the given extras directory
    def getExtrasDirFiles(self, basepath, exitOnFirst=False):
        # If a custom path, then don't looks for the Extras directory
        if not Settings.isCustomPathEnabled():
            # Add the name of the extras directory to the end of the path
            extrasDir = os.path.join( basepath, Settings.getExtrasDirName() )
        else:
            extrasDir = basepath
        log( "VideoExtrasFinder: Checking existence for " + extrasDir )
        extras = []
        # Check if the extras directory exists
        if xbmcvfs.exists( extrasDir ):
            # lest everything in the extras directory
            dirs, files = xbmcvfs.listdir( extrasDir )
            for filename in files:
                log( "VideoExtrasFinder: found file: " + filename)
                # Check each file in the directory to see if it should be skipped
                if not self._shouldSkipFile(filename):
                    extrasFile = os.path.join( extrasDir, filename )
                    extraItem = ExtrasItem(extrasDir, extrasFile)
                    extras.append(extraItem)
                    # Check if we are only looking for the first entry
                    if exitOnFirst == True:
                        break
        return extras

    def _getNestedExtrasFiles(self, basepath, filename, exitOnFirst=False):
        extras = []
        if xbmcvfs.exists( basepath ):
            dirs, files = xbmcvfs.listdir( basepath )
            for dirname in dirs:
                dirpath = os.path.join( basepath, dirname )
                log( "VideoExtrasFinder: Nested check in directory: " + dirpath )
                if( dirname != Settings.getExtrasDirName() ):
                    log( "VideoExtrasFinder: Check directory: " + dirpath )
                    extras.extend( self.getExtrasDirFiles(dirpath, exitOnFirst) )
                     # Check if we are only looking for the first entry
                    if files and (exitOnFirst == True):
                        break
                    extras.extend( self._getExtrasFiles( dirpath, filename, exitOnFirst ) )
                     # Check if we are only looking for the first entry
                    if files and (exitOnFirst == True):
                        break
                    extras.extend( self._getNestedExtrasFiles( dirpath, filename, exitOnFirst ) )
                     # Check if we are only looking for the first entry
                    if files and (exitOnFirst == True):
                        break
        return extras

    # Search for files with the same name as the original video file
    # but with the extras tag on, this will not recurse directories
    # as they must exist in the same directory
    def _getExtrasFiles(self, filepath, filename, exitOnFirst=False):
        extras = []
        extrasTag = Settings.getExtrasFileTag()

        # If there was no filename given, nothing to do
        if (filename == None) or (filename == "") or (extrasTag == ""):
            return extras
        directory = filepath
        dirs, files = xbmcvfs.listdir(directory)

        for aFile in files:
            if not self._shouldSkipFile(aFile) and (extrasTag in aFile):
                extrasFile = os.path.join( directory, aFile )
                extraItem = ExtrasItem(directory, extrasFile, True)
                extras.append(extraItem)
                # Check if we are only looking for the first entry
                if exitOnFirst == True:
                    break
        return extras

    # Checks if a file should be skipped because it is in the exclude list
    def _shouldSkipFile(self, filename):
        shouldSkip = False
        if( Settings.getExcludeFiles() != "" ):
            m = re.search(Settings.getExcludeFiles(), filename )
        else:
            m = ""
        if m:
            shouldSkip = True
            log( "VideoExtrasFinder: Skipping file: " + filename)
        return shouldSkip


#################################
# Main Class to control the work
#################################
class VideoExtras():
    def __init__( self, inputArg ):
        log( "VideoExtras: Finding extras for " + inputArg )
        self.baseDirectory = inputArg
        if self.baseDirectory.startswith("stack://"):
            self.baseDirectory = self.baseDirectory.split(" , ")[0]
            self.baseDirectory = self.baseDirectory.replace("stack://", "")
        # Support special paths like smb:// means that we can not just call
        # os.path.isfile as it will return false even if it is a file
        # (A bit of a shame - but that's the way it is)
        fileExt = os.path.splitext( self.baseDirectory )[1]
        # If this is a file, then get it's parent directory
        if fileExt != None and fileExt != "":
            self.baseDirectory = os.path.dirname(self.baseDirectory)
            self.filename = (os.path.split(inputArg))[1]
        else:
            self.filename = None
        log( "VideoExtras: Root directory: " + self.baseDirectory )

    def findExtras(self, exitOnFirst=False):
        # Display the busy icon while searching for files
        xbmc.executebuiltin( "ActivateWindow(busydialog)" )
        files = []
        try:
            extrasFinder = VideoExtrasFinder()
            files = extrasFinder.loadExtras(self.baseDirectory, self.filename, exitOnFirst )
        except:
            log("ExtrasItem: " + traceback.format_exc())
        xbmc.executebuiltin( "Dialog.Close(busydialog)" )
        return files

    # Enable and disable the display of the extras button
    def checkButtonEnabled(self):
        # See if the option to force the extras button is enabled,
        # if which case just make sure the hide option is cleared
        if Settings.isForceButtonDisplay():
            xbmcgui.Window( 12003 ).clearProperty("HideVideoExtrasButton")
            log("VideoExtras: Force VideoExtras Button Enabled")
        else:
            # Search for the extras, stopping when the first is found
            # only want to find out if the button should be available
            files = self.findExtras(True)
            if files:
                # Set a flag on the window so we know there is data
                xbmcgui.Window( 12003 ).clearProperty("HideVideoExtrasButton")
                log("VideoExtras: Button Enabled")
            else:
                # Hide the extras button, there are no extras
                xbmcgui.Window( 12003 ).setProperty( "HideVideoExtrasButton", "true" )
                log("VideoExtras: Button disabled")
        


    def run(self, files):
        # All the files have been retrieved, now need to display them
        extrasWindow = VideoExtrasWindow()
        if not files:
            error = True
        else:
            error = extrasWindow.showList( files )
        if error:
            extrasWindow.showError()


#################################
# Class to handle database access
#################################

#####
##### THE FOLLOWING CLASS IS JUST A TEST CLASS AT THE MOMENT
##### IF IS NOT CALLED FOR THE LIVE SYSTEM
#####

class ExtrasDB():
    def __init__( self ):
        # Start by getting the database location
        self.configPath = xbmc.translatePath(__addon__.getAddonInfo('profile'))
        self.databasefile = os.path.join(self.configPath, "extras_database.db")
        log("ExtrasDB: Database file location = " + self.databasefile)


    def cleanDatabase(self):
        # If the database file exists, delete it
        if xbmcvfs.exists(self.databasefile):
            xbmcvfs.delete(self.databasefile)
            log("ExtrasDB: Removed database: " + self.databasefile)
        else:
            log("ExtrasDB: No database exists: " + self.databasefile)
    
    def createDatabase(self):
        # Make sure the database does not already exist
        if not xbmcvfs.exists(self.databasefile):
            # Get a connection to the database, this will create the file
            conn = sqlite3.connect(self.databasefile)
            c = conn.cursor()
            
            # Create the version number table, this is a simple table
            # that just holds the version details of what created it
            # It should make upgrade later easier
            c.execute('''CREATE TABLE version (version text primary key)''')
            
            # Insert a row for the version
            versionNum = Settings.getAddonVersion()
            log("Version number = " + versionNum)
            # Run the statement passing in an array with one value
            c.execute("INSERT INTO version VALUES (?)", (versionNum,))

            # Create a table that will be used to store each extras file
            # The "id" will be auto-generated as the primary key
            c.execute('''CREATE TABLE ExtrasFile (id integer primary key, filename text, order_key text, display_name text)''')
            
            c.execute('''CREATE TABLE ExtrasDir (id integer primary key, path text, filename text, order_key text, display_name text)''')
            
            # Lookup table between the Movie or TV path/filename and the supported extras
            c.execute('''CREATE TABLE VideoExtrasFileMap (id integer primary key, video_source text, extras_id integer)''')

            # Save (commit) the changes
            conn.commit()

            # We can also close the connection if we are done with it.
            # Just be sure any changes have been committed or they will be lost.
            conn.close()
        else:
            # Check if this is an upgrade
            conn = sqlite3.connect(self.databasefile)
            c = conn.cursor()
            c.execute('SELECT * FROM version')
            log("Current version number in DB is: " + c.fetchone()[0])
            conn.close()

    def insertExtrasItem(self, extrasItem):

        conn = sqlite3.connect(self.databasefile)
        c = conn.cursor()

        # TODO: Do a select to see if the extras file already exists in the database

        # Insert one at a time so we can get the ID of each
        if extrasItem.isFileMatchExtra() :
            insertData = (extrasItem.getFilename(), extrasItem.getOrderKey(), extrasItem.getDisplayName())
            c.execute('''INSERT INTO ExtrasFile(filename, order_key, display_name) VALUES (?,?,?)''', insertData)
        else:
            insertData = (extrasItem.getDirectory(),extrasItem.getFilename(), extrasItem.getOrderKey(), extrasItem.getDisplayName())
            c.execute('''INSERT INTO ExtrasDir(path, filename, order_key, display_name) VALUES (?,?,?,?)''', insertData)

        rowId = c.lastrowid
        conn.commit()
        conn.close()
        
        return rowId

    def hasExtras(self, filename):
        # Start by selecting for the filename (if the filename option is being used)
        conn = sqlite3.connect(self.databasefile)
        c = conn.cursor()

        c.execute('SELECT count(*) FROM VideoExtrasFileMap where video_source = ?', (filename,))
        log("Count by file is: " + c.fetchone()[0])
        
        # TODO: Need to also check by directory
        conn.close()



        
#########################
# Main
#########################
try:
    if len(sys.argv) > 1:
        # get the type of operation
        log("Operation = " + sys.argv[1])
        
        # Should the existing database be removed
        if sys.argv[1] == "cleanDatabase":
            extrasDb = ExtrasDB()
            extrasDb.cleanDatabase()
        
        # All other operations require at least 2 arguments
        elif len(sys.argv) > 2:
            # Create the extras class that deals with any extras request
            videoExtras = VideoExtras(sys.argv[2])
    
            # We are either running the command or just checking for existence
            if sys.argv[1] == "check":
                videoExtras.checkButtonEnabled()
            else:
                # Perform the search command
                files = videoExtras.findExtras()
                # need to display the extras
                videoExtras.run(files)
                if Settings.isDatabaseEnabled():
                    extrasDb = ExtrasDB()
                    extrasDb.createDatabase()
except:
    log("ExtrasItem: " + traceback.format_exc())
