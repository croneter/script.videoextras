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
import xbmc, xbmcgui, sys, os, re, xbmcvfs, xbmcaddon, random, xbmcplugin
if sys.version_info < (2, 7):
    import simplejson
else:
    import json as simplejson

def log(msg):
    if xbmcaddon.Addon().getSetting( "logEnabled" ) == "true":
        print "VideoExtras : " + msg

path = xbmcaddon.Addon().getAddonInfo('path').decode("utf-8")
log("Path: " + path)


class VideoExtras(xbmcgui.Window):
    def get_movie_sources(self):    
        log( "getting sources" )
        jsonResult = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "Files.GetSources", "params": {"media": "video"}, "id": 1}')
        log( jsonResult )
        shares = eval(jsonResult)
        shares = shares['result']['sources']
        
        results = []
        for s in shares:
            share = {}
            share['path'] = s['file']
            share['name'] = s['label']
            log( "found source, path: " + share['path'] + " name: " + share['name'] )
            results.append(share['path'])
            
        return results

    def showList(self, exList):
        addPlayAll = len(exList) > 1
        if addPlayAll:
            if( exList[0][0] != "PlayAll" ):
                exList.insert(0, ("PlayAll", "Play All", "Play All") )
        select = xbmcgui.Dialog().select('Extras', [name[2].replace(".sample","").replace("&#58;", ":") for name in exList])
        infoDialogId = xbmcgui.getCurrentWindowDialogId();
        listingWindow = xbmcgui.getCurrentWindowId()
        if select != -1:
            xbmc.executebuiltin("Dialog.Close(all, true)")
            # Switch the to root location as this can trigger some running plugins to stop
            xbmc.executebuiltin("xbmc.ActivateWindow(home)")
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
                    log( "Start playing " + item[0] )
                    playlist.add( item[0] )
                extrasPlayer.play( playlist )
            else:
                log( "Start playing " + exList[select][0] )
                extrasPlayer.play( exList[select][0] )
            while extrasPlayer.isPlaying():
                xbmc.sleep(100)
            xbmc.executebuiltin("xbmc.ActivateWindow(" + str(listingWindow) + ")")
            if xbmcaddon.Addon().getSetting( "extrasReturn" ) != "Video Selection":
                while(extrasPlayer.isPlaying()):
                    xbmc.sleep(100)
                if xbmcaddon.Addon().getSetting( "extrasReturn" ) == "Home":
                    xbmc.executebuiltin("xbmc.ActivateWindow(home)")
                else:
                    # Put the information dialog back up
                    xbmc.executebuiltin("xbmc.ActivateWindow(" + str(infoDialogId) + ")")
                    if xbmcaddon.Addon().getSetting( "extrasReturn" ) != "Information":
                        # Wait for the Info window to open, it can take a while
                        # this is to avoid the case where the exList dialog displays
                        # behind the info dialog
                        while( xbmcgui.getCurrentWindowDialogId() != infoDialogId):
                            xbmc.sleep(10)
                        # Reshow the exList that was previously generated
                        self.showList(exList)
        
    def showError(self):
        xbmcgui.Dialog().ok("Info", "No extras found")

    def getOrderAndDisplay(self, displayName):
        result = ( displayName, displayName )
        match = re.search("^\[(?P<order>.+)\](?P<Display>.*)", displayName)
        if match:
            orderKey = match.group('order')
            if orderKey != "":
                result = ( orderKey, match.group('Display') )
        return result
        
    def getExtrasDirFiles(self, filepath):
        basepath = os.path.dirname( filepath )
        extrasDir = basepath + os.sep + xbmcaddon.Addon().getSetting( "extrasDirName" ) + os.sep
        log( "Checking existence for " + extrasDir )
        extras = []
        if xbmcvfs.exists( extrasDir ):
            dirs, files = xbmcvfs.listdir( extrasDir )
            for filename in files:
                log( "found file: " + filename)
                if( xbmcaddon.Addon().getSetting( "excludeFiles" ) != "" ):
                    m = re.search(xbmcaddon.Addon().getSetting( "excludeFiles" ), filename )
                else:
                    m = ""
                if m:
                    log( "Skiping file: " + filename)
                else:
                    orderDisplay = self.getOrderAndDisplay( os.path.splitext(filename)[0] )
                    extras.append( ( extrasDir + filename, orderDisplay[0], orderDisplay[1] ) )
        return extras
        
    def getExtrasFiles(self, filepath):
        extras = []
        directory = os.path.dirname(filepath)
        dirs, files = xbmcvfs.listdir(directory)
        fileWoExt = os.path.splitext( os.path.basename( filepath ) )[0]
        pattern = fileWoExt + xbmcaddon.Addon().getSetting( "extrasFileTag" )
        for aFile in files:
            m = re.search(pattern + ".*", aFile)
            if m:
                path = os.path.join( directory, aFile )
                displayName = os.path.splitext(aFile[len(pattern):])[0]
                orderDisplay = self.getOrderAndDisplay( displayName )
                extras.append( ( path, orderDisplay[0], orderDisplay[1]  ) )
                log( "Found extras aFile: " + path + ", " + displayName )
        return extras

    def getNestedExtrasFiles(self, filepath):
        basepath = os.path.dirname( filepath )
        extras = []
        if xbmcvfs.exists( basepath ):
            dirs, files = xbmcvfs.listdir( basepath )
            for dirname in dirs:
                dirpath = basepath + os.sep + dirname + os.sep
                log( "Nested check in directory: " + dirpath )
                if( dirname != xbmcaddon.Addon().getSetting( "extrasDirName" ) ):
                    log( "Check directory: " + dirpath )
                    extras.extend( self.getExtrasDirFiles(dirpath) )
                    extras.extend( self.getExtrasFiles( dirpath ) )
                    extras.extend( self.getNestedExtrasFiles( dirpath ) )
        return extras

    def findExtras(self, path):
        xbmc.executebuiltin( "ActivateWindow(busydialog)" )
        files = self.getExtrasDirFiles(path)
        files.extend( self.getExtrasFiles( path ) )
        if xbmcaddon.Addon().getSetting( "searchNested" ) == "true":
            files.extend( self.getNestedExtrasFiles( path ) )
        files.sort(key=lambda tup: tup[1])
        xbmc.executebuiltin( "Dialog.Close(busydialog)" )
        if not files:
            error = True
        else:
            error = self.showList( files )
        if error:
            self.showError()



# Get the currently selected TV Show Season
log("*** ROB *** Season = " + str(xbmc.getInfoLabel("ListItem.Season")))
log("*** ROB *** FolderPath = " + str(xbmc.getInfoLabel("Container.FolderPath")))
log("*** ROB *** FolderName = " + str(xbmc.getInfoLabel("Container.FolderName")))
log("*** ROB *** ListItem.Episode = " + str(xbmc.getInfoLabel("ListItem.Episode")))

extras = VideoExtras()
if len(sys.argv) > 1:
    path = sys.argv[1]
    if path.startswith("stack://"):
        path = path.replace("stack://", "")
    log( "finding extras for " + sys.argv[1] )
    extras.findExtras(path)
