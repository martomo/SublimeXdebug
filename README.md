# SublimeXdebug

## Features

- Automatically display scope variables and stack trace
- Debugging layout for stack and variables
- Click variable to inspect value
- Auto-launch web browser for session based debugging (see below)

![Screenshot](https://github.com/martomo/SublimeXdebug/raw/master/doc/images/screenshot.png)

## Quick start

Use `Shift+F8` to show a list of actions:

- **Add/Remove Breakpoint**: A marker in the gutter shows the breakpoint
- **Clear all Breakpoints**: Remove all breakpoint markers in the gutter
- **Start debugging**: Start listening for an Xdebug connection
- **Start debugging (Launch browser)**: Start listening for an Xdebug connection and open debug URL

Once the Xdebug connection is captured, using the same shortcut shows these
Xdebug actions:

- **Stop debugging**: Stop listening for an Xdebug connection
- **Stop debugging (Launch browser)**: Stop listening for an Xdebug connection and open browser to end session
- **Stop debugging (Close windows)**: Stop listening for an Xdebug connection and close all Xdebug windows
- **Status**: Shows the client status in the status bar
- **Execute**: Opens command line for sending raw commands

### Debugger control menu

- **Run**: run to the next breakpoint or end of the script
- **Step Over**: steps to the next statement, if there is a function call on the line from which the step_over is issued then the debugger engine will stop at the statement after the function call in the same scope as from where the command was issued
- **Step Out**: steps out of the current scope and breaks on the statement after returning from the current function
- **Step Into**: steps to the next statement, if there is a function call involved it will break on the first statement in that function
- **Stop**: stops script execution immediately
- **Detach**: stops interaction with debugger but allows script to finish

## Shortcut keys

- `Shift+F8`: Open Xdebug quick panel
- `F8`: Open Xdebug control quick panel when debugger is connected
- `Ctrl+F8`: Toggle breakpoint
- `Ctrl+Shift+F5`: Run to next breakpoint
- `Ctrl+Shift+F6`: Step over
- `Ctrl+Shift+F7`: Step into
- `Ctrl+Shift+F8`: Step out

## Session based debugging

This plugin can initiate or terminate a debugging session by launching your default web browser and sending a web request to the configured URL with the following parameters XDEBUG_SESSION_START or XDEBUG_SESSION_STOP together with an IDE key.

For remote debugging to resolve the file locations it is required to configure the path mapping with the server path as key and local path as value.

The debug URL, IDE key and path mapping are defined in your .sublime-project file like this:

	{
		"folders":
		[
			{
				"path": "..."
			},
		],

		"settings": {
			"xdebug": {
				"url": "http://your.web.server",
				"ide_key": "your_custom_ide_key",
				"path_mapping": {
					"/path/to/file/on/server" : "/path/to/file/on/computer",
					"/var/www/htdocs/example/" : "C:/git/websites/example/"
				}
			}
		}
	}

If you do not configure the URL, the plugin will still listen for debugging connections from Xdebug, but you will need to trigger Xdebug <a href="http://xdebug.org/docs/remote">for a remote session</a>. By default the URL will use `sublime.xdebug` as IDE key.

## Gutter icon color

You can change the color of the gutter icons by adding the following scopes to your theme file: xdebug.breakpoint, xdebug.current. Icons from [Font Awesome](http://fortawesome.github.com/Font-Awesome/).

## Installing Xdebug

Of course, SublimeXdebug won't do anything if you don't install and configure Xdebug first.

	[Installation instructions](http://xdebug.org/docs/install)

Here's a quick how to setup Xdebug on Ubuntu 12.04:

- sudo apt-get install php5-xdebug
- Configure settings in /etc/php5/conf.d/xdebug.ini
- Restart Apache

### Configuration

Below is a template for xdebug.ini, this should get you started, be warned if you are on a Live environment, comment/remove `remote_connect_back`.
`remote_connect_back` (since Xdebug version 2.1) allows every debug request from any source to be accepted by Xdebug.

	[xdebug]
	zend_extension = /absolute/path/to/your/xdebug-extension.so
	xdebug.remote_enable = 1
	xdebug.remote_host = "127.0.0.1"
	xdebug.remote_port = 9000
	xdebug.remote_handler = "dbgp"
	xdebug.remote_mode = req
	xdebug.remote_connect_back = 1

## Troubleshooting

Xdebug won't stop at breakpoints on empty lines. The breakpoint must be on a line of PHP code.

By default the debugger assumes Xdebug is configured to connect on port **9000**.

If your window doesn't remove the debugging views when you stop debugging, then you can revert to a single document view by pressing `Shift+Alt+1`
