# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: nil; -*-
### BEGIN LICENSE
# Copyright (C) 2011 Rick Spencer <rick.spencer@canonical.com>
# Copyright (C) 2011-2012 Kevin Mehall <km@kevinmehall.net>
#This program is free software: you can redistribute it and/or modify it 
#under the terms of the GNU General Public License version 3, as published 
#by the Free Software Foundation.
#
#This program is distributed in the hope that it will be useful, but 
#WITHOUT ANY WARRANTY; without even the implied warranties of 
#MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR 
#PURPOSE.  See the GNU General Public License for more details.
#
#You should have received a copy of the GNU General Public License along 
#with this program.  If not, see <http://www.gnu.org/licenses/>.
### END LICENSE
import logging
import math
import codecs
import dbus
import dbus.service
from xml.etree import ElementTree
from gi.repository import Gtk

class PithosMprisService(dbus.service.Object):
    MEDIA_PLAYER2_IFACE = 'org.mpris.MediaPlayer2'
    MEDIA_PLAYER2_PLAYER_IFACE = 'org.mpris.MediaPlayer2.Player'

    def __init__(self, window):
        """
        Creates a PithosSoundMenu object.

        Requires a dbus loop to be created before the gtk mainloop,
        typically by calling DBusGMainLoop(set_as_default=True).
        """

        bus_str = "org.mpris.MediaPlayer2.pithos"
        bus_name = dbus.service.BusName(bus_str, bus=dbus.SessionBus())
        dbus.service.Object.__init__(self, bus_name, "/org/mpris/MediaPlayer2")
        self.window = window
        self._volume = math.pow(self.window.player.props.volume, 1.0/3.0)
        self._metadata = {}
        self._playback_status = 'Stopped'

        self.window.connect("metadata-changed", self._metadatachange_handler)
        self.window.connect("play-state-changed", self._playstate_handler)
        self.window.player.connect("notify::volume", self._volumechange_handler)
        self.window.connect("buffering-finished", lambda window, position: self.Seeked(position // 1000))

        # Updates everything if mpris is enabled in the middle of a song
        if self.window.current_song:
            self._metadatachange_handler(self.window, self.window.current_song)
            self._playstate_handler(self.window, self._current_playback_status)

    def _playstate_handler(self, window, state):
        """Updates the playstate in the Sound Menu"""

        play_state = 'Playing' if state else 'Paused'

        if self._playback_status != play_state: # stops unneeded updates
            self._playback_status = play_state
            d = dbus.Dictionary({"PlaybackStatus":self._playback_status},
                                "sv",variant_level=1)
            self.PropertiesChanged("org.mpris.MediaPlayer2.Player",d,[])

    def _volumechange_handler(self, player, spec):
        """Updates the volume in the Sound Menu"""
        volume = math.pow(player.props.volume, 1.0/3.0)

        if self._volume != volume: # stops unneeded updates
            self._volume = volume
            d = dbus.Dictionary({"Volume": self._volume}, "sv",variant_level=1)
            self.PropertiesChanged("org.mpris.MediaPlayer2.Player",d,[])

    def _metadatachange_handler(self, window, song):
        """Updates the song info in the Sound Menu"""

        if song is self.window.current_song: # we only care about the current song
            self.PropertiesChanged(self.MEDIA_PLAYER2_PLAYER_IFACE, {
                    'Metadata': dbus.Dictionary(self._update_metadata(song), signature='sv'),
                }, [])

    def _update_metadata(self, song):
        """
        metadata changed - sets the info for the current song.

        This method is not typically overriden. It should be called
        by implementations of this class when the player has changed
        songs.

        named arguments:
            artists - a list of strings representing the artists"
            album - a string for the name of the album
            title - a string for the title of the song

        """
        # Map pithos ratings to something MPRIS understands
        if song.rating == 'love':
            userRating = 5
        else:
            userRating = 0

        # Try to use the generic audio MIME type icon from the user's current theme
        # for the cover image if we don't get one from Pandora
        # Workaround for:
        # https://github.com/eonpatapon/gnome-shell-extensions-mediaplayer/issues/248

        if song.artUrl is not None:
            artUrl = song.artUrl
        else:
            icon_sizes = Gtk.IconTheme.get_icon_sizes(Gtk.IconTheme.get_default(), 'audio-x-generic')
            if -1 in icon_sizes: # -1 is a scalable icon(svg)
                best_icon = -1
            else:
                icon_sizes = sorted(icon_sizes, key=int, reverse=True)
                best_icon = icon_sizes[0] 
            icon_info = Gtk.IconTheme.get_default().lookup_icon('audio-x-generic', best_icon, 0)
            artUrl = "file://%s" %icon_info.get_filename()

        # Ensure is a valid dbus path by converting to hex
        track_id = codecs.encode(bytes(song.trackToken, 'ascii'), 'hex').decode('ascii')
        self._metadata = {
            "mpris:trackid": '/io/github/Pithos/TrackId/' + track_id,
            "xesam:title": song.title or "Title Unknown",
            "xesam:artist": [song.artist] or ["Artist Unknown"],
            "xesam:album": song.album or "Album Unknown",
            "xesam:userRating": userRating,
            "mpris:artUrl": artUrl,
            "xesam:url": song.audioUrl,
            "mpris:length": dbus.Int64(self._current_duration),
            "pithos:rating": song.rating or "",
        }

        return self._metadata

    @property
    def _current_playback_status(self):
        """Current status "Playing", "Paused", or "Stopped"."""
        if not self.window.current_song:
            return "Stopped"
        if self.window.playing:
            return "Playing"
        else:
            return "Paused"

    @property
    def _current_metadata(self):
        """The info for the current song."""
        if self._metadata:
            return self._metadata
        else:
            return {"mpris:trackid": '/org/mpris/MediaPlayer2/TrackList/NoTrack',
                    # Workaround for https://github.com/eonpatapon/gnome-shell-extensions-mediaplayer/issues/247
                    "xesam:url": "",}
    @property
    def _current_volume(self):
        volume = self.window.player.get_property("volume")
        scaled_volume = math.pow(volume, 1.0/3.0)
        return scaled_volume

    @property
    def _current_position(self):
        if self.window.query_position() is not None:
            return self.window.query_position() // 1000
        else:
            return 0

    @property
    def _current_duration(self):
        # use the duration provided by Pandora
        #if Gstreamer hasn't figured out the duration yet
        if self.window.query_duration() is not None:
            return self.window.query_duration() // 1000
        else:
            return self.window.current_song.trackLength * 1000000

    def _set_volume(self, new_volume):
        self.window.player.set_property('volume', new_volume)

    @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature='ss', out_signature='v')
    def Get(self, interface_name, property_name):
        try:
            return self.GetAll(interface_name)[property_name]
        except KeyError:
            raise dbus.exceptions.DBusException(
                interface_name, 'Property %s was not found.' %property_name)

    @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature='ssv')
    def Set(self, interface_name, property_name, new_value):
        if interface_name == self.MEDIA_PLAYER2_IFACE:
            pass
        elif interface_name == self.MEDIA_PLAYER2_PLAYER_IFACE:
            if property_name == 'Volume':
                new_vol = math.pow(new_value, 3.0/1.0)
                self._set_volume(new_vol)
        else:
            raise dbus.exceptions.DBusException(
                'org.mpris.MediaPlayer2.pithos',
                'This object does not implement the %s interface'
                % interface_name)

    @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface_name):
        if interface_name == self.MEDIA_PLAYER2_IFACE:
            return {
                'CanQuit': True,
                'CanRaise': True,
                'HasTrackList': False,
                'Identity': 'Pithos',
                'DesktopEntry': 'pithos',
                'SupportedUriSchemes': [''],
                'SupportedMimeTypes': [''],
            }
        elif interface_name == self.MEDIA_PLAYER2_PLAYER_IFACE:
            return {
                'PlaybackStatus': self._current_playback_status,
                'LoopStatus': "None",
                'Rate': dbus.Double(1.0),
                'Shuffle': False,
                'Metadata': dbus.Dictionary(self._current_metadata, signature='sv'),
                'Volume': dbus.Double(self._current_volume),
                'Position': dbus.Int64(self._current_position),
                'MinimumRate': dbus.Double(1.0),
                'MaximumRate': dbus.Double(1.0),
                 # set CanGoNext, CanPlay and CanPause all to True
                 # to avoid applets ending up in an inconsistent state
                 # some applets only check this prop once
                 # if we can play/pause or skip a song will be decided in the methods
                'CanGoNext': True,
                'CanGoPrevious': False,
                'CanPlay': True,
                'CanPause': True,
                # CanSeek has to be True for some sound applets
                # to show the song position/duration info
                'CanSeek': True,
                'CanControl': True,
            }
        else:
            raise dbus.exceptions.DBusException(
                'org.mpris.MediaPlayer2.pithos',
                'This object does not implement the %s interface'
                % interface_name)

    @dbus.service.method(MEDIA_PLAYER2_IFACE)
    def Raise(self):
        """Bring the media player to the front when selected by the sound menu"""

        self.window.bring_to_top()

    @dbus.service.method(MEDIA_PLAYER2_IFACE)
    def Quit(self):
        """Exit the player"""

        self.window.quit()

    @dbus.service.method(MEDIA_PLAYER2_PLAYER_IFACE)
    def Previous(self):
        """Play previous song, not implemented"""

        pass

    @dbus.service.method(MEDIA_PLAYER2_PLAYER_IFACE)
    def Next(self):
        """Play next song"""
        if not self.window.waiting_for_playlist:
            self.window.next_song()

    @dbus.service.method(MEDIA_PLAYER2_PLAYER_IFACE)
    def PlayPause(self):
        if self.window.current_song:
            self.window.playpause()

    @dbus.service.method(MEDIA_PLAYER2_PLAYER_IFACE)
    def Play(self):
        if self.window.current_song:
            self.window.play()

    @dbus.service.method(MEDIA_PLAYER2_PLAYER_IFACE)
    def Pause(self):
        if self.window.current_song:
            self.window.pause()

    @dbus.service.method(MEDIA_PLAYER2_PLAYER_IFACE)
    def Stop(self):
        """Stop is only used internally, mapping to pause instead"""
        self.window.pause()

    @dbus.service.method(MEDIA_PLAYER2_PLAYER_IFACE, in_signature='ox')
    def SetPosition(self, trackid, position):
        """
        We can't actually seek, we lie so gnome-shell-extensions-mediaplayer[1] will show the
        position slider. We send a Seeked signal with the current position to make sure applets
        update their postion.

        Under normal circumstances SetPosition would tell the player where to seek to and any
        seeking caused by either the MPRIS client or the player would cause a Seeked signal to
        be fired with current track position after the seek.

        (The MPRIS client tells the player that it wants to seek to a position >>>
         the player seeks to the disired position >>>
         the player tells the MPRIS client were it actually seeked too.)

        We're skipping the middleman(Pithos) because we can't seek. Some players do not send
        a Seeked signal and some clients workaround that[2] so this may not be necessary for
        all clients.

        [1] https://github.com/eonpatapon/gnome-shell-extensions-mediaplayer/issues/246
        [2] https://github.com/eonpatapon/gnome-shell-extensions-mediaplayer#known-bugs
        """

        self.Seeked(self._current_position)

    @dbus.service.signal(MEDIA_PLAYER2_PLAYER_IFACE, signature='x')
    def Seeked(self, position):
        pass

    @dbus.service.signal(dbus.PROPERTIES_IFACE, signature='sa{sv}as')
    def PropertiesChanged(self, interface_name, changed_properties,
                          invalidated_properties):
        """PropertiesChanged

        A function necessary to implement dbus properties.

        Typically, this function is not overriden or called directly.

        """

        pass

    # python-dbus does not have our properties for introspection, so we must manually add them
    @dbus.service.method(dbus.INTROSPECTABLE_IFACE, in_signature="", out_signature="s",
                         path_keyword="object_path", connection_keyword="connection")
    def Introspect(self, object_path, connection):
        data = dbus.service.Object.Introspect(self, object_path, connection)
        xml = ElementTree.fromstring(data)

        for iface in xml.findall("interface"):
            name = iface.attrib["name"]
            if name.startswith(self.MEDIA_PLAYER2_IFACE):
                for item, value in self.GetAll(name).items():
                    prop = {"name": item, "access": "read"}
                    if item == "Volume": # Hardcode the only writable property..
                        prop["access"] = "readwrite"

                    # Ugly mapping of types to signatures, is there a helper for this?
                    # KEEP IN SYNC!
                    if isinstance(value, str):
                        prop["type"] = "s"
                    elif isinstance(value, bool):
                        prop["type"] = "b"
                    elif isinstance(value, float):
                        prop["type"] = "d"
                    elif isinstance(value, int):
                        prop["type"] = "x"
                    elif isinstance(value, list):
                        prop["type"] = "as"
                    elif isinstance(value, dict):
                        prop["type"] = "a{sv}"
                    iface.append(ElementTree.Element("property", prop))
        return ElementTree.tostring(xml, encoding="UTF-8")
