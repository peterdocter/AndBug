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

'implementation of the "break" command'

import andbug.command, andbug.screed, andbug.options
from Queue import Queue

'''
该命令用来跟踪触发断点时各参数的信息
'''

def parse_frame_detail(frame):
    '''
    函数功能：解析一个堆栈帧的详细情况
    '''
    all_var_infor = frame.values
    for var_name in all_var_infor:
        #print "%s = %s" %(var_name, all_var_infor[var_name])
        andbug.screed.item(var_name + ":" + str(all_var_infor[var_name]))

def report_hit(t):
    '''
    处理METHOD_ENTRY事件回调函数，
    t有两个参数，分别  t[0] thread
                    t[1] Location
    '''
    t = t[0] #t是一个Thread类型的变量
    with andbug.screed.section("Breakpoint hit in %s, process suspended." % t):
        t.sess.suspend() #暂停当前线程
        for f in t.frames: #t.frames是返回当前的堆栈信息
            name = str(f.loc)
            if f.native:  #判断堆栈中函数的类型，是否是内部函数。如dalvik.system.NativeStart.main([Ljava/lang/String;)V <native>
                name += ' <native>'
            with andbug.screed.refer(name):
                parse_frame_detail(f)
               
               
def cmd_break_methods(ctxt, cpath, mpath):
    for c in ctxt.sess.classes(cpath):
        for m in c.methods(mpath):
            l = m.firstLoc   #这里会调用jdwp的命令
            if l.native:  #等于true，无法设置断点
                andbug.screed.item('Could not hook native %s' % l)
                continue
            l.hook(func = report_hit) #调用断点设置函数
            andbug.screed.item('Hooked %s' % l)

def cmd_break_classes(ctxt, cpath):
    for c in ctxt.sess.classes(cpath): #c为vm.py中，Class类的一个对象
        c.hookEntries(func = report_hit)
        andbug.screed.item('Hooked %s' % c)

@andbug.command.action(
    '<class> [<method>]', name='break-detail', aliases=('b',), shell=True
)
def cmd_break(ctxt, cpath, mquery=None):
    'suspends the process when a method is called'
    cpath, mname, mjni = andbug.options.parse_mquery(cpath, mquery)
    #print "cpath=" + cpath + "\t mname=" + mname + "\t mjni=" + mjni 
    #输出的结果是：cpath=Lcom/example/test/MainActivity$1;     mname=onClick     mjni=(Landroid/view/View;)V
    with andbug.screed.section('Setting Hooks'):
        if mname is None:
            cmd_break_classes(ctxt, cpath)
        else:
            cmd_break_methods(ctxt, cpath, mname)

    ctxt.block_exit()
