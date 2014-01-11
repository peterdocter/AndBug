#!/usr/bin/env python
# -*- coding: utf-8 -*- 

## Copyright 2011, IOActive, Inc. All rights reserved.
##
## AndBug is free software: you can redistribute it and/or modify it under 
## the terms of version 3 of the GNU Lesser General Public License as 
## published by the Free Software Foundation.
##
## AndBug is distributed in the hope that it will be useful, but WITHOUT ANY
## WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS 
## FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for 
## more details.
##
## You should have received a copy of the GNU Lesser General Public License
## along with AndBug.  If not, see <http://www.gnu.org/licenses/>.

'implementation of the "frame_value" command'

import andbug.command, andbug.screed, andbug.options

@andbug.command.action('<threadName frameInfor>', aliases=('fv',))
def frame_value(ctxt, threadName, frameName):
    '''
    函数功能：根据指定的线程名称，堆栈位置，获取相应堆栈中参数的信息
    '''
    
    thread = ctxt.sess.threads(threadName)
    frames = thread.frames()  #!!!!!!调用失败，还没找到原因
    for f in thread.frames: #t.frames是返回当前的堆栈信息
        name = str(f.loc)
        if name.find(frameName)==-1:
            continue
        if f.native:  #判断堆栈中函数的类型，是否是内部函数。如dalvik.system.NativeStart.main([Ljava/lang/String;)V <native>
            name += ' <native>'
        with andbug.screed.refer(name):
            for var_name in f:                             
                andbug.screed.item(var_name + ":" + str(f[var_name]))
     

    
