#!/usr/bin/env python
# -*- coding: utf-8 -*- 

## Copyright 2011, IOActive, Inc. All rights reserved.
##
## Redistribution and use in source and binary forms, with or without 
## modification, are permitted provided that the following conditions are 
## met:
## 
##    1. Redistributions of source code must retain the above copyright 
##       notice, this list of conditions and the following disclaimer.
## 
##    2. Redistributions in binary form must reproduce the above copyright 
##       notice, this list of conditions and the following disclaimer in the
##       documentation and/or other materials provided with the distribution.
## 
## THIS SOFTWARE IS PROVIDED BY SCOTT DUNLOP 'AS IS' AND ANY EXPRESS OR 
## IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES
## OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. 
## IN NO EVENT SHALL SCOTT DUNLOP OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT,
## INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES 
## (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR 
## SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) 
## HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, 
## STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
## ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE 
## POSSIBILITY OF SUCH DAMAGE.

import subprocess, threading, os, os.path
import re
from andbug.errors import *
from andbug import log

RE_INT = re.compile('^[0-9]+$')

from cStringIO import StringIO

class ShellException( Exception ):
    def __init__( self, command, output, status ):
        self.command = command
        self.output = output
        self.status = status

def printout( prefix, data ):
    data = data.rstrip()
    if not data: return ''
    print prefix + data.replace( '\n', '\n' + prefix )

#创建一个进程，去执行一个指定的command
def sh( command, no_echo=True, no_fail=False, no_wait=False ):
    if not no_echo: 
        printout( '>>> ', repr( command ) )

    process = subprocess.Popen( 
        command,
        stdout = subprocess.PIPE,
        stderr = subprocess.STDOUT,
        stdin = None,
        shell = True if isinstance( command, str ) else False
    )
    
    if no_wait: return process

    output, _ = process.communicate( )
    status = process.returncode
    #print "status=" + str(status)
    if status: 
        if not no_echo: printout( '!!! ', output )
        if not no_fail: raise ShellException( command, output, status )
    else:
        if not no_echo: printout( '::: ', output )

    return output

def ShellIO( command):
    '''
    临时增加以便解决多次输入的问题
    '''
    print "begin"
    process = subprocess.Popen( 
        command,
        stdout = subprocess.PIPE,
        stderr = subprocess.PIPE,
        stdin = subprocess.PIPE,
        shell = True if isinstance( command, str ) else False
    )
    
    print "end"
    return process

def which( utility ):
    for path in os.environ['PATH'].split( os.pathsep ):
        path = os.path.expanduser( os.path.join( path, utility ) )
        if os.path.exists( path ):
            return path

def test( command, no_echo=False ):
    process = subprocess.Popen( 
        command,
        stdout = subprocess.PIPE,
        stderr = subprocess.STDOUT,
        stdin = None,
        shell = True if isinstance( command, str ) else False
    )
    
    output, _ = process.communicate( )
    return process.returncode

def cat(*seqs):
    for seq in seqs:
        for item in seq:
            yield item

def seq(*args):
    return args

def adb(*args):
    log.debug(adb, ' '.join(map(str, args)))
    try:
        return sh(seq("adb", *args))
    except OSError as err:
        raise ConfigError('could not find "adb" from the Android SDK in your PATH')

#函数用于获得设备信息，使用命令"adb devices"来获得
def find_dev(dev=None):
    'determines the device for the command based on dev'
    if dev:
		#当dev不为空时，检验dev中是否是devices值
        if dev not in map( 
            lambda x: x.split()[0], 
            adb('devices').splitlines()[1:-1]
        ):
            raise OptionError('device serial number not online')
    else:
		#当dev为空时，获取devices的值后保存到dev中
        lines = adb('devices').splitlines()
        if len(lines) != 3:
            raise OptionError(
                'you must specify a device serial unless there is only'
                ' one online'
            )
        dev = lines[1].split()[0]
        
    return dev

#获得进程id的值，执行“adb shell ps” 命令
def find_pid(pid, dev=None):
    '''determines the process id for the command based on dev, pid and/or name
    返回值：如果在虚拟机中找到返回pid的值，如果没有找到返回None
    '''

    ps = ('-s', dev, 'shell', 'ps') if dev else ('shell', 'ps') 
    ps = adb(*ps)
    ps = ps.splitlines()
    head = ps[0]
    ps = (p.split() for p in ps[1:])

    if head.startswith('PID'):
        ps = ((int(p[0]), p[-1]) for p in ps)
    elif head.startswith('USER'):
        ps = ((int(p[1]), p[-1]) for p in ps)
    else:
        raise ConfigError('could not parse "adb shell ps" output')
    
    if RE_INT.match(str(pid)):
        pid = int(pid)
        ps = list(p for p in ps if p[0] == pid)
        if not ps:
            #raise OptionError('could not find process ' + str(pid))
            return None
    elif pid:
        ps = list(ps)
        ps = list(p for p in ps if p[1] == pid)
        if not ps:
            #raise OptionError('could not find process ' + str(pid))
            return None
        pid = ps[0][0]
    else:
        raise OptionError('process pid or name must be specified')

    return pid

