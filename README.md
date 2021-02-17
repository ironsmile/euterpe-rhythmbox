# HTTPMS Plugin for Rhythmbox

Using this plugin you can listen to your music served from a [HTTPMS server](https://github.com/ironsmile/httpms) directly in Rhythmbox.

## Installation

Create a directory and place the contents of this repository under one of the following:

* `$HOME/.local/share/rhythmbox/plugins` - install for a single user
* `/usr/lib/rhythmbox/plugins` - install for all users

## Configuration

_Insert configuration instructions here_

## Usage

After activating the plugin you will see a "HTTPMS" tab in the "Shared" group. In it you can use the "Search" menu to find your music.

[![Plugin Screenshot](images/screenshot.png)](images/screenshot.png)

## Development

_Istrunctions for developers and contributers_

## Cheat Sheet

The [Rhythmbox plug-in development guide](https://wiki.gnome.org/Apps/Rhythmbox/Plugins/WritingGuide).

## TODO

* Settings for chaning the HTTPMS address
* Timeout in the search field. Searching should start 50-100ms after the user stops typing.
* Track time
* ~~Sort tracks after search~~ (sort of done)
* Some README explaination
