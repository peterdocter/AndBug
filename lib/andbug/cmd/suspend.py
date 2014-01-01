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

'implementation of the "suspend" command'

import andbug.command, andbug.screed

@andbug.command.action('[<name>]', shell=True)
def suspend(ctxt, name=None): #ctxt 是Context类
    'suspends threads in the process'
    #没有指定线程名称，则将虚拟机中所有进程挂起
    if name is None:
        ctxt.sess.suspend() 
        return andbug.screed.section('Process Suspended')
    elif name == '*':
        name = None
    
    #指定了线程的名称，则挂起相应的线程
    with andbug.screed.section('Suspending Threads'):
        for t in ctxt.sess.threads(name): #t是一个Thread类型的对象
            t.suspend()   #将对应的线程暂停
            andbug.screed.item('suspended %s' % t)
